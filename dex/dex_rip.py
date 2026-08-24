"""Phase 4 rip-session allocation and immutable cost-basis history."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from dex_economics import CALCULATION_VERSION, allocate_cents
from dex_corrections import current_bulk_basis_cents, current_card_basis_cents, current_sealed_basis_cents
from dex_sealed import open_units_for_rip, rip_unit_basis


CORRECTION_REASONS = (
    "LATE_CARD_ADDITION",
    "BASIS_REALLOCATION",
    "BULK_CORRECTION",
    "ENTRY_ERROR",
    "OTHER",
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _text(value: object, limit: int = 500) -> str:
    return str(value or "").strip()[:limit]


def _integer(value: object, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a whole number")
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a whole number") from None
    if number < minimum:
        raise ValueError(f"{label} must be at least {minimum}")
    return number


def _cents(value: object, label: str, *, signed: bool = False) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a dollar amount")
    try:
        decimal = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{label} must be a dollar amount") from None
    if not decimal.is_finite() or decimal.as_tuple().exponent < -2:
        raise ValueError(f"{label} must use no more than two decimal places")
    cents = int((decimal * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if not signed and cents < 0:
        raise ValueError(f"{label} cannot be negative")
    return cents


def _activity(db: sqlite3.Connection, action: str, description: str, payload: dict) -> None:
    db.execute(
        "INSERT INTO activity_log (created_at, action_type, description, payload) VALUES (?, ?, ?, ?)",
        (utcnow(), action, description, json.dumps(payload, separators=(",", ":"), sort_keys=True)),
    )


def _batch(db: sqlite3.Connection, batch_id: int) -> sqlite3.Row:
    row = db.execute(
        "SELECT * FROM batches WHERE id = ? AND recycled_at IS NULL", (batch_id,)
    ).fetchone()
    if not row:
        raise ValueError("Batch not found")
    return row


def _session(db: sqlite3.Connection, rip_id: int) -> sqlite3.Row:
    row = db.execute(
        """SELECT r.*, b.batch_code, b.product_name, b.status AS batch_status,
                  b.economics_mode, b.economics_status,
                  b.final_usd_paid_cents, b.units_acquired
           FROM rip_sessions r JOIN batches b ON b.id = r.batch_id
           WHERE r.id = ? AND b.recycled_at IS NULL""",
        (rip_id,),
    ).fetchone()
    if not row:
        raise ValueError("Rip session not found")
    return row


def create_rip_session(db: sqlite3.Connection, batch_id: int, payload: dict) -> dict:
    batch = _batch(db, batch_id)
    mode = batch["economics_mode"]
    if mode not in ("SEALED_RIP", "SINGLES_KNOWN_COST", "SINGLES_LUMP_SUM"):
        raise ValueError("Enter authoritative acquisition facts before creating a rip session")
    if batch["final_usd_paid_cents"] is None:
        raise ValueError("Trustworthy final USD acquisition cost is required")
    if mode == "SEALED_RIP":
        if not batch["units_acquired"] or batch["units_acquired"] < 1:
            raise ValueError("Trustworthy units acquired is required")
        units_opened = _integer(payload.get("units_opened"), "Units opened", 1)
        already = db.execute(
            "SELECT COALESCE(SUM(units_opened), 0) FROM rip_sessions WHERE batch_id = ? AND status = 'FINALIZED'",
            (batch_id,),
        ).fetchone()[0]
        pending = db.execute(
            "SELECT COALESCE(SUM(units_opened), 0) FROM rip_sessions WHERE batch_id = ? AND status IN ('DRAFT','ACTIVE')",
            (batch_id,),
        ).fetchone()[0]
        if already + pending + units_opened > batch["units_acquired"]:
            raise ValueError("Opened units would exceed the acquisition's available sealed units")
    else:
        units_opened = 0
        existing = db.execute(
            "SELECT 1 FROM rip_sessions WHERE batch_id = ? LIMIT 1", (batch_id,)
        ).fetchone()
        if existing:
            raise ValueError("Purchased singles use one allocation session per batch")
    now = utcnow()
    temporary = f"PENDING-{uuid.uuid4()}"
    cursor = db.execute(
        "INSERT INTO rip_sessions (rip_code, batch_id, units_opened, created_at) VALUES (?, ?, ?, ?)",
        (temporary, batch_id, units_opened, now),
    )
    rip_code = f"RIP-{cursor.lastrowid:04d}"
    db.execute("UPDATE rip_sessions SET rip_code = ? WHERE id = ?", (rip_code, cursor.lastrowid))
    opened_units: list[dict] = []
    if mode == "SEALED_RIP":
        opened_units = open_units_for_rip(db, batch_id, int(cursor.lastrowid), units_opened)
    _activity(
        db,
        "RIP_CREATE",
        f"Created {rip_code} for {batch['batch_code']}",
        {
            "rip_session_id": cursor.lastrowid,
            "batch_id": batch_id,
            "units_opened": units_opened,
            "sealed_unit_ids": [unit["id"] for unit in opened_units],
        },
    )
    return rip_session_payload(db, cursor.lastrowid)


def active_rip_for_batch(db: sqlite3.Connection, batch_id: int) -> int | None:
    setting = db.execute("SELECT value FROM settings WHERE key = 'active_rip_session_id'").fetchone()
    if not setting or not setting[0]:
        return None
    try:
        rip_id = int(setting[0])
    except ValueError:
        return None
    row = db.execute(
        "SELECT id FROM rip_sessions WHERE id = ? AND batch_id = ? AND status = 'ACTIVE'",
        (rip_id, batch_id),
    ).fetchone()
    return row[0] if row else None


def activate_rip(db: sqlite3.Connection, rip_id: int) -> dict:
    rip = _session(db, rip_id)
    if rip["status"] == "FINALIZED":
        raise ValueError("A finalized rip cannot receive ordinary intake")
    if rip["batch_status"] != "OPEN":
        raise ValueError("Reopen this batch before starting rip scanner intake")
    current = db.execute("SELECT value FROM settings WHERE key = 'active_rip_session_id'").fetchone()
    current_id = int(current[0]) if current and current[0] else None
    if current_id and current_id != rip_id:
        db.execute("UPDATE rip_sessions SET status = 'DRAFT' WHERE id = ? AND status = 'ACTIVE'", (current_id,))
    now = utcnow()
    db.execute("UPDATE rip_sessions SET status = 'ACTIVE', started_at = COALESCE(started_at, ?) WHERE id = ?", (now, rip_id))
    db.execute(
        "INSERT INTO settings (key, value) VALUES ('active_rip_session_id', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(rip_id),),
    )
    _activity(db, "RIP_ACTIVATE", f"Activated {rip['rip_code']} for scanner intake", {"rip_session_id": rip_id, "previous_rip_session_id": current_id})
    return rip_session_payload(db, rip_id)


def deactivate_rip(db: sqlite3.Connection, rip_id: int) -> dict:
    rip = _session(db, rip_id)
    if rip["status"] == "ACTIVE":
        db.execute("UPDATE rip_sessions SET status = 'DRAFT' WHERE id = ?", (rip_id,))
    db.execute("UPDATE settings SET value = '' WHERE key = 'active_rip_session_id' AND value = ?", (str(rip_id),))
    _activity(db, "RIP_DEACTIVATE", f"Stopped scanner intake for {rip['rip_code']}", {"rip_session_id": rip_id})
    return rip_session_payload(db, rip_id)


def _consumed_cost(db: sqlite3.Connection, rip: sqlite3.Row) -> tuple[int, int | None, int | None]:
    total = rip["final_usd_paid_cents"]
    if total is None:
        raise ValueError("Trustworthy final USD acquisition cost is required")
    if rip["economics_mode"] != "SEALED_RIP":
        prior = db.execute(
            "SELECT 1 FROM rip_sessions WHERE batch_id = ? AND status = 'FINALIZED' AND id <> ?",
            (rip["batch_id"], rip["id"]),
        ).fetchone()
        if prior:
            raise ValueError("Purchased singles cost has already been allocated")
        return total, None, None
    return rip_unit_basis(db, rip["id"])


def allocation_preview(db: sqlite3.Connection, rip_id: int, payload: dict | None = None) -> dict:
    payload = payload or {}
    rip = _session(db, rip_id)
    if rip["status"] == "FINALIZED":
        return rip_session_payload(db, rip_id)
    consumed, unit_start, unit_end = _consumed_cost(db, rip)
    cards = db.execute(
        "SELECT id, sku, name, recycled_at FROM cards WHERE rip_session_id = ? ORDER BY id",
        (rip_id,),
    ).fetchall()
    method = _text(payload.get("allocation_method") or ("MANUAL" if rip["economics_mode"] == "SINGLES_KNOWN_COST" else "EQUAL"), 20).upper()
    if method not in ("EQUAL", "MANUAL"):
        raise ValueError("Allocation method must be Equal or Manual")
    bulk_mode = _text(payload.get("bulk_mode") or "NONE", 30).upper()
    if bulk_mode not in ("NONE", "KNOWN_QUANTITY", "MANUAL_RESERVE"):
        raise ValueError("Choose no bulk, known bulk quantity, or manual bulk reserve")
    bulk_quantity = None
    bulk_basis = 0
    reserve = None
    if bulk_mode == "KNOWN_QUANTITY":
        bulk_quantity = _integer(payload.get("bulk_quantity"), "Bulk card quantity", 1)
    elif bulk_mode == "MANUAL_RESERVE":
        reserve_input = payload.get("bulk_reserve")
        if reserve_input is None or not str(reserve_input).strip():
            raise ValueError("Unknown-quantity bulk requires an explicit manual reserve amount")
        reserve = _cents(reserve_input, "Manual bulk reserve")
        if reserve <= 0:
            raise ValueError("Unknown-quantity bulk requires an explicit reserve greater than $0.00")
        if reserve > consumed:
            raise ValueError("Bulk reserve cannot exceed the rip cost")

    card_basis: dict[int, int] = {}
    if method == "MANUAL":
        raw = payload.get("card_overrides", [])
        if not isinstance(raw, list):
            raise ValueError("Manual card costs must be a list")
        supplied: dict[str, int] = {}
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError("Each manual card cost must identify a SKU")
            sku = _text(item.get("sku"), 60).upper()
            if not sku or sku in supplied:
                raise ValueError("Manual card costs require unique SKUs")
            supplied[sku] = _cents(item.get("basis"), f"Basis for {sku}")
        expected = {row["sku"] for row in cards}
        if set(supplied) != expected:
            raise ValueError("Manual allocation requires an explicit cost for every participating scanned card")
        card_basis = {row["id"]: supplied[row["sku"]] for row in cards}
        bulk_basis = reserve or 0
        if bulk_mode == "KNOWN_QUANTITY":
            bulk_basis = _cents(payload.get("bulk_reserve", ""), "Known-bulk basis")
    else:
        if bulk_mode == "MANUAL_RESERVE":
            bulk_basis = reserve or 0
            available = consumed - bulk_basis
            allocations = allocate_cents(available, [f"CARD:{row['id']:020d}" for row in cards])
        else:
            recipients = [f"CARD:{row['id']:020d}" for row in cards]
            if bulk_quantity:
                recipients.extend(f"BULK:{rip_id:020d}:{index:020d}" for index in range(1, bulk_quantity + 1))
            allocations = allocate_cents(consumed, recipients)
            bulk_basis = sum(item.cents for item in allocations if str(item.stable_id).startswith("BULK:"))
        by_key = {str(item.stable_id): item.cents for item in allocations}
        card_basis = {row["id"]: by_key[f"CARD:{row['id']:020d}"] for row in cards}

    scanned = sum(card_basis.values())
    allocated = scanned + bulk_basis
    difference = consumed - allocated
    return {
        "calculation_version": CALCULATION_VERSION,
        "rip_session_id": rip_id,
        "rip_code": rip["rip_code"],
        "status": rip["status"],
        "allocation_method": method,
        "bulk_mode": bulk_mode,
        "bulk_quantity": bulk_quantity,
        "valuation_complete": bulk_mode != "MANUAL_RESERVE",
        "unit_sequence_start": unit_start,
        "unit_sequence_end": unit_end,
        "reconciliation": {
            "rip_cost_cents": consumed,
            "scanned_card_basis_cents": scanned,
            "bulk_reserve_basis_cents": bulk_basis,
            "total_allocated_cents": allocated,
            "difference_cents": difference,
        },
        "cards": [
            {
                "id": row["id"],
                "sku": row["sku"],
                "name": row["name"],
                "recycled_at": row["recycled_at"],
                "basis_cents": card_basis[row["id"]],
            }
            for row in cards
        ],
        "confirmation_required": True,
    }


def finalize_rip(db: sqlite3.Connection, rip_id: int, payload: dict) -> dict:
    rip = _session(db, rip_id)
    if rip["status"] == "FINALIZED":
        raise ValueError("Rip session is already finalized")
    if not payload.get("confirm_all_cards_accounted"):
        raise ValueError("Confirm that every intended scanned or bulk card is accounted for")
    if not payload.get("confirm_finalization"):
        raise ValueError("Final allocation confirmation is required")
    linked = db.execute(
        """SELECT l.id,l.quantity,l.product_class
             FROM batches b JOIN acquisition_lines l ON l.id=b.acquisition_line_id
            WHERE b.id=?""",
        (rip["batch_id"],),
    ).fetchone()
    if linked and linked["product_class"] == "SINGLE_CARDS":
        routed = int(db.execute(
            """SELECT COALESCE(SUM(quantity),0)
                 FROM acquisition_intake_route_events
                WHERE acquisition_line_id=? AND route_action='SCAN_IDENTIFY'""",
            (linked["id"],),
        ).fetchone()[0])
        if routed != int(linked["quantity"]):
            raise ValueError(
                "Finish routing this singles acquisition line before finalizing its full cost allocation"
            )
    request_id = _text(payload.get("request_id"), 100)
    if not request_id:
        raise ValueError("A unique request ID is required")
    duplicate = db.execute("SELECT rip_session_id FROM rip_economic_events WHERE request_id = ?", (request_id,)).fetchone()
    if duplicate:
        return rip_session_payload(db, duplicate[0])
    preview = allocation_preview(db, rip_id, payload)
    if preview["reconciliation"]["difference_cents"] != 0:
        raise ValueError("Allocation must reconcile to an exact $0.00 difference")
    now = utcnow()
    event_id = f"ECO-{uuid.uuid4()}"
    db.execute(
        """INSERT INTO rip_economic_events
           (event_id, request_id, rip_session_id, event_type, effective_at, recorded_at, reason_code, notes, payload)
           VALUES (?, ?, ?, 'FINALIZATION', ?, ?, 'RIP_FINALIZED', ?, ?)""",
        (event_id, request_id, rip_id, _text(payload.get("effective_at"), 40) or now, now, _text(payload.get("notes")), json.dumps(preview, separators=(",", ":"), sort_keys=True)),
    )
    for card in preview["cards"]:
        db.execute(
            "INSERT INTO rip_basis_events (event_id, rip_session_id, target_type, card_id, amount_delta_cents, created_at) VALUES (?, ?, 'CARD', ?, ?, ?)",
            (event_id, rip_id, card["id"], card["basis_cents"], now),
        )
    if preview["reconciliation"]["bulk_reserve_basis_cents"]:
        db.execute(
            "INSERT INTO rip_basis_events (event_id, rip_session_id, target_type, card_id, amount_delta_cents, created_at) VALUES (?, ?, 'BULK', NULL, ?, ?)",
            (event_id, rip_id, preview["reconciliation"]["bulk_reserve_basis_cents"], now),
        )
    rec = preview["reconciliation"]
    db.execute(
        """UPDATE rip_sessions SET status='FINALIZED', allocation_method=?, bulk_mode=?, bulk_quantity=?,
           consumed_cost_cents=?, scanned_basis_cents=?, bulk_basis_cents=?, total_allocated_cents=?,
           difference_cents=?, valuation_complete=?, cards_accounted_confirmed=1,
           unit_sequence_start=?, unit_sequence_end=?, finalized_at=? WHERE id=?""",
        (preview["allocation_method"], preview["bulk_mode"], preview["bulk_quantity"], rec["rip_cost_cents"], rec["scanned_card_basis_cents"], rec["bulk_reserve_basis_cents"], rec["total_allocated_cents"], rec["difference_cents"], 1 if preview["valuation_complete"] else 0, preview["unit_sequence_start"], preview["unit_sequence_end"], now, rip_id),
    )
    db.execute("UPDATE batches SET economics_status='FINALIZED' WHERE id=?", (rip["batch_id"],))
    db.execute("UPDATE settings SET value='' WHERE key='active_rip_session_id' AND value=?", (str(rip_id),))
    _activity(db, "RIP_FINALIZE", f"Finalized {rip['rip_code']} with exact cost reconciliation", {"event_id": event_id, "request_id": request_id, "rip_session_id": rip_id, "reconciliation": rec})
    return rip_session_payload(db, rip_id)


def correct_rip(db: sqlite3.Connection, rip_id: int, payload: dict) -> dict:
    rip = _session(db, rip_id)
    if rip["status"] != "FINALIZED":
        raise ValueError("Corrections apply only after finalization")
    request_id = _text(payload.get("request_id"), 100)
    if not request_id:
        raise ValueError("A unique request ID is required")
    duplicate = db.execute("SELECT rip_session_id FROM rip_economic_events WHERE request_id=?", (request_id,)).fetchone()
    if duplicate:
        return rip_session_payload(db, duplicate[0])
    reason = _text(payload.get("reason_code"), 40).upper()
    notes = _text(payload.get("notes"), 1000)
    if reason not in CORRECTION_REASONS:
        raise ValueError("Choose a standardized correction reason")
    if not notes:
        raise ValueError("Correction notes are required")
    raw = payload.get("card_adjustments", [])
    if not isinstance(raw, list):
        raise ValueError("Card adjustments must be a list")
    adjustments: list[tuple[sqlite3.Row, int]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Each correction must identify a card")
        sku = _text(item.get("sku"), 60).upper()
        if not sku or sku in seen:
            raise ValueError("Correction SKUs must be unique")
        seen.add(sku)
        card = db.execute("SELECT * FROM cards WHERE sku=? AND batch_id=? AND recycled_at IS NULL", (sku, rip["batch_id"])).fetchone()
        if not card:
            raise ValueError(f"Card {sku} is not active in this acquisition batch")
        if card["rip_session_id"] not in (None, rip_id):
            raise ValueError(f"Card {sku} already belongs to another rip session")
        delta = _cents(item.get("delta"), f"Basis change for {sku}", signed=True)
        current = db.execute("SELECT COALESCE(SUM(amount_delta_cents),0) FROM rip_basis_events WHERE target_type='CARD' AND card_id=?", (card["id"],)).fetchone()[0]
        if current + delta < 0:
            raise ValueError(f"Correction would make {sku} basis negative")
        adjustments.append((card, delta))
    bulk_delta = _cents(payload.get("bulk_delta", "0"), "Bulk reserve change", signed=True)
    current_bulk = db.execute("SELECT COALESCE(SUM(amount_delta_cents),0) FROM rip_basis_events WHERE rip_session_id=? AND target_type='BULK'", (rip_id,)).fetchone()[0]
    if current_bulk + bulk_delta < 0:
        raise ValueError("Correction would make the bulk reserve negative")
    if sum(delta for _, delta in adjustments) + bulk_delta != 0:
        raise ValueError("Correction card changes plus bulk change must equal exactly $0.00")
    if not any(delta for _, delta in adjustments) and bulk_delta == 0:
        raise ValueError("Enter at least one economic correction")
    now = utcnow()
    event_id = f"ECO-{uuid.uuid4()}"
    event_payload = {"cards": [{"sku": card["sku"], "delta_cents": delta} for card, delta in adjustments], "bulk_delta_cents": bulk_delta}
    db.execute(
        """INSERT INTO rip_economic_events
           (event_id, request_id, rip_session_id, event_type, effective_at, recorded_at, reason_code, notes, payload)
           VALUES (?, ?, ?, 'CORRECTION', ?, ?, ?, ?, ?)""",
        (event_id, request_id, rip_id, _text(payload.get("effective_at"), 40) or now, now, reason, notes, json.dumps(event_payload, separators=(",", ":"), sort_keys=True)),
    )
    for card, delta in adjustments:
        if card["rip_session_id"] is None:
            db.execute("UPDATE cards SET rip_session_id=?, updated_at=? WHERE id=?", (rip_id, now, card["id"]))
        db.execute("INSERT INTO rip_basis_events (event_id, rip_session_id, target_type, card_id, amount_delta_cents, created_at) VALUES (?, ?, 'CARD', ?, ?, ?)", (event_id, rip_id, card["id"], delta, now))
    if bulk_delta:
        db.execute("INSERT INTO rip_basis_events (event_id, rip_session_id, target_type, card_id, amount_delta_cents, created_at) VALUES (?, ?, 'BULK', NULL, ?, ?)", (event_id, rip_id, bulk_delta, now))
    _activity(db, "RIP_CORRECTION", f"Recorded audited correction for {rip['rip_code']}", {"event_id": event_id, "request_id": request_id, "reason_code": reason, **event_payload})
    return rip_session_payload(db, rip_id)


def rip_session_payload(db: sqlite3.Connection, rip_id: int) -> dict:
    rip = _session(db, rip_id)
    cards = db.execute(
        """SELECT c.id, c.sku, c.name, c.recycled_at
           FROM cards c WHERE c.rip_session_id=? ORDER BY c.id""",
        (rip_id,),
    ).fetchall()
    card_payloads = [
        {**dict(row), "basis_cents": current_card_basis_cents(db, int(row["id"]))}
        for row in cards
    ]
    events = db.execute(
        "SELECT event_id, request_id, event_type, effective_at, recorded_at, reason_code, notes FROM rip_economic_events WHERE rip_session_id=? ORDER BY recorded_at, event_id",
        (rip_id,),
    ).fetchall()
    active = active_rip_for_batch(db, rip["batch_id"]) == rip_id
    current_bulk = current_bulk_basis_cents(db, rip_id)
    current_scanned = sum(row["basis_cents"] for row in card_payloads)
    sealed_units = db.execute(
        """SELECT id, unit_code, unit_sequence, basis_cents, status
           FROM sealed_units WHERE rip_session_id=? ORDER BY unit_sequence""",
        (rip_id,),
    ).fetchall()
    return {
        "calculation_version": CALCULATION_VERSION,
        "id": rip["id"], "rip_code": rip["rip_code"], "batch_id": rip["batch_id"],
        "batch_code": rip["batch_code"], "product_name": rip["product_name"],
        "status": rip["status"], "active_for_intake": active, "units_opened": rip["units_opened"],
        "allocation_method": rip["allocation_method"], "bulk_mode": rip["bulk_mode"],
        "bulk_quantity": rip["bulk_quantity"], "valuation_complete": bool(rip["valuation_complete"]),
        "created_at": rip["created_at"], "started_at": rip["started_at"], "finalized_at": rip["finalized_at"],
        "reconciliation": {
            "rip_cost_cents": rip["consumed_cost_cents"], "scanned_card_basis_cents": current_scanned,
            "bulk_reserve_basis_cents": current_bulk,
            "total_allocated_cents": current_scanned + current_bulk,
            "difference_cents": None if rip["consumed_cost_cents"] is None else rip["consumed_cost_cents"] - current_scanned - current_bulk,
        },
        "unit_sequence_start": rip["unit_sequence_start"], "unit_sequence_end": rip["unit_sequence_end"],
        "cards": card_payloads, "events": [dict(row) for row in events],
        "sealed_units": [
            {**dict(row), "basis_cents": current_sealed_basis_cents(db, int(row["id"]))}
            for row in sealed_units
        ],
    }


def batch_rips_payload(db: sqlite3.Connection, batch_id: int) -> dict:
    batch = _batch(db, batch_id)
    rows = db.execute("SELECT id FROM rip_sessions WHERE batch_id=? ORDER BY id", (batch_id,)).fetchall()
    active_setting = db.execute("SELECT value FROM settings WHERE key='active_rip_session_id'").fetchone()
    active = None
    if active_setting and active_setting[0]:
        active_row = db.execute(
            """SELECT r.id, r.rip_code, r.batch_id, b.product_name
               FROM rip_sessions r JOIN batches b ON b.id=r.batch_id
               WHERE r.id=? AND r.status='ACTIVE'""", (int(active_setting[0]),)
        ).fetchone()
        active = dict(active_row) if active_row else None
    return {
        "calculation_version": CALCULATION_VERSION,
        "batch_id": batch_id,
        "economics_mode": batch["economics_mode"],
        "active_intake": active,
        "sessions": [rip_session_payload(db, row["id"]) for row in rows],
    }
