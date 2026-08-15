"""Phase 6 read-only batch economics derived from authoritative source facts.

Calculated totals are never persisted. Money remains integer cents and every
cross-batch card-order attribution uses stable sale-item identifiers.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from dex_economics import CALCULATION_VERSION, allocate_weighted_cents
from dex_corrections import (
    current_acquisition_cost_cents,
    current_operational_loss_cents,
)
from dex_post_sale import active_returned_sale_items, financial_facts


GROUP_NOTICE = (
    "Informational aggregation only. Shared shipping, tax, discounts, and fees "
    "were not allocated automatically."
)
ORDER_ATTRIBUTION_NOTICE = (
    "Cross-batch card orders use the original stable sale-item weighting. "
    "Each order component is allocated once across immutable sale-item IDs."
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def dollars_to_cents(value: object) -> int | None:
    if value is None:
        return None
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not amount.is_finite():
        return None
    return int(amount * 100)


def _columns(db: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in db.execute(f"PRAGMA table_info({table})")}


def _exact_or_legacy(row: sqlite3.Row, exact: str, legacy: str) -> int:
    if exact in row.keys() and row[exact] is not None:
        return int(row[exact])
    return dollars_to_cents(row[legacy]) or 0


def _allocated(total: int, weighted_ids: list[tuple[int, int]]) -> dict[int, int]:
    return {int(item.stable_id): item.cents for item in allocate_weighted_cents(total, weighted_ids)}


def card_sale_item_allocations(db: sqlite3.Connection, order_ids: set[int]) -> dict[int, dict]:
    """Allocate each order's effective facts once using its original stable weights."""
    if not order_ids:
        return {}
    order_columns = _columns(db, "sale_orders")
    optional = {
        name: (f"o.{name}" if name in order_columns else f"NULL AS {name}")
        for name in (
            "merchandise_total_cents",
            "shipping_collected_cents",
            "marketplace_fees_cents",
            "actual_postage_cents",
        )
    }
    placeholders = ",".join("?" for _ in order_ids)
    rows = db.execute(
        f"""
        SELECT si.id AS sale_item_id, si.card_id, si.order_id, si.sale_price,
               c.batch_id, o.subtotal, o.shipping_collected, o.platform_fees,
               o.postage_cost, {optional['merchandise_total_cents']},
               {optional['shipping_collected_cents']},
               {optional['marketplace_fees_cents']}, {optional['actual_postage_cents']}
          FROM sale_items si
          JOIN cards c ON c.id=si.card_id
          JOIN sale_orders o ON o.id=si.order_id
         WHERE si.order_id IN ({placeholders})
         ORDER BY si.order_id, si.id
        """,
        tuple(sorted(order_ids)),
    ).fetchall()
    by_order: dict[int, list[sqlite3.Row]] = {}
    for row in rows:
        by_order.setdefault(int(row["order_id"]), []).append(row)

    result: dict[int, dict] = {}
    for order_id, items in by_order.items():
        weights = [
            (int(row["sale_item_id"]), max(0, dollars_to_cents(row["sale_price"]) or 0))
            for row in items
        ]
        effective = financial_facts(db, order_id)["effective"]
        merchandise = int(effective["merchandise_cents"])
        shipping = int(effective["shipping_cents"])
        fees = int(effective["marketplace_fees_cents"])
        postage = int(effective["postage_cents"])
        other_net = int(effective["other_net_cents"])
        net = int(effective["net_proceeds_cents"])
        allocated = {
            "gross_cents": _allocated(merchandise, weights),
            "shipping_cents": _allocated(shipping, weights),
            "fees_cents": _allocated(fees, weights),
            "postage_cents": _allocated(postage, weights),
            "other_net_cents": _allocated(other_net, weights),
            "net_cents": _allocated(net, weights),
        }
        for row in items:
            item_id = int(row["sale_item_id"])
            result[item_id] = {
                "sale_item_id": item_id,
                "order_id": order_id,
                "batch_id": int(row["batch_id"]),
                "card_id": int(row["card_id"]),
                **{name: values[item_id] for name, values in allocated.items()},
            }
    return result


def _card_rows(db: sqlite3.Connection, batch_id: int) -> list[sqlite3.Row]:
    return db.execute(
        """
        SELECT c.*, r.status AS rip_status, r.rip_code, r.finalized_at AS rip_finalized_at,
               cb.basis_cents, COALESCE(cb.basis_event_count,0) AS basis_event_count
          FROM cards c
          LEFT JOIN rip_sessions r ON r.id=c.rip_session_id
          LEFT JOIN (
              SELECT card_id, SUM(amount_delta_cents) AS basis_cents,
                     COUNT(*) AS basis_event_count FROM (
                  SELECT card_id, amount_delta_cents
                    FROM rip_basis_events WHERE target_type='CARD'
                  UNION ALL
                  SELECT target_id AS card_id, amount_delta_cents
                    FROM economic_event_entries
                   WHERE entry_type='BASIS' AND target_type='CARD'
              ) GROUP BY card_id
          ) cb ON cb.card_id=c.id
         WHERE c.batch_id=?
         ORDER BY c.id
        """,
        (batch_id,),
    ).fetchall()


def _basis_known(card: sqlite3.Row) -> bool:
    return card["rip_status"] == "FINALIZED" and int(card["basis_event_count"] or 0) > 0


def _valuation(
    cards: list[sqlite3.Row],
    value_field: str,
    timestamp_field: str | None,
    *,
    additional_unknown_count: int = 0,
    quantity_unknown: bool = False,
) -> dict:
    known_values: list[int] = []
    timestamps: list[str] = []
    timestamp_unknown = False
    for card in cards:
        cents = dollars_to_cents(card[value_field])
        if cents is None:
            continue
        known_values.append(cents)
        if timestamp_field and card[timestamp_field]:
            timestamps.append(str(card[timestamp_field]))
        else:
            timestamp_unknown = True
    total = len(cards) + additional_unknown_count
    freshness = min(timestamps) if known_values and not timestamp_unknown and len(timestamps) == len(known_values) else None
    complete = len(known_values) == total and not quantity_unknown
    return {
        "known_value_cents": sum(known_values),
        "valued_count": len(known_values),
        "total_count": total,
        "quantity_unknown": quantity_unknown,
        "complete": complete,
        "freshness": freshness,
        "freshness_label": freshness or "Freshness Unknown",
        "coverage_label": (
            f"{len(known_values)}/{total} inventory items valued"
            + ("; additional bulk quantity unknown" if quantity_unknown else "")
        ),
    }


def _sale_orders(db: sqlite3.Connection, order_ids: set[int]) -> dict[int, sqlite3.Row]:
    if not order_ids:
        return {}
    placeholders = ",".join("?" for _ in order_ids)
    return {
        int(row["id"]): row
        for row in db.execute(
            f"SELECT * FROM sale_orders WHERE id IN ({placeholders}) ORDER BY id",
            tuple(sorted(order_ids)),
        ).fetchall()
    }


def _sales_for_batch(db: sqlite3.Connection, batch_id: int, cards: list[sqlite3.Row]) -> dict:
    card_items = db.execute(
        """SELECT si.id AS sale_item_id, si.order_id, si.sale_price,
                  c.id AS card_id, c.sku
             FROM sale_items si JOIN cards c ON c.id=si.card_id
            WHERE c.batch_id=? ORDER BY si.order_id, si.id""",
        (batch_id,),
    ).fetchall()
    cards_by_id = {int(card["id"]): card for card in cards}
    card_order_ids = {int(item["order_id"]) for item in card_items}
    card_allocations = card_sale_item_allocations(db, card_order_ids)
    sealed_items = db.execute(
        """SELECT ssi.*, su.unit_code, su.unit_sequence,
                  su.basis_cents + COALESCE((
                      SELECT SUM(eee.amount_delta_cents)
                        FROM economic_event_entries eee
                       WHERE eee.entry_type='BASIS' AND eee.target_type='SEALED_UNIT'
                         AND eee.target_id=su.id
                  ),0) AS current_basis_cents
             FROM sealed_sale_items ssi
             JOIN sealed_units su ON su.id=ssi.sealed_unit_id
            WHERE ssi.batch_id=? ORDER BY ssi.order_id, ssi.id""",
        (batch_id,),
    ).fetchall()
    all_order_ids = card_order_ids | {int(row["order_id"]) for row in sealed_items}
    order_rows = _sale_orders(db, all_order_ids)
    returned_items = active_returned_sale_items(db, all_order_ids)
    records: dict[int, dict] = {}

    def record_for(order_id: int, order_type: str) -> dict:
        if order_id in records:
            return records[order_id]
        order = order_rows[order_id]
        records[order_id] = {
            "order_id": order_id,
            "order_type": order_type,
            "platform": order["platform"],
            "order_number": order["order_number"],
            "sold_at": order["sold_at"],
            "canceled": bool(order["canceled_at"]),
            "canceled_at": order["canceled_at"],
            "counts_in_realized": not bool(order["canceled_at"]),
            "gross_merchandise_cents": 0,
            "shipping_collected_cents": 0,
            "marketplace_fees_cents": 0,
            "actual_postage_cents": 0,
            "other_net_cents": 0,
            "net_proceeds_cents": 0,
            "known_sold_basis_cents": 0,
            "basis_known_count": 0,
            "basis_total_count": 0,
            "items": [],
            "attribution": "Stable attributable batch portion" if order_type == "CARD" else "Exact sealed-order batch",
        }
        return records[order_id]

    for sale_item in card_items:
        item_id = int(sale_item["sale_item_id"])
        if item_id not in card_allocations:
            continue
        card = cards_by_id[int(sale_item["card_id"])]
        allocation = card_allocations[item_id]
        record = record_for(int(sale_item["order_id"]), "CARD")
        record["gross_merchandise_cents"] += allocation["gross_cents"]
        record["shipping_collected_cents"] += allocation["shipping_cents"]
        record["marketplace_fees_cents"] += allocation["fees_cents"]
        record["actual_postage_cents"] += allocation["postage_cents"]
        record["other_net_cents"] += allocation["other_net_cents"]
        record["net_proceeds_cents"] += allocation["net_cents"]
        known = _basis_known(card)
        basis = int(card["basis_cents"] or 0) if known else None
        returned = returned_items.get(("CARD", item_id))
        if not returned:
            record["basis_total_count"] += 1
            if known:
                record["basis_known_count"] += 1
                record["known_sold_basis_cents"] += int(basis)
        record["items"].append({
            "item_type": "CARD",
            "stable_item_id": int(item_id),
            "physical_id": int(card["id"]),
            "identifier": card["sku"],
            "basis_cents": basis,
            "returned": bool(returned),
            "return_outcome": returned["outcome"] if returned else None,
            "gross_merchandise_cents": allocation["gross_cents"],
            "net_proceeds_cents": allocation["net_cents"],
        })

    sealed_by_order: dict[int, list[sqlite3.Row]] = {}
    for item in sealed_items:
        sealed_by_order.setdefault(int(item["order_id"]), []).append(item)
    for order_id, items in sealed_by_order.items():
        effective = financial_facts(db, order_id)["effective"]
        weights = [(int(row["id"]), int(row["merchandise_amount_cents"])) for row in items]
        merchandise = int(effective["merchandise_cents"])
        shipping = int(effective["shipping_cents"])
        fees = int(effective["marketplace_fees_cents"])
        postage = int(effective["postage_cents"])
        other_net = int(effective["other_net_cents"])
        net = int(effective["net_proceeds_cents"])
        allocated_merchandise = _allocated(merchandise, weights)
        allocated_shipping = _allocated(shipping, weights)
        allocated_fees = _allocated(fees, weights)
        allocated_postage = _allocated(postage, weights)
        allocated_other_net = _allocated(other_net, weights)
        allocated_net = _allocated(net, weights)
        record = record_for(order_id, "SEALED")
        for item in items:
            item_id = int(item["id"])
            returned = returned_items.get(("SEALED_UNIT", item_id))
            record["gross_merchandise_cents"] += allocated_merchandise[item_id]
            record["shipping_collected_cents"] += allocated_shipping[item_id]
            record["marketplace_fees_cents"] += allocated_fees[item_id]
            record["actual_postage_cents"] += allocated_postage[item_id]
            record["other_net_cents"] += allocated_other_net[item_id]
            record["net_proceeds_cents"] += allocated_net[item_id]
            if not returned:
                record["known_sold_basis_cents"] += int(item["current_basis_cents"])
                record["basis_known_count"] += 1
                record["basis_total_count"] += 1
            record["items"].append({
                "item_type": "SEALED",
                "stable_item_id": item_id,
                "physical_id": int(item["sealed_unit_id"]),
                "identifier": item["unit_code"],
                "basis_cents": int(item["current_basis_cents"]),
                "returned": bool(returned),
                "return_outcome": returned["outcome"] if returned else None,
                "gross_merchandise_cents": allocated_merchandise[item_id],
                "net_proceeds_cents": allocated_net[item_id],
            })

    orders = []
    for record in records.values():
        complete = record["basis_known_count"] == record["basis_total_count"]
        record["sold_basis_complete"] = complete
        record["sold_basis_cents"] = record["known_sold_basis_cents"] if complete else None
        record["realized_profit_loss_cents"] = (
            record["net_proceeds_cents"] - record["known_sold_basis_cents"] if complete else None
        )
        orders.append(record)
    orders.sort(key=lambda row: (row["sold_at"], row["order_id"]), reverse=True)
    included = [row for row in orders if row["counts_in_realized"]]
    basis_known_count = sum(row["basis_known_count"] for row in included)
    basis_total_count = sum(row["basis_total_count"] for row in included)
    basis_complete = basis_known_count == basis_total_count
    known_basis = sum(row["known_sold_basis_cents"] for row in included)
    net = sum(row["net_proceeds_cents"] for row in included)
    return {
        "gross_merchandise_cents": sum(row["gross_merchandise_cents"] for row in included),
        "shipping_collected_cents": sum(row["shipping_collected_cents"] for row in included),
        "marketplace_fees_cents": sum(row["marketplace_fees_cents"] for row in included),
        "actual_postage_cents": sum(row["actual_postage_cents"] for row in included),
        "other_net_cents": sum(row["other_net_cents"] for row in included),
        "net_proceeds_cents": net,
        "known_sold_basis_cents": known_basis,
        "sold_basis_cents": known_basis if basis_complete else None,
        "sold_basis_known_count": basis_known_count,
        "sold_basis_total_count": basis_total_count,
        "sold_basis_complete": basis_complete,
        "realized_profit_loss_cents": net - known_basis if basis_complete else None,
        "active_order_count": len(included),
        "canceled_order_count": len(orders) - len(included),
        "orders": orders,
        "allocation_notice": ORDER_ATTRIBUTION_NOTICE,
    }


def _legacy_report(batch: sqlite3.Row) -> dict:
    return {
        "calculation_version": CALCULATION_VERSION,
        "generated_at": utcnow(),
        "state": "LEGACY_ESTIMATE_ONLY",
        "authoritative": False,
        "batch": {
            "id": batch["id"],
            "batch_code": batch["batch_code"],
            "status": batch["status"],
            "economics_status": batch["economics_status"] or "ESTIMATED",
        },
        "notice": "Estimate only. Cost basis not finalized. Use the existing legacy preview.",
        "warnings": [{
            "code": "LEGACY_ESTIMATE_ONLY",
            "severity": "material",
            "message": "No authoritative Phase 3 acquisition cost has been finalized for this batch.",
        }],
    }


def _batch_report(db: sqlite3.Connection, batch_id: int) -> dict:
    batch = db.execute("SELECT * FROM batches WHERE id=? AND recycled_at IS NULL", (batch_id,)).fetchone()
    if not batch:
        raise ValueError("Batch not found")
    if batch["economics_mode"] not in ("SEALED_RIP", "SINGLES_KNOWN_COST", "SINGLES_LUMP_SUM") or batch["final_usd_paid_cents"] is None:
        return _legacy_report(batch)

    preserved_source_cost = int(batch["final_usd_paid_cents"])
    authoritative_cost = current_acquisition_cost_cents(db, batch_id)
    operational_loss = current_operational_loss_cents(db, batch_id)
    cards = _card_rows(db, batch_id)
    sales = _sales_for_batch(db, batch_id, cards)
    active_cards = [row for row in cards if row["status"] != "SOLD" and row["recycled_at"] is None]
    excluded_cards = [row for row in cards if row["status"] != "SOLD" and row["recycled_at"] is not None]
    active_basis_known = [row for row in active_cards if _basis_known(row)]
    excluded_basis_known = [row for row in excluded_cards if _basis_known(row)]

    rips = db.execute(
        """SELECT r.*,
                  COALESCE((SELECT SUM(amount_delta_cents) FROM rip_basis_events be WHERE be.rip_session_id=r.id AND be.target_type='BULK'),0)
                    + COALESCE((SELECT SUM(amount_delta_cents) FROM economic_event_entries eee WHERE eee.entry_type='BASIS' AND eee.target_type='RIP_BULK' AND eee.target_id=r.id),0) AS current_bulk_basis_cents,
                  COALESCE((SELECT SUM(be.amount_delta_cents) FROM rip_basis_events be WHERE be.rip_session_id=r.id AND be.target_type='CARD'),0)
                    + COALESCE((SELECT SUM(eee.amount_delta_cents) FROM economic_event_entries eee JOIN cards ec ON ec.id=eee.target_id WHERE eee.entry_type='BASIS' AND eee.target_type='CARD' AND ec.rip_session_id=r.id),0) AS current_card_basis_cents
             FROM rip_sessions r WHERE r.batch_id=? ORDER BY r.id""",
        (batch_id,),
    ).fetchall()
    finalized_rips = [row for row in rips if row["status"] == "FINALIZED"]
    pending_rips = [row for row in rips if row["status"] != "FINALIZED"]
    bulk_basis = sum(int(row["current_bulk_basis_cents"] or 0) for row in finalized_rips)
    known_bulk_quantity = sum(int(row["bulk_quantity"] or 0) for row in finalized_rips if row["bulk_mode"] == "KNOWN_QUANTITY")
    bulk_quantity_unknown = any(
        row["bulk_mode"] == "MANUAL_RESERVE" and int(row["current_bulk_basis_cents"] or 0) > 0
        for row in finalized_rips
    )

    sealed_units = db.execute(
        """SELECT su.*, r.status AS rip_status,
                  su.basis_cents + COALESCE((SELECT SUM(eee.amount_delta_cents)
                    FROM economic_event_entries eee WHERE eee.entry_type='BASIS'
                      AND eee.target_type='SEALED_UNIT' AND eee.target_id=su.id),0) AS current_basis_cents
             FROM sealed_units su LEFT JOIN rip_sessions r ON r.id=su.rip_session_id
            WHERE su.batch_id=? ORDER BY su.unit_sequence""",
        (batch_id,),
    ).fetchall()
    remaining_units = [row for row in sealed_units if row["status"] == "REMAINING"]
    adjusted_units = [row for row in sealed_units if row["status"] == "ADJUSTED"]
    pending_opened_units = [row for row in sealed_units if row["status"] == "OPENED" and row["rip_status"] != "FINALIZED"]
    remaining_sealed_basis = sum(int(row["current_basis_cents"]) for row in remaining_units)
    adjusted_basis = sum(int(row["current_basis_cents"]) for row in adjusted_units)
    pending_opened_basis = sum(int(row["current_basis_cents"]) for row in pending_opened_units)
    unallocated_singles_basis = (
        authoritative_cost
        if batch["economics_mode"] != "SEALED_RIP" and not finalized_rips
        else 0
    )

    additional_unknown = len(remaining_units) + known_bulk_quantity
    market = _valuation(
        active_cards,
        "market_average",
        "market_updated_at",
        additional_unknown_count=additional_unknown,
        quantity_unknown=bulk_quantity_unknown,
    )
    listed = _valuation(
        active_cards,
        "listing_price",
        None,
        additional_unknown_count=additional_unknown,
        quantity_unknown=bulk_quantity_unknown,
    )
    excluded_market = _valuation(excluded_cards, "market_average", "market_updated_at")
    excluded_listed = _valuation(excluded_cards, "listing_price", None)

    remaining_known_basis = (
        sum(int(row["basis_cents"] or 0) for row in active_basis_known)
        + remaining_sealed_basis + bulk_basis + pending_opened_basis + unallocated_singles_basis
    )
    remaining_basis_complete = len(active_basis_known) == len(active_cards) and not pending_rips
    excluded_known_basis = sum(int(row["basis_cents"] or 0) for row in excluded_basis_known) + adjusted_basis

    current_position = sales["net_proceeds_cents"] + market["known_value_cents"] - authoritative_cost
    listed_position = sales["net_proceeds_cents"] + listed["known_value_cents"] - authoritative_cost
    recovery = None if authoritative_cost == 0 else round(sales["net_proceeds_cents"] * 100 / authoritative_cost, 2)

    rip_reconciliation = []
    for rip in rips:
        allocated = int(rip["current_card_basis_cents"] or 0) + int(rip["current_bulk_basis_cents"] or 0)
        consumed = rip["consumed_cost_cents"]
        difference = None if consumed is None else int(consumed) - allocated
        rip_reconciliation.append({
            "rip_session_id": int(rip["id"]),
            "rip_code": rip["rip_code"],
            "status": rip["status"],
            "rip_cost_cents": consumed,
            "allocated_cents": allocated,
            "difference_cents": difference,
            "reconciled": difference == 0 if difference is not None else False,
        })

    if batch["economics_mode"] == "SEALED_RIP":
        allocation_total = sum(int(row["current_basis_cents"]) for row in sealed_units) + operational_loss
    else:
        allocation_total = sum(int(row["current_card_basis_cents"] or 0) + int(row["current_bulk_basis_cents"] or 0) for row in finalized_rips) + operational_loss
    basis_difference = authoritative_cost - allocation_total
    sealed_counts = {status: 0 for status in ("REMAINING", "OPENED", "SOLD", "ADJUSTED")}
    for row in sealed_units:
        sealed_counts[row["status"]] += 1
    units_acquired = int(batch["units_acquired"] or 0)
    quantity_accounted = sum(sealed_counts.values())

    warnings: list[dict[str, str]] = []
    if batch["economics_status"] != "FINALIZED":
        warnings.append({"code": "ECONOMICS_NOT_FINALIZED", "severity": "material", "message": "Acquisition cost is authoritative, but card/bulk allocation is not fully finalized."})
    if pending_rips:
        warnings.append({"code": "RIP_ALLOCATION_PENDING", "severity": "material", "message": "One or more rip sessions are not finalized; remaining basis and valuation may be incomplete."})
    if not sales["sold_basis_complete"]:
        warnings.append({"code": "SOLD_BASIS_INCOMPLETE", "severity": "material", "message": "One or more sold cards do not have finalized basis, so realized P/L is incomplete."})
    if not market["complete"]:
        warnings.append({"code": "MARKET_VALUE_INCOMPLETE", "severity": "material", "message": "Unknown-priced remaining inventory makes Current Economic Position incomplete."})
    if not listed["complete"]:
        warnings.append({"code": "LISTED_VALUE_INCOMPLETE", "severity": "material", "message": "Unknown-listed remaining inventory makes Projected Listed Position incomplete."})
    if remaining_units:
        warnings.append({"code": "SEALED_VALUE_UNKNOWN", "severity": "material", "message": "Remaining sealed units have no market/listed price field in this release."})
    if bulk_quantity_unknown:
        warnings.append({"code": "BULK_QUANTITY_UNKNOWN", "severity": "material", "message": "Unscanned bulk has reserved basis but unknown physical quantity; valuation coverage is incomplete."})
    if excluded_cards or adjusted_units:
        warnings.append({"code": "EXCLUDED_INVENTORY", "severity": "info", "message": "Recycled cards and adjusted sealed units are shown separately and excluded from active remaining value."})
    if operational_loss:
        warnings.append({"code": "OPERATIONAL_LOSS_RECORDED", "severity": "info", "message": "Audited damage, loss, or disposition basis is reported as an operational loss; DEX makes no tax-deduction conclusion."})
    if sales["canceled_order_count"]:
        warnings.append({"code": "CANCELED_SALES_EXCLUDED", "severity": "info", "message": "Canceled sealed orders remain in history but do not contribute to realized totals."})
    if basis_difference:
        warnings.append({"code": "BASIS_RECONCILIATION_DIFFERENCE", "severity": "material", "message": "Authoritative acquisition cost does not fully reconcile to the current unit/allocation ledger."})
    if batch["economics_mode"] == "SEALED_RIP" and units_acquired != quantity_accounted:
        warnings.append({"code": "QUANTITY_RECONCILIATION_DIFFERENCE", "severity": "material", "message": "Sealed acquired quantity does not reconcile to unit states."})
    if recovery is None:
        warnings.append({"code": "ZERO_ACQUISITION_COST", "severity": "info", "message": "Cost Recovery % is undefined because authoritative acquisition cost is $0.00."})

    receipt_reference = batch["receipt_group_reference"] or ""
    report = {
        "calculation_version": CALCULATION_VERSION,
        "generated_at": utcnow(),
        "state": "AUTHORITATIVE",
        "authoritative": True,
        "batch": {
            "id": int(batch["id"]),
            "batch_code": batch["batch_code"],
            "status": batch["status"],
            "economics_mode": batch["economics_mode"],
            "economics_status": batch["economics_status"],
            "product_name": batch["product_name"] or batch["acquisition_type"],
            "receipt_group_reference": receipt_reference,
        },
        "summary": {
            "authoritative_cost_cents": authoritative_cost,
            "realized_net_proceeds_cents": sales["net_proceeds_cents"],
            "known_remaining_market_value_cents": market["known_value_cents"],
            "current_economic_position_cents": current_position,
            "current_position_complete": market["complete"],
        },
        "acquisition": {
            "authoritative_cost_cents": authoritative_cost,
            "preserved_source_cost_cents": preserved_source_cost,
            "correction_delta_cents": authoritative_cost - preserved_source_cost,
            "reporting_currency": "USD",
            "economics_status": batch["economics_status"],
            "receipt_group_reference": receipt_reference,
        },
        "realized": {
            **{key: value for key, value in sales.items() if key != "orders"},
            "cost_recovery_percent": recovery,
            "cost_recovery_definition": "realized net proceeds ÷ authoritative acquisition cost",
        },
        "remaining": {
            "active_card_count": len(active_cards),
            "remaining_sealed_unit_count": len(remaining_units),
            "known_bulk_quantity": known_bulk_quantity,
            "bulk_quantity_unknown": bulk_quantity_unknown,
            "known_basis_cents": remaining_known_basis,
            "basis_known_count": len(active_basis_known) + len(remaining_units) + known_bulk_quantity,
            "basis_total_count": len(active_cards) + len(remaining_units) + known_bulk_quantity,
            "basis_complete": remaining_basis_complete,
            "market": market,
            "listed": listed,
            "current_economic_position_cents": current_position,
            "current_position_complete": market["complete"],
            "current_position_definition": "realized net proceeds + known remaining market value − acquisition cost",
            "projected_listed_position_cents": listed_position,
            "projected_listed_position_complete": listed["complete"],
            "projected_listed_position_definition": "realized net proceeds + known remaining listed value − acquisition cost",
        },
        "excluded": {
            "recycled_card_count": len(excluded_cards),
            "adjusted_sealed_unit_count": len(adjusted_units),
            "known_basis_cents": excluded_known_basis,
            "basis_known_count": len(excluded_basis_known) + len(adjusted_units),
            "basis_total_count": len(excluded_cards) + len(adjusted_units),
            "market": excluded_market,
            "listed": excluded_listed,
            "operational_loss_cents": operational_loss,
        },
        "sales": {"orders": sales["orders"], "allocation_notice": ORDER_ATTRIBUTION_NOTICE},
        "reconciliation": {
            "basis": {
                "authoritative_cost_cents": authoritative_cost,
                "ledger_or_finalized_allocation_cents": allocation_total,
                "difference_cents": basis_difference,
                "reconciled": basis_difference == 0,
            },
            "sealed_quantity": {
                "applicable": batch["economics_mode"] == "SEALED_RIP",
                "acquired": units_acquired,
                "opened": sealed_counts["OPENED"],
                "sold": sealed_counts["SOLD"],
                "remaining": sealed_counts["REMAINING"],
                "corrected_adjusted": sealed_counts["ADJUSTED"],
                "difference": units_acquired - quantity_accounted,
                "reconciled": units_acquired == quantity_accounted,
            },
            "rip_sessions": rip_reconciliation,
            "materially_incomplete": any(row["severity"] == "material" for row in warnings),
        },
        "warnings": warnings,
    }
    return report


def _combine_valuation(reports: list[dict], key: str) -> dict:
    values = [report["remaining"][key] for report in reports]
    timestamps = [item["freshness"] for item in values if item["freshness"]]
    freshness_unknown = any(item["freshness"] is None and item["valued_count"] for item in values)
    valued = sum(item["valued_count"] for item in values)
    total = sum(item["total_count"] for item in values)
    quantity_unknown = any(item["quantity_unknown"] for item in values)
    freshness = min(timestamps) if timestamps and not freshness_unknown else None
    return {
        "known_value_cents": sum(item["known_value_cents"] for item in values),
        "valued_count": valued,
        "total_count": total,
        "quantity_unknown": quantity_unknown,
        "complete": all(item["complete"] for item in values),
        "freshness": freshness,
        "freshness_label": freshness or "Freshness Unknown",
        "coverage_label": f"{valued}/{total} inventory items valued" + ("; additional bulk quantity unknown" if quantity_unknown else ""),
    }


def acquisition_group_economics_payload(db: sqlite3.Connection, reference: str) -> dict:
    normalized = str(reference or "").strip().upper()
    if not normalized:
        raise ValueError("Receipt/Acquisition Group reference is required")
    batch_ids = [
        int(row[0])
        for row in db.execute(
            "SELECT id FROM batches WHERE receipt_group_reference=? AND recycled_at IS NULL ORDER BY id",
            (normalized,),
        ).fetchall()
    ]
    if not batch_ids:
        raise ValueError("Receipt/Acquisition Group not found")
    reports = [_batch_report(db, batch_id) for batch_id in batch_ids]
    authoritative = [report for report in reports if report["authoritative"]]
    market = _combine_valuation(authoritative, "market") if authoritative else {
        "known_value_cents": 0, "valued_count": 0, "total_count": 0, "quantity_unknown": False,
        "complete": False, "freshness": None, "freshness_label": "Freshness Unknown", "coverage_label": "0/0 inventory items valued",
    }
    listed = _combine_valuation(authoritative, "listed") if authoritative else dict(market)
    cost = sum(report["acquisition"]["authoritative_cost_cents"] for report in authoritative)
    net = sum(report["realized"]["net_proceeds_cents"] for report in authoritative)
    order_ids = {
        order["order_id"]
        for report in authoritative
        for order in report["sales"]["orders"]
        if order["counts_in_realized"]
    }
    return {
        "calculation_version": CALCULATION_VERSION,
        "generated_at": utcnow(),
        "state": "INFORMATIONAL_GROUP_ROLLUP",
        "reference": normalized,
        "notice": GROUP_NOTICE,
        "batch_count": len(reports),
        "authoritative_batch_count": len(authoritative),
        "cost_coverage": {"known": len(authoritative), "total": len(reports)},
        "authoritative_assigned_cost_cents": cost,
        "realized": {
            "gross_merchandise_cents": sum(report["realized"]["gross_merchandise_cents"] for report in authoritative),
            "shipping_collected_cents": sum(report["realized"]["shipping_collected_cents"] for report in authoritative),
            "marketplace_fees_cents": sum(report["realized"]["marketplace_fees_cents"] for report in authoritative),
            "actual_postage_cents": sum(report["realized"]["actual_postage_cents"] for report in authoritative),
            "other_net_cents": sum(report["realized"]["other_net_cents"] for report in authoritative),
            "net_proceeds_cents": net,
            "cost_recovery_percent": None if cost == 0 else round(net * 100 / cost, 2),
            "unique_order_count": len(order_ids),
            "allocation_notice": ORDER_ATTRIBUTION_NOTICE,
        },
        "remaining": {
            "market": market,
            "listed": listed,
            "current_economic_position_cents": net + market["known_value_cents"] - cost,
            "current_position_complete": len(authoritative) == len(reports) and market["complete"],
            "projected_listed_position_cents": net + listed["known_value_cents"] - cost,
            "projected_listed_position_complete": len(authoritative) == len(reports) and listed["complete"],
        },
        "batches": [{
            "id": report["batch"]["id"],
            "batch_code": report["batch"]["batch_code"],
            "economics_status": report["batch"]["economics_status"],
            "authoritative": report["authoritative"],
        } for report in reports],
    }


def batch_economics_payload(db: sqlite3.Connection, batch_id: int) -> dict:
    report = _batch_report(db, batch_id)
    if report["authoritative"] and report["batch"]["receipt_group_reference"]:
        report["receipt_group_rollup"] = acquisition_group_economics_payload(
            db, report["batch"]["receipt_group_reference"]
        )
    else:
        report["receipt_group_rollup"] = None
    return report


def batch_economics_core_payload(db: sqlite3.Connection, batch_id: int) -> dict:
    """Return one batch report without recursively calculating its receipt group."""
    return _batch_report(db, batch_id)


def batch_economics_export_rows(db: sqlite3.Connection, batch_id: int | None = None) -> list[dict]:
    if batch_id is None:
        ids = [int(row[0]) for row in db.execute("SELECT id FROM batches WHERE recycled_at IS NULL ORDER BY id").fetchall()]
    else:
        ids = [batch_id]
    rows: list[dict] = []
    for current_id in ids:
        report = _batch_report(db, current_id)
        batch = report["batch"]
        row = {
            "calculation_version": CALCULATION_VERSION,
            "economics_state": report["state"],
            "batch_id": batch["id"],
            "batch_code": batch["batch_code"],
            "economics_mode": batch.get("economics_mode", "LEGACY"),
            "economics_status": batch["economics_status"],
            "product_name": batch.get("product_name", ""),
            "receipt_group_reference": batch.get("receipt_group_reference", ""),
        }
        if report["authoritative"]:
            realized = report["realized"]
            remaining = report["remaining"]
            row.update({
                "authoritative_cost_cents": report["acquisition"]["authoritative_cost_cents"],
                "preserved_source_cost_cents": report["acquisition"]["preserved_source_cost_cents"],
                "acquisition_correction_delta_cents": report["acquisition"]["correction_delta_cents"],
                "realized_gross_merchandise_cents": realized["gross_merchandise_cents"],
                "realized_shipping_collected_cents": realized["shipping_collected_cents"],
                "realized_marketplace_fees_cents": realized["marketplace_fees_cents"],
                "realized_actual_postage_cents": realized["actual_postage_cents"],
                "realized_other_net_cents": realized["other_net_cents"],
                "realized_net_proceeds_cents": realized["net_proceeds_cents"],
                "sold_basis_cents": realized["sold_basis_cents"],
                "sold_basis_known_count": realized["sold_basis_known_count"],
                "sold_basis_total_count": realized["sold_basis_total_count"],
                "realized_profit_loss_cents": realized["realized_profit_loss_cents"],
                "cost_recovery_percent": realized["cost_recovery_percent"],
                "remaining_known_basis_cents": remaining["known_basis_cents"],
                "remaining_basis_complete": int(remaining["basis_complete"]),
                "remaining_market_value_cents": remaining["market"]["known_value_cents"],
                "remaining_market_valued_count": remaining["market"]["valued_count"],
                "remaining_market_total_count": remaining["market"]["total_count"],
                "remaining_market_freshness": remaining["market"]["freshness_label"],
                "remaining_market_complete": int(remaining["market"]["complete"]),
                "remaining_listed_value_cents": remaining["listed"]["known_value_cents"],
                "remaining_listed_valued_count": remaining["listed"]["valued_count"],
                "remaining_listed_total_count": remaining["listed"]["total_count"],
                "remaining_listed_freshness": remaining["listed"]["freshness_label"],
                "remaining_listed_complete": int(remaining["listed"]["complete"]),
                "current_economic_position_cents": remaining["current_economic_position_cents"],
                "current_position_complete": int(remaining["current_position_complete"]),
                "projected_listed_position_cents": remaining["projected_listed_position_cents"],
                "projected_listed_position_complete": int(remaining["projected_listed_position_complete"]),
                "excluded_known_basis_cents": report["excluded"]["known_basis_cents"],
                "operational_loss_cents": report["excluded"]["operational_loss_cents"],
                "materially_incomplete": int(report["reconciliation"]["materially_incomplete"]),
                "warning_codes": " | ".join(item["code"] for item in report["warnings"]),
            })
        rows.append(row)
    return rows
