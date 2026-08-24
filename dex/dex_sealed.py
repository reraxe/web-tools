"""Phase 5 exact sealed-unit inventory and sealed-only outbound economics."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from dex_economics import CALCULATION_VERSION, allocate_cents
from dex_corrections import current_acquisition_cost_cents, current_sealed_basis_cents


SEALED_STATUSES = ("REMAINING", "OPENED", "SOLD", "ADJUSTED")
ADJUSTMENT_REASONS = (
    "COUNT_CORRECTION",
    "DAMAGED",
    "MISSING_LOST",
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
        result = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a whole number") from None
    if result < minimum:
        raise ValueError(f"{label} must be at least {minimum}")
    return result


def cents(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a dollar amount")
    try:
        amount = Decimal(str(value if value not in (None, "") else "0").strip())
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{label} must be a dollar amount") from None
    if not amount.is_finite() or amount.as_tuple().exponent < -2:
        raise ValueError(f"{label} must use no more than two decimal places")
    result = int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if result < 0:
        raise ValueError(f"{label} cannot be negative")
    return result


def _event(
    db: sqlite3.Connection,
    unit_id: int,
    event_type: str,
    from_status: str | None,
    to_status: str,
    request_id: str,
    *,
    rip_session_id: int | None = None,
    order_id: int | None = None,
    reason_code: str = "",
    notes: str = "",
    payload: dict | None = None,
    effective_at: str | None = None,
) -> str:
    now = utcnow()
    event_id = f"SEALED-{uuid.uuid4()}"
    db.execute(
        """INSERT INTO sealed_unit_events
           (event_id, request_id, sealed_unit_id, event_type, from_status, to_status,
            rip_session_id, order_id, reason_code, notes, effective_at, recorded_at, payload)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event_id,
            request_id,
            unit_id,
            event_type,
            from_status,
            to_status,
            rip_session_id,
            order_id,
            reason_code,
            notes,
            effective_at or now,
            now,
            json.dumps(payload or {}, separators=(",", ":"), sort_keys=True),
        ),
    )
    return event_id


def _batch(db: sqlite3.Connection, batch_id: int) -> sqlite3.Row:
    row = db.execute(
        "SELECT * FROM batches WHERE id=? AND recycled_at IS NULL", (batch_id,)
    ).fetchone()
    if not row:
        raise ValueError("Batch not found")
    if row["economics_mode"] != "SEALED_RIP":
        raise ValueError("Sealed units require a sealed-product acquisition batch")
    if row["final_usd_paid_cents"] is None:
        raise ValueError("Trustworthy final USD acquisition cost is required")
    if not row["units_acquired"] or int(row["units_acquired"]) < 1:
        raise ValueError("Trustworthy units acquired is required")
    return row


def synchronize_sealed_units(db: sqlite3.Connection, batch_id: int) -> None:
    """Create/rebuild an unused unit ledger from authoritative batch facts.

    Once a unit has been opened, sold, or adjusted, the acquisition facts are
    economically locked and this function refuses to rewrite unit identity/basis.
    """

    batch = db.execute("SELECT * FROM batches WHERE id=?", (batch_id,)).fetchone()
    if not batch:
        raise ValueError("Batch not found")
    existing = db.execute(
        "SELECT * FROM sealed_units WHERE batch_id=? ORDER BY unit_sequence", (batch_id,)
    ).fetchall()
    used = [row for row in existing if row["status"] != "REMAINING"]
    if used:
        if (
            batch["economics_mode"] != "SEALED_RIP"
            or batch["final_usd_paid_cents"] is None
            or len(existing) != int(batch["units_acquired"] or 0)
            or sum(int(row[0]) for row in db.execute("SELECT basis_cents FROM sealed_units WHERE batch_id=?", (batch_id,)))
            != int(batch["final_usd_paid_cents"])
        ):
            raise ValueError("Acquisition facts are locked after a sealed unit is opened, sold, or adjusted")
        return

    if (
        batch["economics_mode"] != "SEALED_RIP"
        or batch["final_usd_paid_cents"] is None
        or not batch["units_acquired"]
    ):
        if existing:
            ids = [row["id"] for row in existing]
            placeholders = ",".join("?" for _ in ids)
            db.execute(f"DELETE FROM sealed_unit_events WHERE sealed_unit_id IN ({placeholders})", ids)
            db.execute("DELETE FROM sealed_units WHERE batch_id=?", (batch_id,))
        return

    now = utcnow()
    allocations = allocate_cents(
        int(batch["final_usd_paid_cents"]), range(1, int(batch["units_acquired"]) + 1)
    )
    current_by_sequence = {
        row["unit_sequence"]: db.execute("SELECT * FROM sealed_units WHERE id=?", (row["id"],)).fetchone()
        for row in existing
    }
    desired_sequences = {int(item.stable_id) for item in allocations}
    removed = [row for sequence, row in current_by_sequence.items() if sequence not in desired_sequences]
    if removed:
        ids = [row["id"] for row in removed]
        placeholders = ",".join("?" for _ in ids)
        db.execute(f"DELETE FROM sealed_unit_events WHERE sealed_unit_id IN ({placeholders})", ids)
        db.execute(f"DELETE FROM sealed_units WHERE id IN ({placeholders})", ids)
    for allocation in allocations:
        sequence = int(allocation.stable_id)
        current = current_by_sequence.get(sequence)
        if current:
            db.execute(
                "UPDATE sealed_units SET unit_code=?, basis_cents=?, updated_at=? WHERE id=?",
                (f"{batch['batch_code']}-UNIT-{sequence:04d}", allocation.cents, now, current["id"]),
            )
            continue
        cursor = db.execute(
            """INSERT INTO sealed_units
               (unit_code, batch_id, unit_sequence, basis_cents, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                f"{batch['batch_code']}-UNIT-{sequence:04d}",
                batch_id,
                sequence,
                allocation.cents,
                now,
                now,
            ),
        )
        _event(
            db,
            int(cursor.lastrowid),
            "CREATED",
            None,
            "REMAINING",
            f"CREATE-{uuid.uuid4()}",
            reason_code="ACQUISITION_FACTS",
            payload={"basis_cents": allocation.cents, "unit_sequence": sequence},
        )


def acquisition_has_used_units(db: sqlite3.Connection, batch_id: int) -> bool:
    return bool(
        db.execute(
            """SELECT 1 FROM sealed_units su
                 LEFT JOIN sealed_unit_events sue ON sue.sealed_unit_id=su.id
                WHERE su.batch_id=? AND (su.status<>'REMAINING' OR sue.event_type IN ('OPENED','SOLD','ADJUSTED'))
                LIMIT 1""",
            (batch_id,),
        ).fetchone()
    )


def open_units_for_rip(db: sqlite3.Connection, batch_id: int, rip_id: int, quantity: int) -> list[dict]:
    _batch(db, batch_id)
    synchronize_sealed_units(db, batch_id)
    projected = db.execute(
        "SELECT 1 FROM batches WHERE id=? AND acquisition_line_id IS NOT NULL", (batch_id,)
    ).fetchone()
    disposition = "AND intake_disposition='RIP_OPEN'" if projected else ""
    rows = db.execute(
        f"""SELECT * FROM sealed_units
            WHERE batch_id=? AND status='REMAINING' {disposition}
            ORDER BY unit_sequence LIMIT ?""",
        (batch_id, quantity),
    ).fetchall()
    if len(rows) != quantity:
        raise ValueError("Opened units would exceed the acquisition's available sealed units")
    now = utcnow()
    for row in rows:
        changed = db.execute(
            """UPDATE sealed_units SET status='OPENED', rip_session_id=?, updated_at=?
               WHERE id=? AND status='REMAINING'""",
            (rip_id, now, row["id"]),
        )
        if changed.rowcount != 1:
            raise sqlite3.IntegrityError("A sealed unit was claimed by another operation")
        _event(
            db,
            row["id"],
            "OPENED",
            "REMAINING",
            "OPENED",
            f"RIP-OPEN-{rip_id}-{row['id']}",
            rip_session_id=rip_id,
            reason_code="RIP_SESSION",
        )
    return [dict(row) for row in rows]


def rip_unit_basis(db: sqlite3.Connection, rip_id: int) -> tuple[int, int | None, int | None]:
    rows = db.execute(
        "SELECT id, unit_sequence, basis_cents FROM sealed_units WHERE rip_session_id=? AND status='OPENED' ORDER BY unit_sequence",
        (rip_id,),
    ).fetchall()
    if not rows:
        raise ValueError("This rip has no exact sealed units assigned")
    return sum(current_sealed_basis_cents(db, int(row["id"])) for row in rows), rows[0]["unit_sequence"], rows[-1]["unit_sequence"]


def batch_sealed_payload(db: sqlite3.Connection, batch_id: int) -> dict:
    batch = _batch(db, batch_id)
    rows = db.execute(
        "SELECT * FROM sealed_units WHERE batch_id=? ORDER BY unit_sequence", (batch_id,)
    ).fetchall()
    counts = {status: 0 for status in SEALED_STATUSES}
    intake_pending = 0
    for row in rows:
        counts[row["status"]] += 1
        if row["status"] == "REMAINING" and row["intake_disposition"] == "PENDING":
            intake_pending += 1
    acquired = int(batch["units_acquired"])
    accounted = sum(counts.values())
    units = []
    for row in rows:
        item = dict(row)
        item["preserved_source_basis_cents"] = int(row["basis_cents"])
        item["basis_cents"] = current_sealed_basis_cents(db, int(row["id"]))
        units.append(item)
    return {
        "calculation_version": CALCULATION_VERSION,
        "batch_id": batch_id,
        "batch_code": batch["batch_code"],
        "product_name": batch["product_name"] or batch["acquisition_type"],
        "receipt_group_reference": batch["receipt_group_reference"] or "",
        "group_notice": "Informational grouping only. Shared costs are not allocated automatically.",
        "authoritative_cost_cents": current_acquisition_cost_cents(db, batch_id),
        "acquisition_facts_locked": acquisition_has_used_units(db, batch_id),
        "units_acquired": acquired,
        "counts": {
            "remaining": counts["REMAINING"] - intake_pending,
            "opened": counts["OPENED"],
            "sold": counts["SOLD"],
            "corrected_adjusted": counts["ADJUSTED"],
            **({"intake_pending": intake_pending} if intake_pending else {}),
        },
        "reconciliation": {
            "acquired": acquired,
            "accounted": accounted,
            "difference": acquired - accounted,
            "reconciled": acquired == accounted,
        },
        "remaining_basis_cents": sum(
            row["basis_cents"] for row in units
            if row["status"] == "REMAINING" and row["intake_disposition"] in ("LEGACY_AVAILABLE", "KEEP_SEALED")
        ),
        "units": units,
    }


def sealed_inventory_payload(db: sqlite3.Connection) -> dict:
    batch_ids = [
        row[0]
        for row in db.execute(
            """SELECT id FROM batches
               WHERE recycled_at IS NULL AND economics_mode='SEALED_RIP'
                 AND final_usd_paid_cents IS NOT NULL AND units_acquired > 0
               ORDER BY created_at DESC, id DESC"""
        ).fetchall()
    ]
    return {
        "calculation_version": CALCULATION_VERSION,
        "batches": [batch_sealed_payload(db, batch_id) for batch_id in batch_ids],
    }


def _selected_units(db: sqlite3.Connection, payload: dict) -> tuple[sqlite3.Row, list[sqlite3.Row]]:
    batch_id = _integer(payload.get("batch_id"), "Acquisition batch", 1)
    batch = _batch(db, batch_id)
    recorded = db.execute("SELECT COUNT(*) FROM sealed_units WHERE batch_id=?", (batch_id,)).fetchone()[0]
    if recorded != int(batch["units_acquired"]):
        raise ValueError("Sealed unit ledger is incomplete; save the authoritative acquisition facts again")
    requested_ids = payload.get("sealed_unit_ids")
    if requested_ids is not None:
        if not isinstance(requested_ids, list) or not requested_ids:
            raise ValueError("Selected sealed units must be a non-empty list")
        ids = list(dict.fromkeys(_integer(value, "Sealed unit ID", 1) for value in requested_ids))
        placeholders = ",".join("?" for _ in ids)
        rows = db.execute(
            f"SELECT * FROM sealed_units WHERE batch_id=? AND id IN ({placeholders}) ORDER BY unit_sequence",
            [batch_id, *ids],
        ).fetchall()
        if len(rows) != len(ids):
            raise ValueError("One or more selected sealed units do not belong to this batch")
    else:
        quantity = _integer(payload.get("quantity"), "Quantity", 1)
        rows = db.execute(
            """SELECT * FROM sealed_units WHERE batch_id=? AND status='REMAINING'
                 AND intake_disposition IN ('LEGACY_AVAILABLE','KEEP_SEALED')
               ORDER BY unit_sequence LIMIT ?""",
            (batch_id, quantity),
        ).fetchall()
        if len(rows) != quantity:
            raise ValueError("Not enough sealed units remain available")
    unavailable = [
        row["unit_code"] for row in rows
        if row["status"] != "REMAINING"
        or row["intake_disposition"] not in ("LEGACY_AVAILABLE", "KEEP_SEALED")
    ]
    if unavailable:
        raise ValueError("Sealed unit is no longer available: " + ", ".join(unavailable))
    return batch, rows


def sealed_sale_preview(db: sqlite3.Connection, payload: dict) -> dict:
    batch, units = _selected_units(db, payload)
    merchandise = cents(payload.get("merchandise_total"), "Gross merchandise sale")
    shipping = cents(payload.get("shipping_collected"), "Shipping collected")
    fees = cents(payload.get("marketplace_fees"), "Marketplace fees")
    postage = cents(payload.get("actual_postage"), "Actual postage")
    tax = cents(payload.get("marketplace_tax"), "Marketplace-collected sales tax")
    effective_basis = {int(row["id"]): current_sealed_basis_cents(db, int(row["id"])) for row in units}
    sold_basis = sum(effective_basis[int(row["id"])] for row in units)
    net = merchandise + shipping - fees - postage
    line_amounts = {
        int(item.stable_id): item.cents
        for item in allocate_cents(merchandise, [int(row["id"]) for row in units])
    }
    return {
        "calculation_version": CALCULATION_VERSION,
        "order_type": "SEALED",
        "batch_id": batch["id"],
        "batch_code": batch["batch_code"],
        "product_name": batch["product_name"] or batch["acquisition_type"],
        "quantity": len(units),
        "sealed_units": [
            {
                "id": row["id"],
                "unit_code": row["unit_code"],
                "unit_sequence": row["unit_sequence"],
                "basis_cents": effective_basis[int(row["id"])],
                "merchandise_amount_cents": line_amounts[row["id"]],
            }
            for row in units
        ],
        "merchandise_total_cents": merchandise,
        "shipping_collected_cents": shipping,
        "marketplace_fees_cents": fees,
        "actual_postage_cents": postage,
        "marketplace_tax_cents": tax,
        "net_proceeds_cents": net,
        "sold_basis_cents": sold_basis,
        "realized_profit_loss_cents": net - sold_basis,
        "tax_notice": "Marketplace-collected sales tax is excluded from revenue and profit/loss.",
        "packaging_notice": "Packaging and supply costs are separate in this release.",
    }


def sealed_order_payload(db: sqlite3.Connection, order_id: int) -> dict:
    order = db.execute(
        "SELECT * FROM sale_orders WHERE id=? AND order_type='SEALED'", (order_id,)
    ).fetchone()
    if not order:
        raise ValueError("Sealed order not found")
    units = db.execute(
        """SELECT ssi.id AS sale_item_id, ssi.merchandise_amount_cents,
                  ssi.basis_cents, su.id, su.unit_code, su.unit_sequence,
                  su.status, su.current_order_id,
                  ssi.batch_id, b.batch_code, b.product_name
           FROM sealed_sale_items ssi
           JOIN sealed_units su ON su.id=ssi.sealed_unit_id
           JOIN batches b ON b.id=ssi.batch_id
           WHERE ssi.order_id=? ORDER BY su.unit_sequence, su.id""",
        (order_id,),
    ).fetchall()
    merchandise = int(order["merchandise_total_cents"] or 0)
    shipping = int(order["shipping_collected_cents"] or 0)
    fees = int(order["marketplace_fees_cents"] or 0)
    postage = int(order["actual_postage_cents"] or 0)
    basis = sum(int(row["basis_cents"]) for row in units)
    net = merchandise + shipping - fees - postage
    undo_action_id = _sealed_sale_undo_action_id(db, order_id)
    has_post_sale_history = bool(
        db.execute("SELECT 1 FROM post_sale_events WHERE order_id=? LIMIT 1", (order_id,)).fetchone()
    )
    units_restorable = bool(units) and all(
        row["status"] == "SOLD" and row["current_order_id"] == order_id for row in units
    )
    undo_eligible = not order["canceled_at"] and not has_post_sale_history and undo_action_id is not None and units_restorable
    if order["canceled_at"]:
        undo_reason = "This order is already canceled and its history has been retained."
    elif undo_action_id is None:
        undo_reason = "The original sealed-sale activity is not available for Undo."
    elif has_post_sale_history:
        undo_reason = "This order has immutable post-sale history; use linked reversal/correction events."
    elif not units_restorable:
        undo_reason = "One or more exact sealed units are no longer eligible to be restored."
    else:
        undo_reason = "Eligible. Undo will restore these exact sealed units atomically."
    payload = dict(order)
    payload.update(
        {
            "calculation_version": CALCULATION_VERSION,
            "item_count": len(units),
            "sealed_units": [dict(row) for row in units],
            "net_proceeds_cents": net,
            "sold_basis_cents": basis,
            "realized_profit_loss_cents": net - basis,
            "canceled": bool(order["canceled_at"]),
            "undo_eligible": undo_eligible,
            "undo_eligibility_reason": undo_reason,
            "post_sale_event_count": int(db.execute("SELECT COUNT(*) FROM post_sale_events WHERE order_id=?", (order_id,)).fetchone()[0]),
        }
    )
    return payload


def _sealed_sale_undo_action_id(db: sqlite3.Connection, order_id: int) -> int | None:
    actions = db.execute(
        """SELECT id, payload FROM activity_log
             WHERE action_type='SEALED_SALE' AND undone_at IS NULL
             ORDER BY id DESC"""
    ).fetchall()
    for action in actions:
        try:
            payload = json.loads(action["payload"] or "{}")
            if int(payload.get("order_id")) == order_id:
                return int(action["id"])
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    return None


def create_sealed_sale(db: sqlite3.Connection, payload: dict, default_sold_at: str) -> dict:
    request_id = _text(payload.get("request_id"), 100)
    if not request_id:
        raise ValueError("A unique request ID is required")
    duplicate = db.execute(
        "SELECT id, order_type FROM sale_orders WHERE request_id=?", (request_id,)
    ).fetchone()
    if duplicate:
        if duplicate["order_type"] != "SEALED":
            raise ValueError("Request ID already belongs to another order type")
        return sealed_order_payload(db, duplicate["id"])
    platform = _text(payload.get("platform"), 30)
    if platform not in ("eBay", "TCGplayer", "Other"):
        raise ValueError("Choose eBay, TCGplayer, or Other as the marketplace")
    if payload.get("skus"):
        raise ValueError("Card and sealed-product items cannot be combined in one order")
    synchronize_sealed_units(db, _integer(payload.get("batch_id"), "Acquisition batch", 1))
    preview = sealed_sale_preview(db, payload)
    units = preview["sealed_units"]
    cursor = db.execute(
        """INSERT INTO sale_orders
           (platform, order_number, sold_at, subtotal, shipping_collected,
            platform_fees, postage_cost, notes, order_type, request_id,
            merchandise_total_cents, shipping_collected_cents,
            marketplace_fees_cents, actual_postage_cents, marketplace_tax_cents)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'SEALED', ?, ?, ?, ?, ?, ?)""",
        (
            platform,
            _text(payload.get("order_number"), 80),
            _text(payload.get("sold_at"), 30) or default_sold_at,
            preview["merchandise_total_cents"] / 100,
            preview["shipping_collected_cents"] / 100,
            preview["marketplace_fees_cents"] / 100,
            preview["actual_postage_cents"] / 100,
            _text(payload.get("notes"), 500),
            request_id,
            preview["merchandise_total_cents"],
            preview["shipping_collected_cents"],
            preview["marketplace_fees_cents"],
            preview["actual_postage_cents"],
            preview["marketplace_tax_cents"],
        ),
    )
    order_id = int(cursor.lastrowid)
    now = utcnow()
    for unit in units:
        changed = db.execute(
            """UPDATE sealed_units SET status='SOLD', current_order_id=?, updated_at=?
               WHERE id=? AND status='REMAINING'""",
            (order_id, now, unit["id"]),
        )
        if changed.rowcount != 1:
            raise sqlite3.IntegrityError("A sealed unit was opened or sold by another operation")
        db.execute(
            """INSERT INTO sealed_sale_items
               (order_id, sealed_unit_id, batch_id, merchandise_amount_cents, basis_cents)
               VALUES (?, ?, ?, ?, ?)""",
            (
                order_id,
                unit["id"],
                preview["batch_id"],
                unit["merchandise_amount_cents"],
                unit["basis_cents"],
            ),
        )
        _event(
            db,
            unit["id"],
            "SOLD",
            "REMAINING",
            "SOLD",
            f"{request_id}-UNIT-{unit['id']}",
            order_id=order_id,
            reason_code="SEALED_SALE",
            effective_at=_text(payload.get("sold_at"), 30) or default_sold_at,
            payload={"basis_cents": unit["basis_cents"], "merchandise_amount_cents": unit["merchandise_amount_cents"]},
        )
    db.execute(
        """INSERT INTO activity_log (created_at, action_type, description, payload)
           VALUES (?, 'SEALED_SALE', ?, ?)""",
        (
            now,
            f"Completed {platform} sealed order with {len(units)} unit(s)",
            json.dumps(
                {"order_id": order_id, "request_id": request_id, "sealed_unit_ids": [unit["id"] for unit in units]},
                separators=(",", ":"),
                sort_keys=True,
            ),
        ),
    )
    return sealed_order_payload(db, order_id)


def undo_sealed_sale(db: sqlite3.Connection, order_id: int, action_id: int) -> dict:
    order = db.execute(
        "SELECT * FROM sale_orders WHERE id=? AND order_type='SEALED'", (order_id,)
    ).fetchone()
    if not order or order["canceled_at"]:
        raise ValueError("This sealed sale is no longer eligible for Undo")
    units = db.execute(
        """SELECT su.* FROM sealed_units su
           JOIN sealed_sale_items ssi ON ssi.sealed_unit_id=su.id
           WHERE ssi.order_id=? ORDER BY su.id""",
        (order_id,),
    ).fetchall()
    if not units or any(row["status"] != "SOLD" or row["current_order_id"] != order_id for row in units):
        raise ValueError("The exact sealed units are no longer eligible for Undo")
    now = utcnow()
    for row in units:
        changed = db.execute(
            """UPDATE sealed_units SET status='REMAINING', current_order_id=NULL, updated_at=?
               WHERE id=? AND status='SOLD' AND current_order_id=?""",
            (now, row["id"], order_id),
        )
        if changed.rowcount != 1:
            raise sqlite3.IntegrityError("A sealed unit changed while the sale was being undone")
        _event(
            db,
            row["id"],
            "SALE_UNDONE",
            "SOLD",
            "REMAINING",
            f"UNDO-{action_id}-{row['id']}",
            order_id=order_id,
            reason_code="OPERATOR_UNDO",
        )
    db.execute(
        "UPDATE sale_orders SET canceled_at=?, cancellation_reason='OPERATOR_UNDO' WHERE id=? AND canceled_at IS NULL",
        (now, order_id),
    )
    return {"order_id": order_id, "restored_unit_ids": [row["id"] for row in units]}


def undo_specific_sealed_sale(db: sqlite3.Connection, order_id: int) -> dict:
    """Undo one eligible sealed order without affecting a different recent action."""
    order = sealed_order_payload(db, order_id)
    if not order["undo_eligible"]:
        raise ValueError(order["undo_eligibility_reason"])
    action_id = _sealed_sale_undo_action_id(db, order_id)
    if action_id is None:
        raise ValueError("The original sealed-sale activity is not available for Undo.")
    result = undo_sealed_sale(db, order_id, action_id)
    db.execute("UPDATE activity_log SET undone_at=? WHERE id=? AND undone_at IS NULL", (utcnow(), action_id))
    result.update({"undone": f"Sealed order {order_id}", "action_id": action_id})
    return result


def adjust_sealed_unit(db: sqlite3.Connection, unit_id: int, payload: dict) -> dict:
    request_id = _text(payload.get("request_id"), 100)
    if not request_id:
        raise ValueError("A unique request ID is required")
    duplicate = db.execute(
        "SELECT sealed_unit_id FROM sealed_unit_events WHERE request_id=?", (request_id,)
    ).fetchone()
    if duplicate:
        return dict(db.execute("SELECT * FROM sealed_units WHERE id=?", (duplicate[0],)).fetchone())
    reason = _text(payload.get("reason_code"), 40).upper()
    if reason not in ADJUSTMENT_REASONS:
        raise ValueError("Choose a standardized quantity-correction reason")
    notes = _text(payload.get("notes"), 1000)
    if reason in ("ENTRY_ERROR", "OTHER") and not notes:
        raise ValueError("Notes are required for this manual correction")
    row = db.execute("SELECT * FROM sealed_units WHERE id=?", (unit_id,)).fetchone()
    if not row:
        raise ValueError("Sealed unit not found")
    if row["status"] != "REMAINING":
        raise ValueError("Only a remaining sealed unit can be quantity-adjusted")
    now = utcnow()
    changed = db.execute(
        "UPDATE sealed_units SET status='ADJUSTED', updated_at=? WHERE id=? AND status='REMAINING'",
        (now, unit_id),
    )
    if changed.rowcount != 1:
        raise sqlite3.IntegrityError("The sealed unit changed during correction")
    _event(
        db,
        unit_id,
        "ADJUSTED",
        "REMAINING",
        "ADJUSTED",
        request_id,
        reason_code=reason,
        notes=notes,
        effective_at=_text(payload.get("effective_at"), 40) or now,
    )
    db.execute(
        """INSERT INTO activity_log (created_at, action_type, description, payload)
           VALUES (?, 'SEALED_ADJUSTMENT', ?, ?)""",
        (
            now,
            f"Adjusted sealed unit {row['unit_code']} with reason {reason}",
            json.dumps({"unit_id": unit_id, "request_id": request_id, "reason_code": reason}, separators=(",", ":")),
        ),
    )
    return dict(db.execute("SELECT * FROM sealed_units WHERE id=?", (unit_id,)).fetchone())
