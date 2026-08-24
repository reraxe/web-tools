"""JARVIS Simplified Economics v1.

The service derives small, explainable item and sale calculations from existing
DEX facts.  It does not own acquisition, allocation, valuation, or sales data,
and it never stores calculated totals.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Mapping

from dex_batch_economics import card_sale_item_allocations
from dex_corrections import current_acquisition_cost_cents, current_card_basis_cents
from dex_economics import allocate_cents
from dex_post_sale import financial_facts, order_payload as post_sale_order_payload


CALCULATION_VERSION = "jarvis-simplified-economics-v1"
STATUSES = ("COMPLETE", "PARTIAL", "UNRESOLVED", "ESTIMATED")
VALUE_STATES = ("RECORDED", "DERIVED", "ESTIMATED", "UNRESOLVED")
ACTIVE_INVENTORY_STATES = ("IN_STOCK", "REVIEW", "HOLD")
CURRENT_VALUE_MAX_AGE_DAYS = 7
AGING_VALUE_MAX_AGE_DAYS = 30


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


def _fact(
    value: int | float | None,
    state: str,
    *,
    record: str,
    field: str,
    observed_at: str | None = None,
    reason: str = "",
    required: bool = True,
) -> dict:
    if state not in VALUE_STATES:
        raise ValueError("JARVIS value state is not supported")
    return {
        "value_cents": value,
        "state": state,
        "source_record": record,
        "source_field": field,
        "observed_at": observed_at,
        "reason": reason,
        "required_for_status": required,
    }


def _roi(profit_cents: int | None, basis_cents: int | None) -> dict:
    if profit_cents is None or basis_cents is None:
        return {"percent": None, "state": "UNRESOLVED", "reason": "REQUIRED_INPUT_UNRESOLVED"}
    if basis_cents == 0:
        return {"percent": None, "state": "UNRESOLVED", "reason": "ZERO_COST_BASIS"}
    percent = round(Decimal(profit_cents) * Decimal(100) / Decimal(basis_cents), 2)
    return {
        "percent": 0 if percent == 0 else percent,
        "state": "DERIVED",
        "reason": "",
    }


def valuation_freshness(observed_at: str | None, *, now: datetime | None = None) -> dict:
    """Describe recorded valuation age without changing valuation authority."""
    if not observed_at:
        return {
            "state": "UNKNOWN", "age_days": None, "observed_at": None,
            "label": "Freshness Unknown",
        }
    try:
        observed = datetime.fromisoformat(str(observed_at).replace("Z", "+00:00"))
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return {
            "state": "UNKNOWN", "age_days": None, "observed_at": observed_at,
            "label": "Freshness Unknown",
        }
    current = now or datetime.now(timezone.utc)
    age_days = max(0, int((current.astimezone(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds() // 86400))
    if age_days <= CURRENT_VALUE_MAX_AGE_DAYS:
        state = "CURRENT"
    elif age_days <= AGING_VALUE_MAX_AGE_DAYS:
        state = "AGING"
    else:
        state = "STALE"
    return {
        "state": state, "age_days": age_days, "observed_at": observed_at,
        "label": f"{state.title()} · observed {observed_at} · {age_days} day(s) old",
    }


def capture_sale_input_evidence(
    db: sqlite3.Connection, order_id: int, payload: Mapping, *, order_type: str
) -> None:
    """Record presence, including explicit zero, without changing sale facts."""
    if order_type == "SEALED":
        names = {
            "merchandise_proceeds_known": "merchandise_total",
            "shipping_collected_known": "shipping_collected",
            "marketplace_fees_known": "marketplace_fees",
            "actual_shipping_cost_known": "actual_postage",
        }
    else:
        names = {
            "merchandise_proceeds_known": "subtotal",
            "shipping_collected_known": "shipping_collected",
            "marketplace_fees_known": "platform_fees",
            "actual_shipping_cost_known": "postage_cost",
        }
    flags = {column: 1 if key in payload and payload.get(key) not in (None, "") else 0 for column, key in names.items()}
    db.execute(
        """INSERT INTO jarvis_sale_input_evidence
             (order_id,merchandise_proceeds_known,shipping_collected_known,
              marketplace_fees_known,actual_shipping_cost_known,captured_at,provenance)
           VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(order_id) DO UPDATE SET
             merchandise_proceeds_known=excluded.merchandise_proceeds_known,
             shipping_collected_known=excluded.shipping_collected_known,
             marketplace_fees_known=excluded.marketplace_fees_known,
             actual_shipping_cost_known=excluded.actual_shipping_cost_known,
             captured_at=excluded.captured_at,provenance=excluded.provenance""",
        (
            order_id,
            flags["merchandise_proceeds_known"],
            flags["shipping_collected_known"],
            flags["marketplace_fees_known"],
            flags["actual_shipping_cost_known"],
            utcnow(),
            f"{order_type}_SALE_ENTRY_PRESENCE_FLAGS",
        ),
    )


def _sale_known_flags(db: sqlite3.Connection, order: sqlite3.Row, effective: Mapping) -> dict[str, bool]:
    evidence = db.execute(
        "SELECT * FROM jarvis_sale_input_evidence WHERE order_id=?", (order["id"],)
    ).fetchone()

    def known(column: str, amount_key: str) -> bool:
        # A non-zero recorded amount is independently trustworthy for legacy
        # orders with no presence ledger.  Once a presence row exists, its
        # explicit supplied/omitted fact controls even if the legacy sale row
        # contains a form-default number.
        if evidence:
            return bool(evidence[column] == 1)
        return bool(int(effective[amount_key] or 0))

    return {
        "merchandise": known("merchandise_proceeds_known", "merchandise_cents"),
        "shipping_collected": known("shipping_collected_known", "shipping_cents"),
        "marketplace_fees": known("marketplace_fees_known", "marketplace_fees_cents"),
        "actual_shipping": known("actual_shipping_cost_known", "postage_cents"),
    }


def _card_basis(db: sqlite3.Connection, card: sqlite3.Row) -> dict:
    authoritative = bool(
        card["rip_status"] == "FINALIZED" and int(card["basis_event_count"] or 0) > 0
    )
    if authoritative:
        value = current_card_basis_cents(db, int(card["id"]))
        return _fact(
            value, "DERIVED", record=f"card:{card['id']}",
            field="rip_basis_events + economic_event_entries",
            reason="AUTHORITATIVE_ALLOCATED_BASIS",
        )
    if (
        card["economics_mode"] == "LEGACY"
        and card["batch_total_cost"] is not None
        and float(card["batch_total_cost"]) > 0
        and int(card["batch_card_count"] or 0) > 0
    ):
        total = dollars_to_cents(card["batch_total_cost"])
        stable_ids = [int(row[0]) for row in db.execute(
            "SELECT id FROM cards WHERE batch_id=? ORDER BY id", (card["batch_id"],)
        ).fetchall()]
        estimate = None
        if total is not None and stable_ids:
            estimates = {int(item.stable_id): item.cents for item in allocate_cents(total, stable_ids)}
            estimate = estimates.get(int(card["id"]))
        return _fact(
            estimate, "ESTIMATED", record=f"batch:{card['batch_id']}",
            field="legacy total_cost / stable internal card IDs",
            reason="ESTIMATE_ONLY_COST_BASIS_NOT_FINALIZED",
        )
    return _fact(
        None, "UNRESOLVED", record=f"card:{card['id']}", field="allocated cost basis",
        reason="NO_AUTHORITATIVE_ITEM_ALLOCATION",
    )


def _acquisition_cost(db: sqlite3.Connection, card: sqlite3.Row) -> dict:
    if card["final_usd_paid_cents"] is not None:
        return _fact(
            current_acquisition_cost_cents(db, int(card["batch_id"])), "DERIVED",
            record=f"batch:{card['batch_id']}",
            field="final_usd_paid_cents + audited acquisition corrections",
            reason="AUTHORITATIVE_ACQUISITION_COST",
        )
    if card["economics_mode"] == "LEGACY" and float(card["batch_total_cost"] or 0) > 0:
        return _fact(
            dollars_to_cents(card["batch_total_cost"]), "ESTIMATED",
            record=f"batch:{card['batch_id']}", field="legacy total_cost",
            reason="ESTIMATE_ONLY_COST_NOT_FINALIZED",
        )
    return _fact(
        None, "UNRESOLVED", record=f"batch:{card['batch_id']}",
        field="final_usd_paid_cents", reason="ACQUISITION_COST_UNKNOWN",
    )


def _card_row(db: sqlite3.Connection, sku: str) -> sqlite3.Row:
    row = db.execute(
        """SELECT c.*,b.batch_code,b.economics_mode,b.economics_status,
                  b.total_cost AS batch_total_cost,b.final_usd_paid_cents,
                  b.acquisition_line_id,al.acquisition_id,r.status AS rip_status,
                  COALESCE((SELECT COUNT(*) FROM cards bc WHERE bc.batch_id=c.batch_id),0)
                    AS batch_card_count,
                  COALESCE((SELECT COUNT(*) FROM rip_basis_events rbe
                             WHERE rbe.card_id=c.id AND rbe.target_type='CARD'),0)
                  + COALESCE((SELECT COUNT(*) FROM economic_event_entries eee
                              WHERE eee.target_id=c.id AND eee.target_type='CARD'
                                AND eee.entry_type='BASIS'),0) AS basis_event_count
             FROM cards c
             JOIN batches b ON b.id=c.batch_id
             LEFT JOIN acquisition_lines al ON al.id=b.acquisition_line_id
             LEFT JOIN rip_sessions r ON r.id=c.rip_session_id
            WHERE c.sku=?""",
        (sku,),
    ).fetchone()
    if not row:
        raise ValueError("Card not found")
    return row


def sale_economics_payload(db: sqlite3.Connection, order_id: int) -> dict:
    order = db.execute("SELECT * FROM sale_orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        raise ValueError("Sale order not found")
    detail = post_sale_order_payload(db, order_id)
    effective = financial_facts(db, order_id)["effective"]
    known = _sale_known_flags(db, order, effective)
    merchandise = int(effective["merchandise_cents"]) if known["merchandise"] else None
    shipping = int(effective["shipping_cents"]) if known["shipping_collected"] else None
    fees = int(effective["marketplace_fees_cents"]) if known["marketplace_fees"] else None
    postage = int(effective["postage_cents"]) if known["actual_shipping"] else None
    gross = merchandise + shipping if merchandise is not None and shipping is not None else None
    net = (
        merchandise + shipping - fees - postage + int(effective["other_net_cents"])
        if None not in (merchandise, shipping, fees, postage) else None
    )
    basis = detail["sold_basis_cents"] if detail["sold_basis_complete"] else None
    profit = net - int(basis) if net is not None and basis is not None else None
    required_known = [known["merchandise"], known["shipping_collected"], known["marketplace_fees"], known["actual_shipping"], basis is not None]
    if order["canceled_at"]:
        status = "UNRESOLVED"
    elif all(required_known):
        status = "COMPLETE"
    elif any(required_known):
        status = "PARTIAL"
    else:
        status = "UNRESOLVED"
    warnings = []
    for key, is_known in known.items():
        if not is_known:
            warnings.append(f"{key.upper()}_UNKNOWN")
    if basis is None:
        warnings.append("SOLD_BASIS_UNKNOWN")
    if order["canceled_at"]:
        warnings.append("CANCELED_ORDER_EXCLUDED")
    return {
        "calculation_version": CALCULATION_VERSION,
        "calculated_at": utcnow(),
        "economics_status": status,
        "order": {
            "id": int(order["id"]), "order_type": order["order_type"],
            "order_number": order["order_number"], "platform": order["platform"],
            "sold_at": order["sold_at"], "canceled": bool(order["canceled_at"]),
            "quantity_sold": len(detail["items"]),
        },
        "items": [
            {
                "sale_item_id": item["sale_item_id"],
                "inventory_type": item["item_type"],
                "inventory_id": item["identifier"],
                "batch_code": item["batch_code"],
                "basis_cents": item["basis_cents"],
                "returned": item["returned"],
            }
            for item in detail["items"]
        ],
        "gross_merchandise_proceeds": _fact(
            merchandise, "RECORDED" if merchandise is not None else "UNRESOLVED",
            record=f"sale_order:{order_id}", field="effective merchandise + explicit input evidence",
            observed_at=order["sold_at"],
            reason="" if merchandise is not None else "MERCHANDISE_PROCEEDS_UNKNOWN",
        ),
        "shipping_charged_to_buyer": _fact(
            shipping, "RECORDED" if shipping is not None else "UNRESOLVED",
            record=f"sale_order:{order_id}", field="effective shipping_collected + explicit input evidence",
            observed_at=order["sold_at"],
            reason="" if shipping is not None else "SHIPPING_COLLECTED_UNKNOWN",
        ),
        "gross_sale_proceeds": _fact(
            gross, "DERIVED" if gross is not None else "UNRESOLVED",
            record=f"sale_order:{order_id}", field="merchandise + shipping collected",
            observed_at=order["sold_at"],
            reason="" if gross is not None else "GROSS_PROCEEDS_INPUT_UNKNOWN",
        ),
        "marketplace_fees": _fact(
            fees, "RECORDED" if fees is not None else "UNRESOLVED",
            record=f"sale_order:{order_id}", field="effective marketplace fees + explicit input evidence",
            observed_at=order["sold_at"],
            reason="" if fees is not None else "MARKETPLACE_FEES_UNKNOWN",
        ),
        "payment_transaction_fees": _fact(
            None, "UNRESOLVED", record=f"sale_order:{order_id}",
            field="not separately supported", reason="NOT_SEPARATELY_RECORDED", required=False,
        ),
        "actual_shipping_cost": _fact(
            postage, "RECORDED" if postage is not None else "UNRESOLVED",
            record=f"sale_order:{order_id}", field="effective actual postage + explicit input evidence",
            observed_at=order["sold_at"],
            reason="" if postage is not None else "ACTUAL_SHIPPING_COST_UNKNOWN",
        ),
        "packaging_fulfillment_cost": _fact(
            None, "UNRESOLVED", record=f"sale_order:{order_id}",
            field="not supported in this release", reason="NOT_RECORDED", required=False,
        ),
        "other_direct_sale_cost": _fact(
            None, "UNRESOLVED", record=f"sale_order:{order_id}",
            field="not supported in this release", reason="NOT_RECORDED", required=False,
        ),
        "other_net_adjustment": _fact(
            int(effective["other_net_cents"]), "DERIVED", record=f"sale_order:{order_id}",
            field="effective post-sale event entries", required=False,
        ),
        "net_proceeds": _fact(
            net, "DERIVED" if net is not None else "UNRESOLVED",
            record=f"sale_order:{order_id}",
            field="gross sale proceeds - fees - actual shipping + other net adjustments",
            reason="" if net is not None else "REQUIRED_SALE_INPUT_UNKNOWN",
        ),
        "cost_basis_of_goods_sold": _fact(
            int(basis) if basis is not None else None,
            "DERIVED" if basis is not None else "UNRESOLVED",
            record=f"sale_order:{order_id}", field="active exact item basis",
            reason="" if basis is not None else "SOLD_BASIS_UNKNOWN",
        ),
        "realized_profit_loss": _fact(
            profit, "DERIVED" if profit is not None else "UNRESOLVED",
            record=f"sale_order:{order_id}", field="net proceeds - sold basis",
            reason="" if profit is not None else "REQUIRED_PROFIT_INPUT_UNKNOWN",
        ),
        "realized_roi": _roi(profit, int(basis) if basis is not None else None),
        "warnings": warnings,
        "source_records_immutable": True,
    }


def card_economics_payload(db: sqlite3.Connection, sku: str) -> dict:
    card = _card_row(db, sku)
    basis = _card_basis(db, card)
    acquisition = _acquisition_cost(db, card)
    market_cents = dollars_to_cents(card["market_average"])
    market = _fact(
        market_cents, "RECORDED" if market_cents is not None else "UNRESOLVED",
        record=f"card:{card['id']}", field="market_average",
        observed_at=card["market_updated_at"],
        reason="" if market_cents is not None else "MARKET_VALUE_UNKNOWN",
    )
    market["freshness"] = valuation_freshness(card["market_updated_at"])
    remaining = card["status"] in ACTIVE_INVENTORY_STATES and card["recycled_at"] is None
    inventory_value = market_cents if remaining else None
    basis_value = basis["value_cents"] if basis["state"] != "UNRESOLVED" else None
    unrealized = inventory_value - int(basis_value) if inventory_value is not None and basis_value is not None else None
    if basis["state"] == "ESTIMATED":
        status = "ESTIMATED"
    elif basis_value is not None and market_cents is not None:
        status = "COMPLETE"
    elif basis_value is not None or market_cents is not None:
        status = "PARTIAL"
    else:
        status = "UNRESOLVED"
    sale_items = db.execute(
        """SELECT si.id,si.order_id,o.canceled_at FROM sale_items si
             JOIN sale_orders o ON o.id=si.order_id WHERE si.card_id=? ORDER BY si.id""",
        (card["id"],),
    ).fetchall()
    sale = sale_economics_payload(db, int(sale_items[-1]["order_id"])) if sale_items else None
    return {
        "calculation_version": CALCULATION_VERSION,
        "calculated_at": utcnow(),
        "economics_status": sale["economics_status"] if card["status"] == "SOLD" and sale else status,
        "inventory": {
            "card_id": int(card["id"]), "sku": card["sku"],
            "acquisition_id": card["acquisition_id"],
            "acquisition_line_id": card["acquisition_line_id"],
            "batch_id": int(card["batch_id"]), "batch_code": card["batch_code"],
            "quantity": 1, "status": card["status"], "remaining": remaining,
        },
        "acquisition_cost": acquisition,
        "allocated_acquisition_cost": basis,
        "cost_basis_per_unit": basis,
        "current_market_reference_value": market,
        "current_inventory_value": _fact(
            inventory_value, "DERIVED" if inventory_value is not None else "UNRESOLVED",
            record=f"card:{card['id']}", field="quantity * market_average",
            observed_at=card["market_updated_at"],
            reason="" if inventory_value is not None else (
                "ITEM_NOT_REMAINING" if not remaining else "MARKET_VALUE_UNKNOWN"
            ),
        ),
        "unrealized_gain_loss": _fact(
            unrealized,
            "ESTIMATED" if unrealized is not None and basis["state"] == "ESTIMATED"
            else "DERIVED" if unrealized is not None else "UNRESOLVED",
            record=f"card:{card['id']}", field="current inventory value - remaining basis",
            reason="" if unrealized is not None else "REQUIRED_UNREALIZED_INPUT_UNKNOWN",
        ),
        "unrealized_roi": _roi(unrealized, int(basis_value) if basis_value is not None else None),
        "sale": sale,
        "warnings": [
            fact["reason"] for fact in (acquisition, basis, market)
            if fact["state"] in ("UNRESOLVED", "ESTIMATED") and fact["reason"]
        ],
        "source_records_immutable": True,
    }


def aggregate_economics_payload(db: sqlite3.Connection) -> dict:
    inventory_record_count = int(db.execute("SELECT COUNT(*) FROM cards").fetchone()[0])
    rows = db.execute(
        """SELECT c.id,c.batch_id,c.status,c.recycled_at,c.market_average,c.market_updated_at,
                  b.economics_mode,b.total_cost AS batch_total_cost,
                  r.status AS rip_status,
                  COALESCE((SELECT COUNT(*) FROM cards bc WHERE bc.batch_id=c.batch_id),0)
                    AS batch_card_count,
                  COALESCE((SELECT COUNT(*) FROM rip_basis_events rbe
                             WHERE rbe.card_id=c.id AND rbe.target_type='CARD'),0)
                  + COALESCE((SELECT COUNT(*) FROM economic_event_entries eee
                              WHERE eee.target_id=c.id AND eee.target_type='CARD'
                                AND eee.entry_type='BASIS'),0) AS basis_event_count
             FROM cards c JOIN batches b ON b.id=c.batch_id
             LEFT JOIN rip_sessions r ON r.id=c.rip_session_id
            WHERE c.recycled_at IS NULL AND c.status IN ('IN_STOCK','REVIEW','HOLD')
            ORDER BY c.id"""
    ).fetchall()
    known_basis = 0
    known_market = 0
    paired_gain = 0
    authoritative_basis_count = 0
    estimated_basis_count = 0
    market_count = 0
    market_timestamp_count = 0
    latest_market_observed_at = None
    freshness_counts = {"CURRENT": 0, "AGING": 0, "STALE": 0, "UNKNOWN": 0}
    paired_count = 0
    for row in rows:
        if row["rip_status"] == "FINALIZED" and int(row["basis_event_count"] or 0) > 0:
            basis = current_card_basis_cents(db, int(row["id"]))
            known_basis += basis
            authoritative_basis_count += 1
        elif row["economics_mode"] == "LEGACY" and float(row["batch_total_cost"] or 0) > 0 and int(row["batch_card_count"] or 0) > 0:
            total = dollars_to_cents(row["batch_total_cost"])
            basis = None if total is None else total // int(row["batch_card_count"])
            estimated_basis_count += 1
        else:
            basis = None
        market = dollars_to_cents(row["market_average"])
        if market is not None:
            known_market += market
            market_count += 1
            freshness = valuation_freshness(row["market_updated_at"])
            freshness_counts[freshness["state"]] += 1
            if row["market_updated_at"]:
                market_timestamp_count += 1
                if latest_market_observed_at is None or row["market_updated_at"] > latest_market_observed_at:
                    latest_market_observed_at = row["market_updated_at"]
        if basis is not None and market is not None and row["rip_status"] == "FINALIZED":
            paired_gain += market - basis
            paired_count += 1
    order_ids = [int(row[0]) for row in db.execute(
        "SELECT id FROM sale_orders WHERE canceled_at IS NULL ORDER BY id"
    ).fetchall()]
    sale_reports = [sale_economics_payload(db, order_id) for order_id in order_ids]
    complete_sales = [item for item in sale_reports if item["economics_status"] == "COMPLETE"]
    realized_revenue = sum(int(item["gross_sale_proceeds"]["value_cents"]) for item in complete_sales)
    realized_profit = sum(int(item["realized_profit_loss"]["value_cents"]) for item in complete_sales)
    total = len(rows)
    incomplete_count = total - paired_count
    return {
        "calculation_version": CALCULATION_VERSION,
        "calculated_at": utcnow(),
        "economics_status": "UNRESOLVED" if not rows and not sale_reports
        else "COMPLETE" if incomplete_count == 0 and len(complete_sales) == len(sale_reports)
        else "PARTIAL",
        "remaining_inventory": {
            "item_count": total,
            "authoritative_basis_count": authoritative_basis_count,
            "estimated_basis_count": estimated_basis_count,
            "unresolved_basis_count": total - authoritative_basis_count - estimated_basis_count,
            "market_valued_count": market_count,
            "paired_authoritative_count": paired_count,
            "total_remaining_cost_basis_cents": known_basis if authoritative_basis_count or inventory_record_count else None,
            "total_current_inventory_value_cents": known_market if market_count or (inventory_record_count and not rows) else None,
            "total_unrealized_gain_loss_cents": paired_gain if paired_count or (inventory_record_count and not rows) else None,
            "coverage_label": f"{paired_count}/{total} remaining items have authoritative basis and market value",
            "valuation_freshness": {
                "known_timestamp_count": market_timestamp_count,
                "unknown_timestamp_count": market_count - market_timestamp_count,
                "latest_observed_at": latest_market_observed_at,
                "state_counts": freshness_counts,
                "label": (
                    f"{freshness_counts['CURRENT']} current · {freshness_counts['AGING']} aging · "
                    f"{freshness_counts['STALE']} stale · {freshness_counts['UNKNOWN']} freshness unknown"
                    if market_count else "Freshness Unknown"
                ),
            },
            "estimated_basis_excluded": True,
        },
        "realized": {
            "active_order_count": len(sale_reports),
            "complete_order_count": len(complete_sales),
            "unresolved_order_count": len(sale_reports) - len(complete_sales),
            "total_realized_revenue_cents": realized_revenue if complete_sales else None,
            "total_realized_profit_loss_cents": realized_profit if complete_sales else None,
            "coverage_label": f"{len(complete_sales)}/{len(sale_reports)} active orders have complete simplified economics",
        },
        "warnings": [warning for warning in (
            "No authoritative simplified economics records are available."
            if not rows and not sale_reports else None,
            "Known aggregates exclude unresolved and estimated item economics."
            if incomplete_count else None,
            "Realized aggregates exclude orders with unresolved required inputs."
            if len(complete_sales) != len(sale_reports) else None,
        ) if warning],
        "source_records_immutable": True,
    }
