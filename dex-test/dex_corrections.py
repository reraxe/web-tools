"""Phase 7A append-only corrections, dispositions, reversals, and tombstones."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from dex_economics import CALCULATION_VERSION, allocate_weighted_cents


ACQUISITION_REASONS = {
    "ACQUISITION_COST_ERROR",
    "SHIPPING_TAX_FEE_CORRECTION",
    "DISCOUNT_CORRECTION",
    "OTHER",
}
BASIS_REASONS = {
    "BASIS_REALLOCATION",
    "LATE_CARD_IDENTIFICATION",
    "BULK_CORRECTION",
    "DUPLICATE_ENTRY_ERROR",
    "OTHER",
}
DISPOSITION_REASONS = {
    "DUPLICATE_ENTRY_ERROR",
    "CORRECTION_HOLD",
    "DAMAGED",
    "MISSING_LOST",
    "DISPOSED",
    "OTHER",
}
PHYSICAL_LOSS_REASONS = {"DAMAGED", "MISSING_LOST", "DISPOSED", "OTHER"}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _text(value: object, limit: int = 1000) -> str:
    return str(value or "").strip()[:limit]


def _money_cents(value: object, label: str, *, signed: bool = False) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a dollar amount")
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{label} must be a dollar amount") from None
    if not amount.is_finite() or amount.as_tuple().exponent < -2:
        raise ValueError(f"{label} must use no more than two decimal places")
    cents = int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if not signed and cents < 0:
        raise ValueError(f"{label} cannot be negative")
    return cents


def _positive_id(value: object, label: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} is required") from None
    if result < 1:
        raise ValueError(f"{label} is required")
    return result


def _batch(db: sqlite3.Connection, batch_id: int) -> sqlite3.Row:
    row = db.execute("SELECT * FROM batches WHERE id=?", (batch_id,)).fetchone()
    if not row:
        raise ValueError("Batch not found")
    if row["economics_mode"] not in ("SEALED_RIP", "SINGLES_KNOWN_COST", "SINGLES_LUMP_SUM"):
        raise ValueError("Phase 7A corrections require authoritative acquisition facts")
    if row["final_usd_paid_cents"] is None:
        raise ValueError("Trustworthy final USD acquisition cost is required")
    sealed_facts_locked = row["economics_mode"] == "SEALED_RIP" and bool(
        db.execute(
            """SELECT 1 FROM sealed_units su
                 LEFT JOIN sealed_unit_events sue ON sue.sealed_unit_id=su.id
                WHERE su.batch_id=? AND (su.status<>'REMAINING' OR sue.event_type IN ('OPENED','SOLD','ADJUSTED'))
                LIMIT 1""",
            (batch_id,),
        ).fetchone()
    )
    if row["economics_status"] != "FINALIZED" and not sealed_facts_locked:
        raise ValueError("Finalize economics before using the audited correction workflow")
    return row


def _request(db: sqlite3.Connection, payload: dict) -> tuple[str, dict | None]:
    request_id = _text(payload.get("request_id"), 100)
    if not request_id:
        raise ValueError("A unique request ID is required")
    duplicate = db.execute(
        "SELECT event_id FROM economic_events WHERE request_id=?", (request_id,)
    ).fetchone()
    return request_id, event_payload(db, duplicate[0]) if duplicate else None


def _reason(payload: dict, allowed: set[str], label: str) -> tuple[str, str]:
    reason = _text(payload.get("reason_code"), 50).upper()
    if reason not in allowed:
        raise ValueError(f"Choose a standardized {label} reason")
    notes = _text(payload.get("notes"), 1000)
    if not notes:
        raise ValueError("Notes are required for material corrections and dispositions")
    return reason, notes


def current_acquisition_cost_cents(db: sqlite3.Connection, batch_id: int) -> int:
    row = db.execute("SELECT final_usd_paid_cents FROM batches WHERE id=?", (batch_id,)).fetchone()
    if not row or row[0] is None:
        raise ValueError("Trustworthy final USD acquisition cost is required")
    correction = db.execute(
        """SELECT COALESCE(SUM(ee.amount_delta_cents),0)
             FROM economic_event_entries ee
             JOIN economic_events e ON e.event_id=ee.event_id
            WHERE e.batch_id=? AND ee.entry_type='ACQUISITION_COST'
              AND ee.target_type='BATCH' AND ee.target_id=?""",
        (batch_id, batch_id),
    ).fetchone()[0]
    return int(row[0]) + int(correction or 0)


def _ledger_delta(
    db: sqlite3.Connection, entry_type: str, target_type: str, target_id: int
) -> int:
    return int(
        db.execute(
            """SELECT COALESCE(SUM(amount_delta_cents),0)
                 FROM economic_event_entries
                WHERE entry_type=? AND target_type=? AND target_id=?""",
            (entry_type, target_type, target_id),
        ).fetchone()[0]
        or 0
    )


def current_card_basis_cents(db: sqlite3.Connection, card_id: int) -> int:
    original = db.execute(
        """SELECT COALESCE(SUM(amount_delta_cents),0) FROM rip_basis_events
            WHERE target_type='CARD' AND card_id=?""",
        (card_id,),
    ).fetchone()[0]
    return int(original or 0) + _ledger_delta(db, "BASIS", "CARD", card_id)


def current_bulk_basis_cents(db: sqlite3.Connection, rip_id: int) -> int:
    original = db.execute(
        """SELECT COALESCE(SUM(amount_delta_cents),0) FROM rip_basis_events
            WHERE target_type='BULK' AND rip_session_id=?""",
        (rip_id,),
    ).fetchone()[0]
    return int(original or 0) + _ledger_delta(db, "BASIS", "RIP_BULK", rip_id)


def current_sealed_basis_cents(db: sqlite3.Connection, unit_id: int) -> int:
    row = db.execute("SELECT basis_cents FROM sealed_units WHERE id=?", (unit_id,)).fetchone()
    if not row:
        raise ValueError("Sealed unit not found")
    return int(row[0]) + _ledger_delta(db, "BASIS", "SEALED_UNIT", unit_id)


def current_operational_loss_cents(db: sqlite3.Connection, batch_id: int) -> int:
    return _ledger_delta(db, "OPERATIONAL_LOSS", "BATCH", batch_id)


def _active_tombstone(db: sqlite3.Connection, entity_type: str, entity_id: int) -> sqlite3.Row | None:
    return db.execute(
        """SELECT t.*, e.event_type, e.payload
             FROM economic_tombstones t
             JOIN economic_events e ON e.event_id=t.event_id
             LEFT JOIN economic_events reversal ON reversal.reverses_event_id=e.event_id
            WHERE t.entity_type=? AND t.entity_id=? AND reversal.event_id IS NULL
            ORDER BY t.id DESC LIMIT 1""",
        (entity_type, entity_id),
    ).fetchone()


def _target(db: sqlite3.Connection, batch_id: int, target_type: str, target_id: int) -> dict:
    target_type = target_type.upper()
    if target_type == "CARD":
        row = db.execute(
            """SELECT c.id, c.sku AS identifier, c.batch_id, r.status AS rip_status
                 FROM cards c LEFT JOIN rip_sessions r ON r.id=c.rip_session_id
                WHERE c.id=?""",
            (target_id,),
        ).fetchone()
        if not row or int(row["batch_id"]) != batch_id:
            raise ValueError("Card basis target must belong to this acquisition batch")
        if row["rip_status"] != "FINALIZED":
            raise ValueError("Card basis targets must belong to a finalized rip/allocation session")
        if _active_tombstone(db, "CARD", int(row["id"])):
            raise ValueError("A disposed or correction-held card cannot receive basis")
        return {
            "target_type": "CARD",
            "target_id": int(row["id"]),
            "identifier": row["identifier"],
            "current_basis_cents": current_card_basis_cents(db, int(row["id"])),
        }
    if target_type == "RIP_BULK":
        row = db.execute(
            "SELECT id, rip_code AS identifier, batch_id, status FROM rip_sessions WHERE id=?",
            (target_id,),
        ).fetchone()
        if not row or int(row["batch_id"]) != batch_id:
            raise ValueError("Bulk basis target must belong to this acquisition batch")
        if row["status"] != "FINALIZED":
            raise ValueError("Bulk basis targets require a finalized rip session")
        return {
            "target_type": "RIP_BULK",
            "target_id": int(row["id"]),
            "identifier": f"{row['identifier']} bulk",
            "current_basis_cents": current_bulk_basis_cents(db, int(row["id"])),
        }
    if target_type == "SEALED_UNIT":
        row = db.execute(
            "SELECT id, unit_code AS identifier, batch_id FROM sealed_units WHERE id=?",
            (target_id,),
        ).fetchone()
        if not row or int(row["batch_id"]) != batch_id:
            raise ValueError("Sealed-unit basis target must belong to this acquisition batch")
        return {
            "target_type": "SEALED_UNIT",
            "target_id": int(row["id"]),
            "identifier": row["identifier"],
            "current_basis_cents": current_sealed_basis_cents(db, int(row["id"])),
        }
    if target_type == "OPERATIONAL_LOSS":
        if target_id != batch_id:
            raise ValueError("Operational loss target must be this acquisition batch")
        return {
            "target_type": "BATCH",
            "target_id": batch_id,
            "identifier": "Operational loss/disposition",
            "current_basis_cents": current_operational_loss_cents(db, batch_id),
            "entry_type": "OPERATIONAL_LOSS",
        }
    raise ValueError("Unknown correction target")


def _ensure_nonnegative(db: sqlite3.Connection, batch_id: int, entries: list[dict]) -> None:
    grouped: dict[tuple[str, str, int], int] = {}
    for entry in entries:
        key = (entry["entry_type"], entry["target_type"], int(entry["target_id"]))
        grouped[key] = grouped.get(key, 0) + int(entry["amount_delta_cents"])
    for (entry_type, target_type, target_id), delta in grouped.items():
        if entry_type == "ACQUISITION_COST":
            current = current_acquisition_cost_cents(db, batch_id)
        elif entry_type == "OPERATIONAL_LOSS":
            current = current_operational_loss_cents(db, batch_id)
        elif target_type == "CARD":
            current = current_card_basis_cents(db, target_id)
        elif target_type == "RIP_BULK":
            current = current_bulk_basis_cents(db, target_id)
        elif target_type == "SEALED_UNIT":
            current = current_sealed_basis_cents(db, target_id)
        else:
            raise ValueError("Unsupported ledger target")
        if current + delta < 0:
            raise ValueError("Correction would make acquisition cost, basis, or loss negative")


def _insert_event(
    db: sqlite3.Connection,
    *,
    request_id: str,
    batch_id: int,
    event_type: str,
    reason_code: str,
    notes: str,
    entries: list[dict],
    payload: dict,
    effective_at: str | None = None,
    reverses_event_id: str | None = None,
    tombstone: dict | None = None,
) -> dict:
    now = utcnow()
    event_id = f"ECO7A-{uuid.uuid4()}"
    db.execute(
        """INSERT INTO economic_events
           (event_id, request_id, batch_id, event_type, reason_code, effective_at,
            recorded_at, notes, reverses_event_id, payload)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event_id,
            request_id,
            batch_id,
            event_type,
            reason_code,
            effective_at or now,
            now,
            notes,
            reverses_event_id,
            json.dumps(payload, separators=(",", ":"), sort_keys=True),
        ),
    )
    for entry in entries:
        amount = int(entry["amount_delta_cents"])
        if not amount:
            continue
        db.execute(
            """INSERT INTO economic_event_entries
               (event_id, entry_type, target_type, target_id, amount_delta_cents, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                event_id,
                entry["entry_type"],
                entry["target_type"],
                int(entry["target_id"]),
                amount,
                now,
            ),
        )
    if tombstone:
        db.execute(
            """INSERT INTO economic_tombstones
               (event_id, entity_type, entity_id, stable_identifier, batch_id,
                reason_code, snapshot, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id,
                tombstone["entity_type"],
                int(tombstone["entity_id"]),
                tombstone["stable_identifier"],
                batch_id,
                reason_code,
                json.dumps(tombstone["snapshot"], separators=(",", ":"), sort_keys=True),
                now,
            ),
        )
    db.execute(
        """INSERT INTO activity_log (created_at, action_type, description, payload)
           VALUES (?, 'ECONOMIC_EVENT', ?, ?)""",
        (
            now,
            f"Recorded {event_type.replace('_', ' ').lower()} ({event_id})",
            json.dumps(
                {
                    "event_id": event_id,
                    "request_id": request_id,
                    "batch_id": batch_id,
                    "event_type": event_type,
                    "reason_code": reason_code,
                    "reverses_event_id": reverses_event_id,
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
        ),
    )
    return event_payload(db, event_id)


def event_payload(db: sqlite3.Connection, event_id: str) -> dict:
    row = db.execute("SELECT * FROM economic_events WHERE event_id=?", (event_id,)).fetchone()
    if not row:
        raise ValueError("Economic event not found")
    entries = [
        dict(item)
        for item in db.execute(
            "SELECT entry_type, target_type, target_id, amount_delta_cents FROM economic_event_entries WHERE event_id=? ORDER BY id",
            (event_id,),
        )
    ]
    tombstones = [
        dict(item)
        for item in db.execute(
            "SELECT entity_type, entity_id, stable_identifier, reason_code, created_at FROM economic_tombstones WHERE event_id=? ORDER BY id",
            (event_id,),
        )
    ]
    reversal = db.execute(
        "SELECT event_id, recorded_at FROM economic_events WHERE reverses_event_id=?",
        (event_id,),
    ).fetchone()
    result = dict(row)
    result["calculation_version"] = CALCULATION_VERSION
    result["entries"] = entries
    result["tombstones"] = tombstones
    result["payload"] = json.loads(row["payload"] or "{}")
    result["reversed"] = reversal is not None
    result["reversed_by_event_id"] = reversal["event_id"] if reversal else None
    result["reversible"] = row["event_type"] != "REVERSAL" and reversal is None
    return result


def _sealed_acquisition_adjustments(
    db: sqlite3.Connection, batch_id: int, delta: int
) -> list[dict]:
    units = db.execute(
        "SELECT id FROM sealed_units WHERE batch_id=? ORDER BY id", (batch_id,)
    ).fetchall()
    recipients: list[tuple[int, bool]] = []
    for row in units:
        tombstone = _active_tombstone(db, "SEALED_UNIT", int(row["id"]))
        if tombstone and tombstone["reason_code"] == "DUPLICATE_ENTRY_ERROR":
            continue
        physical_loss = bool(tombstone and tombstone["reason_code"] in PHYSICAL_LOSS_REASONS)
        recipients.append((int(row["id"]), physical_loss))
    if not recipients:
        raise ValueError("No valid sealed units remain for acquisition-cost allocation")
    allocations = allocate_weighted_cents(delta, [(unit_id, 1) for unit_id, _ in recipients])
    loss_delta = 0
    entries: list[dict] = []
    loss_ids = {unit_id for unit_id, physical in recipients if physical}
    for item in allocations:
        if int(item.stable_id) in loss_ids:
            loss_delta += item.cents
        else:
            entries.append(
                {
                    "entry_type": "BASIS",
                    "target_type": "SEALED_UNIT",
                    "target_id": int(item.stable_id),
                    "amount_delta_cents": item.cents,
                }
            )
    if loss_delta:
        entries.append(
            {
                "entry_type": "OPERATIONAL_LOSS",
                "target_type": "BATCH",
                "target_id": batch_id,
                "amount_delta_cents": loss_delta,
            }
        )
    return entries


def correct_acquisition_cost(db: sqlite3.Connection, batch_id: int, payload: dict) -> dict:
    batch = _batch(db, batch_id)
    request_id, duplicate = _request(db, payload)
    if duplicate:
        return duplicate
    reason, notes = _reason(payload, ACQUISITION_REASONS, "acquisition-cost correction")
    new_total = _money_cents(payload.get("new_total_usd"), "Corrected final USD amount")
    current_total = current_acquisition_cost_cents(db, batch_id)
    delta = new_total - current_total
    if not delta:
        raise ValueError("Corrected acquisition cost must differ from the current authoritative cost")
    entries = [
        {
            "entry_type": "ACQUISITION_COST",
            "target_type": "BATCH",
            "target_id": batch_id,
            "amount_delta_cents": delta,
        }
    ]
    if batch["economics_mode"] == "SEALED_RIP":
        allocation_entries = _sealed_acquisition_adjustments(db, batch_id, delta)
    else:
        raw = payload.get("basis_adjustments")
        if not isinstance(raw, list) or not raw:
            if payload.get("allocation_target_type") and payload.get("allocation_target_id"):
                raw = [{
                    "target_type": payload.get("allocation_target_type"),
                    "target_id": payload.get("allocation_target_id"),
                    "delta_cents": delta,
                }]
            else:
                raise ValueError("Singles acquisition corrections require an explicit basis target")
        allocation_entries = []
        for item in raw:
            target_type = _text(item.get("target_type"), 30).upper()
            target_id = _positive_id(item.get("target_id"), "Basis target")
            target = _target(db, batch_id, target_type, target_id)
            raw_delta = item.get("delta_cents")
            allocation_entries.append(
                {
                    "entry_type": target.get("entry_type", "BASIS"),
                    "target_type": target["target_type"],
                    "target_id": target["target_id"],
                    "amount_delta_cents": int(raw_delta) if raw_delta is not None else _money_cents(
                        item.get("delta"), "Basis adjustment", signed=True
                    ),
                }
            )
        if sum(item["amount_delta_cents"] for item in allocation_entries) != delta:
            raise ValueError("Basis adjustments must reconcile exactly to the acquisition-cost change")
    entries.extend(allocation_entries)
    _ensure_nonnegative(db, batch_id, entries)
    return _insert_event(
        db,
        request_id=request_id,
        batch_id=batch_id,
        event_type="ACQUISITION_COST_CORRECTION",
        reason_code=reason,
        notes=notes,
        entries=entries,
        effective_at=_text(payload.get("effective_at"), 40) or None,
        payload={
            "original_source_cost_cents": int(batch["final_usd_paid_cents"]),
            "prior_corrected_cost_cents": current_total,
            "corrected_cost_cents": new_total,
            "delta_cents": delta,
            "allocation_rule": "STABLE_SEALED_UNIT_EQUAL" if batch["economics_mode"] == "SEALED_RIP" else "EXPLICIT_TARGETS",
        },
    )


def transfer_basis(db: sqlite3.Connection, batch_id: int, payload: dict) -> dict:
    _batch(db, batch_id)
    request_id, duplicate = _request(db, payload)
    if duplicate:
        return duplicate
    reason, notes = _reason(payload, BASIS_REASONS, "basis-correction")
    source = _target(
        db,
        batch_id,
        _text(payload.get("source_type"), 30),
        _positive_id(payload.get("source_id"), "Basis source"),
    )
    destination = _target(
        db,
        batch_id,
        _text(payload.get("destination_type"), 30),
        _positive_id(payload.get("destination_id"), "Basis destination"),
    )
    if (source["target_type"], source["target_id"]) == (
        destination["target_type"],
        destination["target_id"],
    ):
        raise ValueError("Basis source and destination must be different")
    if source["target_type"] not in ("CARD", "RIP_BULK") or destination["target_type"] not in ("CARD", "RIP_BULK"):
        raise ValueError("Phase 7A basis transfers are limited to finalized cards and rip bulk")
    amount = _money_cents(payload.get("amount"), "Basis transfer")
    if amount <= 0:
        raise ValueError("Basis transfer must be greater than $0.00")
    entries = [
        {
            "entry_type": "BASIS",
            "target_type": source["target_type"],
            "target_id": source["target_id"],
            "amount_delta_cents": -amount,
        },
        {
            "entry_type": "BASIS",
            "target_type": destination["target_type"],
            "target_id": destination["target_id"],
            "amount_delta_cents": amount,
        },
    ]
    _ensure_nonnegative(db, batch_id, entries)
    return _insert_event(
        db,
        request_id=request_id,
        batch_id=batch_id,
        event_type="BASIS_TRANSFER",
        reason_code=reason,
        notes=notes,
        entries=entries,
        effective_at=_text(payload.get("effective_at"), 40) or None,
        payload={
            "amount_cents": amount,
            "source": source,
            "destination": destination,
        },
    )


def _disposition_entries(
    db: sqlite3.Connection,
    batch_id: int,
    reason: str,
    source_type: str,
    source_id: int,
    basis: int,
    payload: dict,
) -> list[dict]:
    if not basis or reason == "CORRECTION_HOLD":
        return []
    source = {
        "entry_type": "BASIS",
        "target_type": source_type,
        "target_id": source_id,
        "amount_delta_cents": -basis,
    }
    if reason in PHYSICAL_LOSS_REASONS:
        return [
            source,
            {
                "entry_type": "OPERATIONAL_LOSS",
                "target_type": "BATCH",
                "target_id": batch_id,
                "amount_delta_cents": basis,
            },
        ]
    if reason == "DUPLICATE_ENTRY_ERROR" and source_type == "CARD":
        destination = _target(
            db,
            batch_id,
            _text(payload.get("destination_type"), 30),
            _positive_id(payload.get("destination_id"), "Duplicate-basis destination"),
        )
        if (destination["target_type"], destination["target_id"]) == ("CARD", source_id):
            raise ValueError("Duplicate basis must be reallocated away from the duplicate card")
        return [
            source,
            {
                "entry_type": "BASIS",
                "target_type": destination["target_type"],
                "target_id": destination["target_id"],
                "amount_delta_cents": basis,
            },
        ]
    if reason == "DUPLICATE_ENTRY_ERROR" and source_type == "SEALED_UNIT":
        recipients = [
            int(row[0])
            for row in db.execute(
                "SELECT id FROM sealed_units WHERE batch_id=? AND id<>? AND status<>'ADJUSTED' ORDER BY id",
                (batch_id, source_id),
            ).fetchall()
            if not (
                (tombstone := _active_tombstone(db, "SEALED_UNIT", int(row[0])))
                and tombstone["reason_code"] == "DUPLICATE_ENTRY_ERROR"
            )
        ]
        if not recipients:
            raise ValueError("Duplicate sealed-unit basis has no valid unit to receive reallocation")
        allocations = allocate_weighted_cents(basis, [(unit_id, 1) for unit_id in recipients])
        return [source] + [
            {
                "entry_type": "BASIS",
                "target_type": "SEALED_UNIT",
                "target_id": int(item.stable_id),
                "amount_delta_cents": item.cents,
            }
            for item in allocations
        ]
    return []


def dispose_card(db: sqlite3.Connection, sku: str, payload: dict) -> dict:
    card = db.execute("SELECT * FROM cards WHERE sku=?", (sku,)).fetchone()
    if not card:
        raise ValueError("Card not found")
    batch_id = int(card["batch_id"])
    _batch(db, batch_id)
    request_id, duplicate = _request(db, payload)
    if duplicate:
        return duplicate
    reason, notes = _reason(payload, DISPOSITION_REASONS, "card disposition")
    if card["status"] == "SOLD":
        raise ValueError("Sold-card returns and post-sale corrections belong to Phase 7B")
    if _active_tombstone(db, "CARD", int(card["id"])):
        raise ValueError("Card already has an active correction/disposition tombstone")
    basis = current_card_basis_cents(db, int(card["id"]))
    entries = _disposition_entries(
        db, batch_id, reason, "CARD", int(card["id"]), basis, payload
    )
    _ensure_nonnegative(db, batch_id, entries)
    state_before = {
        "status": card["status"],
        "recycled_at": card["recycled_at"],
        "recycle_reason": card["recycle_reason"],
        "purge_after": card["purge_after"],
        "pre_recycle_status": card["pre_recycle_status"],
    }
    event = _insert_event(
        db,
        request_id=request_id,
        batch_id=batch_id,
        event_type="CARD_DISPOSITION",
        reason_code=reason,
        notes=notes,
        entries=entries,
        effective_at=_text(payload.get("effective_at"), 40) or None,
        payload={
            "entity_type": "CARD",
            "entity_id": int(card["id"]),
            "sku": card["sku"],
            "basis_before_cents": basis,
            "state_before": state_before,
            "treatment": "REALLOCATED" if reason == "DUPLICATE_ENTRY_ERROR" else "HOLD" if reason == "CORRECTION_HOLD" else "OPERATIONAL_LOSS",
        },
        tombstone={
            "entity_type": "CARD",
            "entity_id": int(card["id"]),
            "stable_identifier": card["sku"],
            "snapshot": dict(card),
        },
    )
    now = utcnow()
    db.execute(
        """UPDATE cards SET recycled_at=COALESCE(recycled_at, ?), recycle_reason=?,
                  purge_after=NULL, pre_recycle_status=COALESCE(pre_recycle_status,status),
                  updated_at=? WHERE id=?""",
        (now, reason, now, card["id"]),
    )
    return event_payload(db, event["event_id"])


def dispose_sealed_unit(db: sqlite3.Connection, unit_id: int, payload: dict) -> dict:
    unit = db.execute("SELECT * FROM sealed_units WHERE id=?", (unit_id,)).fetchone()
    if not unit:
        raise ValueError("Sealed unit not found")
    batch_id = int(unit["batch_id"])
    _batch(db, batch_id)
    request_id, duplicate = _request(db, payload)
    if duplicate:
        return duplicate
    reason, notes = _reason(payload, DISPOSITION_REASONS, "sealed quantity correction")
    if unit["status"] != "REMAINING":
        raise ValueError("Only a remaining sealed unit can receive a Phase 7A quantity correction")
    if _active_tombstone(db, "SEALED_UNIT", unit_id):
        raise ValueError("Sealed unit already has an active correction/disposition tombstone")
    basis = current_sealed_basis_cents(db, unit_id)
    entries = _disposition_entries(
        db, batch_id, reason, "SEALED_UNIT", unit_id, basis, payload
    )
    _ensure_nonnegative(db, batch_id, entries)
    event = _insert_event(
        db,
        request_id=request_id,
        batch_id=batch_id,
        event_type="SEALED_QUANTITY_CORRECTION",
        reason_code=reason,
        notes=notes,
        entries=entries,
        effective_at=_text(payload.get("effective_at"), 40) or None,
        payload={
            "entity_type": "SEALED_UNIT",
            "entity_id": unit_id,
            "unit_code": unit["unit_code"],
            "basis_before_cents": basis,
            "state_before": {"status": unit["status"]},
            "treatment": "REALLOCATED" if reason == "DUPLICATE_ENTRY_ERROR" else "HOLD" if reason == "CORRECTION_HOLD" else "OPERATIONAL_LOSS",
        },
        tombstone={
            "entity_type": "SEALED_UNIT",
            "entity_id": unit_id,
            "stable_identifier": unit["unit_code"],
            "snapshot": dict(unit),
        },
    )
    now = utcnow()
    changed = db.execute(
        "UPDATE sealed_units SET status='ADJUSTED', updated_at=? WHERE id=? AND status='REMAINING'",
        (now, unit_id),
    )
    if changed.rowcount != 1:
        raise sqlite3.IntegrityError("Sealed unit changed during disposition")
    db.execute(
        """INSERT INTO sealed_unit_events
           (event_id, request_id, sealed_unit_id, event_type, from_status, to_status,
            reason_code, notes, effective_at, recorded_at, payload)
           VALUES (?, ?, ?, 'ADJUSTED', 'REMAINING', 'ADJUSTED', ?, ?, ?, ?, ?)""",
        (
            f"SEALED-{uuid.uuid4()}",
            f"{request_id}-SEALED",
            unit_id,
            reason,
            notes,
            event["effective_at"],
            now,
            json.dumps({"economic_event_id": event["event_id"]}, separators=(",", ":")),
        ),
    )
    return event_payload(db, event["event_id"])


def reverse_event(db: sqlite3.Connection, event_id: str, payload: dict) -> dict:
    original = event_payload(db, event_id)
    request_id, duplicate = _request(db, payload)
    if duplicate:
        return duplicate
    if original["event_type"] == "REVERSAL":
        raise ValueError("Reverse the original correction with a new reviewed workflow; reversal-of-reversal is not supported in Phase 7A")
    if original["reversed"]:
        raise ValueError("Economic event already has a linked reversal")
    notes = _text(payload.get("notes"), 1000)
    if not notes:
        raise ValueError("Reversal notes are required")
    batch_id = int(original["batch_id"])
    entries = [
        {
            "entry_type": item["entry_type"],
            "target_type": item["target_type"],
            "target_id": int(item["target_id"]),
            "amount_delta_cents": -int(item["amount_delta_cents"]),
        }
        for item in original["entries"]
    ]
    _ensure_nonnegative(db, batch_id, entries)

    entity_type = original["payload"].get("entity_type")
    entity_id = original["payload"].get("entity_id")
    if entity_type == "CARD":
        card = db.execute("SELECT * FROM cards WHERE id=?", (entity_id,)).fetchone()
        if not card or not _active_tombstone(db, "CARD", int(entity_id)):
            raise ValueError("Card disposition state no longer matches the event being reversed")
    elif entity_type == "SEALED_UNIT":
        unit = db.execute("SELECT * FROM sealed_units WHERE id=?", (entity_id,)).fetchone()
        if not unit or unit["status"] != "ADJUSTED" or not _active_tombstone(db, "SEALED_UNIT", int(entity_id)):
            raise ValueError("Sealed disposition state no longer matches the event being reversed")

    reversal = _insert_event(
        db,
        request_id=request_id,
        batch_id=batch_id,
        event_type="REVERSAL",
        reason_code="OPERATOR_REVERSAL",
        notes=notes,
        entries=entries,
        effective_at=_text(payload.get("effective_at"), 40) or None,
        reverses_event_id=event_id,
        payload={
            "reverses_event_id": event_id,
            "original_event_type": original["event_type"],
            "entity_type": entity_type,
            "entity_id": entity_id,
        },
    )
    if entity_type == "CARD":
        before = original["payload"]["state_before"]
        db.execute(
            """UPDATE cards SET status=?, recycled_at=?, recycle_reason=?, purge_after=?,
                      pre_recycle_status=?, updated_at=? WHERE id=?""",
            (
                before["status"],
                before["recycled_at"],
                before["recycle_reason"],
                before["purge_after"],
                before["pre_recycle_status"],
                utcnow(),
                entity_id,
            ),
        )
    elif entity_type == "SEALED_UNIT":
        now = utcnow()
        previous_status = original["payload"]["state_before"]["status"]
        db.execute(
            "UPDATE sealed_units SET status=?, updated_at=? WHERE id=? AND status='ADJUSTED'",
            (previous_status, now, entity_id),
        )
        db.execute(
            """INSERT INTO sealed_unit_events
               (event_id, request_id, sealed_unit_id, event_type, from_status, to_status,
                reason_code, notes, effective_at, recorded_at, payload)
               VALUES (?, ?, ?, 'ADJUSTED', 'ADJUSTED', ?, 'OPERATOR_REVERSAL', ?, ?, ?, ?)""",
            (
                f"SEALED-{uuid.uuid4()}",
                f"{request_id}-SEALED",
                entity_id,
                previous_status,
                notes,
                reversal["effective_at"],
                now,
                json.dumps({"economic_event_id": reversal["event_id"]}, separators=(",", ":")),
            ),
        )
    return event_payload(db, reversal["event_id"])


def batch_corrections_payload(db: sqlite3.Connection, batch_id: int) -> dict:
    batch = _batch(db, batch_id)
    cards = db.execute(
        """SELECT c.id, c.sku, c.name, c.status, c.recycled_at, c.rip_session_id,
                  r.status AS rip_status,
                  COALESCE(rb.amount,0) + COALESCE(eb.amount,0) AS basis_cents,
                  CASE WHEN EXISTS (
                      SELECT 1 FROM economic_tombstones et
                      JOIN economic_events e ON e.event_id=et.event_id
                      LEFT JOIN economic_events er ON er.reverses_event_id=e.event_id
                      WHERE et.entity_type='CARD' AND et.entity_id=c.id AND er.event_id IS NULL
                  ) THEN 1 ELSE 0 END AS active_tombstone
             FROM cards c LEFT JOIN rip_sessions r ON r.id=c.rip_session_id
             LEFT JOIN (SELECT card_id, SUM(amount_delta_cents) AS amount FROM rip_basis_events
                         WHERE target_type='CARD' GROUP BY card_id) rb ON rb.card_id=c.id
             LEFT JOIN (SELECT target_id, SUM(amount_delta_cents) AS amount FROM economic_event_entries
                         WHERE entry_type='BASIS' AND target_type='CARD' GROUP BY target_id) eb ON eb.target_id=c.id
            WHERE c.batch_id=? ORDER BY c.id""",
        (batch_id,),
    ).fetchall()
    rips = db.execute(
        """SELECT r.id, r.rip_code, r.status,
                  COALESCE(rb.amount,0) + COALESCE(eb.amount,0) AS basis_cents
             FROM rip_sessions r
             LEFT JOIN (SELECT rip_session_id, SUM(amount_delta_cents) AS amount FROM rip_basis_events
                         WHERE target_type='BULK' GROUP BY rip_session_id) rb ON rb.rip_session_id=r.id
             LEFT JOIN (SELECT target_id, SUM(amount_delta_cents) AS amount FROM economic_event_entries
                         WHERE entry_type='BASIS' AND target_type='RIP_BULK' GROUP BY target_id) eb ON eb.target_id=r.id
            WHERE r.batch_id=? ORDER BY r.id""",
        (batch_id,),
    ).fetchall()
    units = db.execute(
        """SELECT su.id, su.unit_code, su.unit_sequence, su.status,
                  su.basis_cents + COALESCE(eb.amount,0) AS basis_cents,
                  CASE WHEN EXISTS (
                      SELECT 1 FROM economic_tombstones et
                      JOIN economic_events e ON e.event_id=et.event_id
                      LEFT JOIN economic_events er ON er.reverses_event_id=e.event_id
                      WHERE et.entity_type='SEALED_UNIT' AND et.entity_id=su.id AND er.event_id IS NULL
                  ) THEN 1 ELSE 0 END AS active_tombstone
             FROM sealed_units su
             LEFT JOIN (SELECT target_id, SUM(amount_delta_cents) AS amount FROM economic_event_entries
                         WHERE entry_type='BASIS' AND target_type='SEALED_UNIT' GROUP BY target_id) eb ON eb.target_id=su.id
            WHERE su.batch_id=? ORDER BY su.unit_sequence""",
        (batch_id,),
    ).fetchall()
    event_ids = [
        row[0]
        for row in db.execute(
            "SELECT event_id FROM economic_events WHERE batch_id=? ORDER BY recorded_at DESC, event_id DESC",
            (batch_id,),
        ).fetchall()
    ]
    original = int(batch["final_usd_paid_cents"])
    corrected = current_acquisition_cost_cents(db, batch_id)
    return {
        "calculation_version": CALCULATION_VERSION,
        "batch_id": batch_id,
        "batch_code": batch["batch_code"],
        "economics_mode": batch["economics_mode"],
        "economics_status": batch["economics_status"],
        "acquisition_cost": {
            "preserved_source_cents": original,
            "correction_delta_cents": corrected - original,
            "current_authoritative_cents": corrected,
        },
        "operational_loss_cents": current_operational_loss_cents(db, batch_id),
        "cards": [{**dict(row), "active_tombstone": bool(row["active_tombstone"])} for row in cards],
        "bulk_targets": [
            {
                **dict(row),
            }
            for row in rips
            if row["status"] == "FINALIZED"
        ],
        "sealed_units": [
            {
                **dict(row),
                "active_tombstone": bool(row["active_tombstone"]),
            }
            for row in units
        ],
        "events": [event_payload(db, event_id) for event_id in event_ids],
        "rules": {
            "append_only": True,
            "source_facts_preserved": True,
            "reversals_are_linked_inverse_events": True,
            "tax_accounting": False,
        },
    }


def card_has_economic_history(db: sqlite3.Connection, card_id: int) -> bool:
    return bool(
        db.execute(
            "SELECT 1 FROM rip_basis_events WHERE card_id=? LIMIT 1", (card_id,)
        ).fetchone()
        or db.execute(
            "SELECT 1 FROM economic_tombstones WHERE entity_type='CARD' AND entity_id=? LIMIT 1",
            (card_id,),
        ).fetchone()
        or db.execute(
            "SELECT 1 FROM economic_event_entries WHERE target_type='CARD' AND target_id=? LIMIT 1",
            (card_id,),
        ).fetchone()
    )
