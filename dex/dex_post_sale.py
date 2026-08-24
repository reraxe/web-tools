"""Phase 7B immutable post-sale financial events and exact returns."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from dex_corrections import current_card_basis_cents, current_sealed_basis_cents
from dex_economics import CALCULATION_VERSION


REFUND_REASONS = {"CUSTOMER_REQUEST", "ORDER_CANCELLATION", "SERVICE_RECOVERY", "OTHER"}
RETURN_REASONS = {"CUSTOMER_RETURN", "ORDER_CANCELLATION", "OTHER"}
CHARGEBACK_REASONS = {"PAYMENT_DISPUTE", "FRAUD", "PROCESSING_ERROR", "OTHER"}
FEE_CREDIT_REASONS = {"MARKETPLACE_CREDIT", "FEE_REVERSAL", "OTHER"}
POSTAGE_REASONS = {"CARRIER_REFUND", "VOIDED_LABEL", "OTHER"}
CORRECTION_REASONS = {"DATA_ENTRY_ERROR", "MARKETPLACE_ADJUSTMENT", "OTHER"}
RETURN_OUTCOMES = {"RESTOCKED", "DAMAGED_EXCLUDED"}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _text(value: object, limit: int = 1000) -> str:
    return str(value or "").strip()[:limit]


def _money(value: object, label: str, *, signed: bool = False) -> int:
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


def _order(db: sqlite3.Connection, order_id: int) -> sqlite3.Row:
    row = db.execute("SELECT * FROM sale_orders WHERE id=?", (order_id,)).fetchone()
    if not row:
        raise ValueError("Sale order not found")
    if row["canceled_at"]:
        raise ValueError("Canceled orders cannot receive post-sale events")
    return row


def _original_financials(order: sqlite3.Row) -> dict[str, int]:
    def cents(exact: str, legacy: str) -> int:
        if exact in order.keys() and order[exact] is not None:
            return int(order[exact])
        return int((Decimal(str(order[legacy] or 0)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    return {
        "merchandise_cents": cents("merchandise_total_cents", "subtotal"),
        "shipping_cents": cents("shipping_collected_cents", "shipping_collected"),
        "marketplace_fees_cents": cents("marketplace_fees_cents", "platform_fees"),
        "postage_cents": cents("actual_postage_cents", "postage_cost"),
        "other_net_cents": 0,
    }


def financial_facts(db: sqlite3.Connection, order_id: int) -> dict:
    order = db.execute("SELECT * FROM sale_orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        raise ValueError("Sale order not found")
    original = _original_financials(order)
    deltas = {key: 0 for key in original}
    component_keys = {
        "MERCHANDISE": "merchandise_cents",
        "SHIPPING": "shipping_cents",
        "MARKETPLACE_FEES": "marketplace_fees_cents",
        "POSTAGE": "postage_cents",
        "OTHER_NET": "other_net_cents",
    }
    has_ledger = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='post_sale_event_entries'"
    ).fetchone()
    if has_ledger:
        for row in db.execute(
            """SELECT pe.component_type, COALESCE(SUM(pe.amount_delta_cents),0) AS delta
                 FROM post_sale_event_entries pe
                 JOIN post_sale_events e ON e.event_id=pe.event_id
                WHERE e.order_id=? GROUP BY pe.component_type""",
            (order_id,),
        ).fetchall():
            deltas[component_keys[row["component_type"]]] = int(row["delta"] or 0)
    effective = {key: original[key] + deltas[key] for key in original}
    original_net = (
        original["merchandise_cents"] + original["shipping_cents"]
        - original["marketplace_fees_cents"] - original["postage_cents"]
    )
    effective_net = (
        effective["merchandise_cents"] + effective["shipping_cents"]
        - effective["marketplace_fees_cents"] - effective["postage_cents"]
        + effective["other_net_cents"]
    )
    return {
        "original": {**original, "net_proceeds_cents": original_net},
        "deltas": deltas,
        "effective": {**effective, "net_proceeds_cents": effective_net},
    }


def _request(db: sqlite3.Connection, payload: dict) -> tuple[str, dict | None]:
    request_id = _text(payload.get("request_id"), 100)
    if not request_id:
        raise ValueError("A unique request ID is required")
    duplicate = db.execute(
        "SELECT event_id FROM post_sale_events WHERE request_id=?", (request_id,)
    ).fetchone()
    return request_id, event_payload(db, duplicate[0]) if duplicate else None


def _reason(payload: dict, allowed: set[str], label: str, *, notes_required: bool = False) -> tuple[str, str]:
    reason = _text(payload.get("reason_code"), 50).upper()
    if reason not in allowed:
        raise ValueError(f"Choose a standardized {label} reason")
    notes = _text(payload.get("notes"), 1000)
    if notes_required or reason == "OTHER":
        if not notes:
            raise ValueError("Notes are required for this material event")
    return reason, notes


def _insert_event(
    db: sqlite3.Connection,
    *,
    request_id: str,
    order_id: int,
    event_type: str,
    reason_code: str,
    notes: str,
    entries: list[tuple[str, int]],
    payload: dict,
    effective_at: str | None = None,
    reverses_event_id: str | None = None,
) -> dict:
    now = utcnow()
    event_id = f"SALE7B-{uuid.uuid4()}"
    db.execute(
        """INSERT INTO post_sale_events
           (event_id, request_id, order_id, event_type, reason_code, effective_at,
            recorded_at, notes, reverses_event_id, payload)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event_id, request_id, order_id, event_type, reason_code,
            effective_at or now, now, notes, reverses_event_id,
            json.dumps(payload, separators=(",", ":"), sort_keys=True),
        ),
    )
    for component, amount in entries:
        if amount:
            db.execute(
                """INSERT INTO post_sale_event_entries
                   (event_id, component_type, amount_delta_cents, created_at)
                   VALUES (?, ?, ?, ?)""",
                (event_id, component, int(amount), now),
            )
    db.execute(
        """INSERT INTO activity_log (created_at, action_type, description, payload)
           VALUES (?, 'POST_SALE_EVENT', ?, ?)""",
        (
            now,
            f"Recorded {event_type.replace('_', ' ').lower()} ({event_id})",
            json.dumps({"event_id": event_id, "order_id": order_id, "event_type": event_type}, separators=(",", ":")),
        ),
    )
    return event_payload(db, event_id)


def event_payload(db: sqlite3.Connection, event_id: str) -> dict:
    row = db.execute("SELECT * FROM post_sale_events WHERE event_id=?", (event_id,)).fetchone()
    if not row:
        raise ValueError("Post-sale event not found")
    reversal = db.execute(
        "SELECT event_id, recorded_at FROM post_sale_events WHERE reverses_event_id=?", (event_id,)
    ).fetchone()
    result = dict(row)
    result["payload"] = json.loads(row["payload"] or "{}")
    result["entries"] = [
        dict(item) for item in db.execute(
            "SELECT component_type, amount_delta_cents FROM post_sale_event_entries WHERE event_id=? ORDER BY id",
            (event_id,),
        ).fetchall()
    ]
    result["return_items"] = [
        {**dict(item), "prior_state": json.loads(item["prior_state"] or "{}")}
        for item in db.execute(
            """SELECT item_type, sale_item_id, entity_id, stable_identifier, outcome,
                      basis_cents, prior_state, restored_at
                 FROM post_sale_return_items WHERE event_id=? ORDER BY id""",
            (event_id,),
        ).fetchall()
    ]
    result["calculation_version"] = CALCULATION_VERSION
    result["reversed"] = reversal is not None
    result["reversed_by_event_id"] = reversal["event_id"] if reversal else None
    result["reversible"] = row["event_type"] != "REVERSAL" and reversal is None
    return result


def create_refund(db: sqlite3.Connection, order_id: int, payload: dict, *, full: bool = False) -> dict:
    request_id, duplicate = _request(db, payload)
    if duplicate:
        return duplicate
    _order(db, order_id)
    reason, notes = _reason(payload, REFUND_REASONS, "refund")
    facts = financial_facts(db, order_id)
    remaining_merchandise = facts["effective"]["merchandise_cents"]
    remaining_shipping = facts["effective"]["shipping_cents"]
    if full:
        merchandise, shipping = remaining_merchandise, remaining_shipping
        event_type = "FULL_REFUND"
    else:
        merchandise = _money(payload.get("merchandise_amount", 0), "Merchandise refund")
        shipping = _money(payload.get("shipping_amount", 0), "Shipping refund")
        event_type = "PARTIAL_REFUND"
    if merchandise + shipping <= 0:
        raise ValueError("Refund amount must be greater than $0.00")
    if merchandise > remaining_merchandise or shipping > remaining_shipping:
        raise ValueError("Refund exceeds the remaining refundable merchandise or shipping amount")
    return _insert_event(
        db, request_id=request_id, order_id=order_id, event_type=event_type,
        reason_code=reason, notes=notes,
        entries=[("MERCHANDISE", -merchandise), ("SHIPPING", -shipping)],
        payload={"merchandise_refund_cents": merchandise, "shipping_refund_cents": shipping},
        effective_at=_text(payload.get("effective_at"), 40) or None,
    )


def create_chargeback(db: sqlite3.Connection, order_id: int, payload: dict) -> dict:
    request_id, duplicate = _request(db, payload)
    if duplicate:
        return duplicate
    _order(db, order_id)
    reason, notes = _reason(payload, CHARGEBACK_REASONS, "chargeback")
    amount = _money(payload.get("amount"), "Chargeback")
    if amount <= 0:
        raise ValueError("Chargeback must be greater than $0.00")
    return _insert_event(
        db, request_id=request_id, order_id=order_id, event_type="CHARGEBACK",
        reason_code=reason, notes=notes, entries=[("OTHER_NET", -amount)],
        payload={"chargeback_cents": amount}, effective_at=_text(payload.get("effective_at"), 40) or None,
    )


def create_fee_credit(db: sqlite3.Connection, order_id: int, payload: dict) -> dict:
    request_id, duplicate = _request(db, payload)
    if duplicate:
        return duplicate
    _order(db, order_id)
    reason, notes = _reason(payload, FEE_CREDIT_REASONS, "fee-credit")
    amount = _money(payload.get("amount"), "Marketplace fee credit")
    facts = financial_facts(db, order_id)
    if amount <= 0 or amount > facts["effective"]["marketplace_fees_cents"]:
        raise ValueError("Fee credit must be positive and cannot exceed remaining marketplace fees")
    return _insert_event(
        db, request_id=request_id, order_id=order_id, event_type="MARKETPLACE_FEE_CREDIT",
        reason_code=reason, notes=notes, entries=[("MARKETPLACE_FEES", -amount)],
        payload={"fee_credit_cents": amount}, effective_at=_text(payload.get("effective_at"), 40) or None,
    )


def create_postage_refund(db: sqlite3.Connection, order_id: int, payload: dict) -> dict:
    request_id, duplicate = _request(db, payload)
    if duplicate:
        return duplicate
    _order(db, order_id)
    reason, notes = _reason(payload, POSTAGE_REASONS, "postage-refund")
    amount = _money(payload.get("amount"), "Postage refund")
    facts = financial_facts(db, order_id)
    if amount <= 0 or amount > facts["effective"]["postage_cents"]:
        raise ValueError("Postage refund must be positive and cannot exceed remaining postage")
    return _insert_event(
        db, request_id=request_id, order_id=order_id, event_type="POSTAGE_REFUND",
        reason_code=reason, notes=notes, entries=[("POSTAGE", -amount)],
        payload={"postage_refund_cents": amount}, effective_at=_text(payload.get("effective_at"), 40) or None,
    )


def create_sale_correction(db: sqlite3.Connection, order_id: int, payload: dict) -> dict:
    request_id, duplicate = _request(db, payload)
    if duplicate:
        return duplicate
    _order(db, order_id)
    reason, notes = _reason(payload, CORRECTION_REASONS, "sale-correction", notes_required=True)
    input_fields = {
        "MERCHANDISE": ("merchandise_delta", "Merchandise correction"),
        "SHIPPING": ("shipping_delta", "Shipping correction"),
        "MARKETPLACE_FEES": ("marketplace_fees_delta", "Marketplace fee correction"),
        "POSTAGE": ("postage_delta", "Postage correction"),
        "OTHER_NET": ("other_net_delta", "Other proceeds correction"),
    }
    entries = [(component, _money(payload.get(field, 0), label, signed=True)) for component, (field, label) in input_fields.items()]
    if not any(amount for _, amount in entries):
        raise ValueError("At least one non-zero sale correction is required")
    facts = financial_facts(db, order_id)
    effective = facts["effective"]
    key_map = {
        "MERCHANDISE": "merchandise_cents", "SHIPPING": "shipping_cents",
        "MARKETPLACE_FEES": "marketplace_fees_cents", "POSTAGE": "postage_cents",
    }
    for component, amount in entries:
        if component in key_map and effective[key_map[component]] + amount < 0:
            raise ValueError("Correction would make a recorded sale component negative")
    return _insert_event(
        db, request_id=request_id, order_id=order_id, event_type="SALE_CORRECTION",
        reason_code=reason, notes=notes, entries=entries,
        payload={"component_deltas_cents": {component: amount for component, amount in entries if amount}},
        effective_at=_text(payload.get("effective_at"), 40) or None,
    )


def _active_return(db: sqlite3.Connection, item_type: str, sale_item_id: int) -> sqlite3.Row | None:
    return db.execute(
        """SELECT ri.*, e.order_id, e.event_id
             FROM post_sale_return_items ri
             JOIN post_sale_events e ON e.event_id=ri.event_id
             LEFT JOIN post_sale_events reversal ON reversal.reverses_event_id=e.event_id
            WHERE ri.item_type=? AND ri.sale_item_id=? AND reversal.event_id IS NULL
            ORDER BY ri.id DESC LIMIT 1""",
        (item_type, sale_item_id),
    ).fetchone()


def active_returned_sale_items(db: sqlite3.Connection, order_ids: set[int]) -> dict[tuple[str, int], dict]:
    if not order_ids:
        return {}
    placeholders = ",".join("?" for _ in order_ids)
    rows = db.execute(
        f"""SELECT ri.*, e.order_id, e.event_id
              FROM post_sale_return_items ri
              JOIN post_sale_events e ON e.event_id=ri.event_id
              LEFT JOIN post_sale_events reversal ON reversal.reverses_event_id=e.event_id
             WHERE e.order_id IN ({placeholders}) AND reversal.event_id IS NULL
             ORDER BY ri.id""",
        tuple(sorted(order_ids)),
    ).fetchall()
    return {(row["item_type"], int(row["sale_item_id"])): dict(row) for row in rows}


def create_return(db: sqlite3.Connection, order_id: int, payload: dict) -> dict:
    request_id, duplicate = _request(db, payload)
    if duplicate:
        return duplicate
    order = _order(db, order_id)
    reason, notes = _reason(payload, RETURN_REASONS, "return")
    if payload.get("physical_received_confirmed") is not True or payload.get("condition_confirmed") is not True:
        raise ValueError("Physical receipt and condition must both be explicitly confirmed")
    selected = payload.get("items")
    if not isinstance(selected, list) or not selected:
        raise ValueError("Select at least one exact returned item")
    now = utcnow()
    changes: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for request_item in selected:
        item_type = _text(request_item.get("item_type"), 20).upper()
        sale_item_id = int(request_item.get("sale_item_id") or 0)
        outcome = _text(request_item.get("outcome"), 30).upper()
        key = (item_type, sale_item_id)
        if key in seen or item_type not in {"CARD", "SEALED_UNIT"} or sale_item_id < 1:
            raise ValueError("Each exact return item must be selected once")
        if outcome not in RETURN_OUTCOMES:
            raise ValueError("Return outcome must be Restocked or Damaged/Excluded")
        seen.add(key)
        if _active_return(db, item_type, sale_item_id):
            raise ValueError("This exact sale item has already been returned")
        if item_type == "CARD":
            row = db.execute(
                """SELECT si.id AS sale_item_id, si.order_id, c.*, b.batch_code,
                          r.status AS rip_status,
                          EXISTS(SELECT 1 FROM rip_basis_events rbe WHERE rbe.card_id=c.id AND rbe.target_type='CARD') AS basis_known
                     FROM sale_items si JOIN cards c ON c.id=si.card_id
                     JOIN batches b ON b.id=c.batch_id
                     LEFT JOIN rip_sessions r ON r.id=c.rip_session_id
                    WHERE si.id=? AND si.order_id=?""",
                (sale_item_id, order_id),
            ).fetchone()
            if not row:
                raise ValueError("Returned card item does not belong to this order")
            latest = db.execute("SELECT MAX(id) FROM sale_items WHERE card_id=?", (row["id"],)).fetchone()[0]
            if latest != sale_item_id or row["status"] != "SOLD" or row["recycled_at"]:
                raise ValueError("This exact card is not currently held by this sale")
            basis = current_card_basis_cents(db, int(row["id"])) if row["rip_status"] == "FINALIZED" and row["basis_known"] else None
            prior = {"status": row["status"], "recycled_at": row["recycled_at"], "recycle_reason": row["recycle_reason"], "purge_after": row["purge_after"], "pre_recycle_status": row["pre_recycle_status"]}
            if outcome == "RESTOCKED":
                changed = db.execute(
                    """UPDATE cards SET status='IN_STOCK', recycled_at=NULL, recycle_reason='',
                              purge_after=NULL, pre_recycle_status=NULL, updated_at=?
                         WHERE id=? AND status='SOLD' AND recycled_at IS NULL""",
                    (now, row["id"]),
                )
            else:
                changed = db.execute(
                    """UPDATE cards SET status='HOLD', recycled_at=?, recycle_reason='RETURN_DAMAGED',
                              purge_after=NULL, pre_recycle_status='SOLD', updated_at=?
                         WHERE id=? AND status='SOLD' AND recycled_at IS NULL""",
                    (now, now, row["id"]),
                )
            if changed.rowcount != 1:
                raise sqlite3.IntegrityError("Returned card changed during restoration")
            changes.append({"item_type": item_type, "sale_item_id": sale_item_id, "entity_id": int(row["id"]), "identifier": row["sku"], "outcome": outcome, "basis_cents": basis, "prior": prior})
        else:
            row = db.execute(
                """SELECT ssi.id AS sale_item_id, ssi.order_id, su.*
                     FROM sealed_sale_items ssi JOIN sealed_units su ON su.id=ssi.sealed_unit_id
                    WHERE ssi.id=? AND ssi.order_id=?""",
                (sale_item_id, order_id),
            ).fetchone()
            if not row:
                raise ValueError("Returned sealed item does not belong to this order")
            if row["status"] != "SOLD" or row["current_order_id"] != order_id:
                raise ValueError("This exact sealed unit is not currently held by this sale")
            basis = current_sealed_basis_cents(db, int(row["id"]))
            prior = {"status": row["status"], "current_order_id": row["current_order_id"], "rip_session_id": row["rip_session_id"]}
            to_status = "REMAINING" if outcome == "RESTOCKED" else "ADJUSTED"
            changed = db.execute(
                """UPDATE sealed_units SET status=?, current_order_id=NULL, updated_at=?
                     WHERE id=? AND status='SOLD' AND current_order_id=?""",
                (to_status, now, row["id"], order_id),
            )
            if changed.rowcount != 1:
                raise sqlite3.IntegrityError("Returned sealed unit changed during restoration")
            changes.append({"item_type": item_type, "sale_item_id": sale_item_id, "entity_id": int(row["id"]), "identifier": row["unit_code"], "outcome": outcome, "basis_cents": basis, "prior": prior})
    event = _insert_event(
        db, request_id=request_id, order_id=order_id, event_type="CUSTOMER_RETURN",
        reason_code=reason, notes=notes, entries=[],
        payload={"physical_received_confirmed": True, "condition_confirmed": True, "item_count": len(changes)},
        effective_at=_text(payload.get("effective_at"), 40) or None,
    )
    for item in changes:
        db.execute(
            """INSERT INTO post_sale_return_items
               (event_id, item_type, sale_item_id, entity_id, stable_identifier,
                outcome, basis_cents, prior_state, restored_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event["event_id"], item["item_type"], item["sale_item_id"], item["entity_id"],
                item["identifier"], item["outcome"], item["basis_cents"],
                json.dumps(item["prior"], separators=(",", ":"), sort_keys=True), now,
            ),
        )
    return event_payload(db, event["event_id"])


def reverse_event(db: sqlite3.Connection, event_id: str, payload: dict) -> dict:
    request_id, duplicate = _request(db, payload)
    if duplicate:
        return duplicate
    original = db.execute("SELECT * FROM post_sale_events WHERE event_id=?", (event_id,)).fetchone()
    if not original:
        raise ValueError("Post-sale event not found")
    if original["event_type"] == "REVERSAL":
        raise ValueError("A reversal cannot itself be reversed")
    if db.execute("SELECT 1 FROM post_sale_events WHERE reverses_event_id=?", (event_id,)).fetchone():
        raise ValueError("This post-sale event has already been reversed")
    reason, notes = _reason(payload, CORRECTION_REASONS, "reversal", notes_required=True)
    return_rows = db.execute("SELECT * FROM post_sale_return_items WHERE event_id=? ORDER BY id", (event_id,)).fetchall()
    now = utcnow()
    for item in return_rows:
        prior = json.loads(item["prior_state"] or "{}")
        if item["item_type"] == "CARD":
            expected_status = "IN_STOCK" if item["outcome"] == "RESTOCKED" else "HOLD"
            row = db.execute("SELECT * FROM cards WHERE id=?", (item["entity_id"],)).fetchone()
            expected_recycled = item["outcome"] == "DAMAGED_EXCLUDED"
            if not row or row["status"] != expected_status or bool(row["recycled_at"]) != expected_recycled:
                raise ValueError("Returned card changed after restoration; reversal is unsafe")
            changed = db.execute(
                """UPDATE cards SET status=?, recycled_at=?, recycle_reason=?, purge_after=?,
                          pre_recycle_status=?, updated_at=? WHERE id=? AND status=?""",
                (prior["status"], prior["recycled_at"], prior["recycle_reason"], prior["purge_after"], prior["pre_recycle_status"], now, item["entity_id"], expected_status),
            )
        else:
            expected_status = "REMAINING" if item["outcome"] == "RESTOCKED" else "ADJUSTED"
            changed = db.execute(
                """UPDATE sealed_units SET status=?, current_order_id=?, rip_session_id=?, updated_at=?
                     WHERE id=? AND status=? AND current_order_id IS NULL""",
                (prior["status"], prior["current_order_id"], prior["rip_session_id"], now, item["entity_id"], expected_status),
            )
        if changed.rowcount != 1:
            raise sqlite3.IntegrityError("Returned inventory changed during event reversal")
    inverse_entries = [
        (row["component_type"], -int(row["amount_delta_cents"]))
        for row in db.execute(
            "SELECT component_type, amount_delta_cents FROM post_sale_event_entries WHERE event_id=? ORDER BY id",
            (event_id,),
        ).fetchall()
    ]
    return _insert_event(
        db, request_id=request_id, order_id=int(original["order_id"]), event_type="REVERSAL",
        reason_code=reason, notes=notes, entries=inverse_entries,
        payload={"reversed_event_id": event_id, "inventory_items_reversed": len(return_rows)},
        effective_at=_text(payload.get("effective_at"), 40) or None,
        reverses_event_id=event_id,
    )


def _order_items(db: sqlite3.Connection, order: sqlite3.Row) -> list[dict]:
    order_id = int(order["id"])
    active = active_returned_sale_items(db, {order_id})
    items: list[dict] = []
    if order["order_type"] == "CARD":
        rows = db.execute(
            """SELECT si.id AS sale_item_id, si.sale_price, c.id AS entity_id, c.sku AS identifier,
                      c.status, c.recycled_at, c.batch_id, b.batch_code, r.status AS rip_status,
                      EXISTS(SELECT 1 FROM rip_basis_events rbe WHERE rbe.card_id=c.id AND rbe.target_type='CARD') AS basis_known
                 FROM sale_items si JOIN cards c ON c.id=si.card_id
                 JOIN batches b ON b.id=c.batch_id LEFT JOIN rip_sessions r ON r.id=c.rip_session_id
                WHERE si.order_id=? ORDER BY si.id""",
            (order_id,),
        ).fetchall()
        for row in rows:
            returned = active.get(("CARD", int(row["sale_item_id"])))
            basis = current_card_basis_cents(db, int(row["entity_id"])) if row["rip_status"] == "FINALIZED" and row["basis_known"] else None
            items.append({**dict(row), "item_type": "CARD", "basis_cents": basis, "returned": bool(returned), "return_outcome": returned["outcome"] if returned else None})
    else:
        rows = db.execute(
            """SELECT ssi.id AS sale_item_id, ssi.merchandise_amount_cents, su.id AS entity_id,
                      su.unit_code AS identifier, su.status, su.current_order_id,
                      ssi.batch_id, b.batch_code
                 FROM sealed_sale_items ssi JOIN sealed_units su ON su.id=ssi.sealed_unit_id
                 JOIN batches b ON b.id=ssi.batch_id WHERE ssi.order_id=? ORDER BY ssi.id""",
            (order_id,),
        ).fetchall()
        for row in rows:
            returned = active.get(("SEALED_UNIT", int(row["sale_item_id"])))
            items.append({**dict(row), "item_type": "SEALED_UNIT", "basis_cents": current_sealed_basis_cents(db, int(row["entity_id"])), "returned": bool(returned), "return_outcome": returned["outcome"] if returned else None})
    return items


def order_payload(db: sqlite3.Connection, order_id: int) -> dict:
    order = db.execute("SELECT * FROM sale_orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        raise ValueError("Sale order not found")
    items = _order_items(db, order)
    facts = financial_facts(db, order_id)
    active_basis = [item["basis_cents"] for item in items if not item["returned"]]
    basis_complete = all(value is not None for value in active_basis)
    sold_basis = sum(int(value) for value in active_basis if value is not None)
    events = [event_payload(db, row[0]) for row in db.execute(
        "SELECT event_id FROM post_sale_events WHERE order_id=? ORDER BY recorded_at, event_id", (order_id,)
    ).fetchall()]
    result = dict(order)
    result.update({
        "calculation_version": CALCULATION_VERSION,
        "items": items,
        "item_count": len(items),
        "financials": facts,
        "sold_basis_cents": sold_basis if basis_complete else None,
        "sold_basis_complete": basis_complete,
        "realized_profit_loss_cents": facts["effective"]["net_proceeds_cents"] - sold_basis if basis_complete else None,
        "events": events,
        "post_sale_event_count": len(events),
        "post_sale_eligible": not bool(order["canceled_at"]),
        "original_sale_immutable_notice": "Original sale and item facts are preserved. Adjustments are append-only events.",
    })
    return result
