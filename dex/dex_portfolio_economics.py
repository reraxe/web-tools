"""Phase 7C read-only portfolio Operational Economics.

The portfolio is derived from finalized batch facts, stable sale-item attribution,
the Phase 7A correction ledger, and Phase 7B effective post-sale facts. No
calculated portfolio value is persisted.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime, timezone

from dex_batch_economics import (
    GROUP_NOTICE,
    ORDER_ATTRIBUTION_NOTICE,
    batch_economics_core_payload,
    card_sale_item_allocations,
)
from dex_economics import CALCULATION_VERSION, allocate_weighted_cents
from dex_post_sale import active_returned_sale_items, financial_facts


PORTFOLIO_SCOPE_NOTICE = (
    "Portfolio totals include Finalized Economics only. Legacy estimates and "
    "authoritative-but-unfinalized batches remain separate and are not blended."
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _allocated(total: int, weighted_ids: list[tuple[int, int]]) -> dict[int, int]:
    return {int(item.stable_id): item.cents for item in allocate_weighted_cents(total, weighted_ids)}


def _combine_valuation(reports: list[dict], key: str) -> dict:
    values = [report["remaining"][key] for report in reports]
    valued = sum(int(value["valued_count"]) for value in values)
    total = sum(int(value["total_count"]) for value in values)
    timestamps = [value["freshness"] for value in values if value["freshness"]]
    freshness_unknown = any(value["valued_count"] and not value["freshness"] for value in values)
    freshness = min(timestamps) if timestamps and not freshness_unknown else None
    quantity_unknown = any(bool(value["quantity_unknown"]) for value in values)
    complete = bool(reports) and all(bool(value["complete"]) for value in values)
    return {
        "known_value_cents": sum(int(value["known_value_cents"]) for value in values),
        "valued_count": valued,
        "total_count": total,
        "quantity_unknown": quantity_unknown,
        "complete": complete,
        "freshness": freshness,
        "freshness_label": freshness or "Freshness Unknown",
        "coverage_label": (
            f"{valued}/{total} remaining inventory items valued"
            + ("; additional bulk quantity unknown" if quantity_unknown else "")
        ),
    }


def _sale_item_rows(db: sqlite3.Connection, order_ids: set[int]) -> list[sqlite3.Row]:
    if not order_ids:
        return []
    placeholders = ",".join("?" for _ in order_ids)
    return db.execute(
        f"""SELECT si.id AS sale_item_id, si.order_id, c.id AS card_id,
                   c.batch_id, c.sku, r.status AS rip_status,
                   COALESCE((SELECT SUM(rbe.amount_delta_cents)
                               FROM rip_basis_events rbe
                              WHERE rbe.card_id=c.id AND rbe.target_type='CARD'),0)
                     + COALESCE((SELECT SUM(eee.amount_delta_cents)
                                   FROM economic_event_entries eee
                                  WHERE eee.entry_type='BASIS'
                                    AND eee.target_type='CARD' AND eee.target_id=c.id),0)
                       AS current_basis_cents,
                   (EXISTS(SELECT 1 FROM rip_basis_events rbe
                            WHERE rbe.card_id=c.id AND rbe.target_type='CARD')
                    OR EXISTS(SELECT 1 FROM economic_event_entries eee
                               WHERE eee.entry_type='BASIS'
                                 AND eee.target_type='CARD' AND eee.target_id=c.id))
                       AS basis_event_exists
              FROM sale_items si
              JOIN cards c ON c.id=si.card_id
              LEFT JOIN rip_sessions r ON r.id=c.rip_session_id
             WHERE si.order_id IN ({placeholders})
             ORDER BY si.order_id, si.id""",
        tuple(sorted(order_ids)),
    ).fetchall()


def _sealed_sale_item_rows(db: sqlite3.Connection, order_ids: set[int]) -> list[sqlite3.Row]:
    if not order_ids:
        return []
    placeholders = ",".join("?" for _ in order_ids)
    return db.execute(
        f"""SELECT ssi.id AS sale_item_id, ssi.order_id, ssi.batch_id,
                   ssi.sealed_unit_id, ssi.merchandise_amount_cents,
                   su.unit_code,
                   su.basis_cents + COALESCE((SELECT SUM(eee.amount_delta_cents)
                                                FROM economic_event_entries eee
                                               WHERE eee.entry_type='BASIS'
                                                 AND eee.target_type='SEALED_UNIT'
                                                 AND eee.target_id=su.id),0)
                     AS current_basis_cents
              FROM sealed_sale_items ssi
              JOIN sealed_units su ON su.id=ssi.sealed_unit_id
             WHERE ssi.order_id IN ({placeholders})
             ORDER BY ssi.order_id, ssi.id""",
        tuple(sorted(order_ids)),
    ).fetchall()


def _portfolio_sales(db: sqlite3.Connection, finalized_batch_ids: set[int]) -> dict:
    orders = db.execute(
        """SELECT id, COALESCE(order_type,'CARD') AS order_type, canceled_at
             FROM sale_orders ORDER BY id"""
    ).fetchall()
    active = [row for row in orders if not row["canceled_at"]]
    active_ids = {int(row["id"]) for row in active}
    card_order_ids = {int(row["id"]) for row in active if row["order_type"] == "CARD"}
    sealed_order_ids = {int(row["id"]) for row in active if row["order_type"] == "SEALED"}
    returned = active_returned_sale_items(db, active_ids)
    card_allocations = card_sale_item_allocations(db, card_order_ids)
    card_rows = _sale_item_rows(db, card_order_ids)
    sealed_rows = _sealed_sale_item_rows(db, sealed_order_ids)

    component_totals = {
        "gross_merchandise_cents": 0,
        "shipping_collected_cents": 0,
        "marketplace_fees_cents": 0,
        "actual_postage_cents": 0,
        "other_net_cents": 0,
        "net_proceeds_cents": 0,
    }
    known_basis = 0
    basis_known_count = 0
    basis_total_count = 0
    active_sold_card_count = 0
    active_sold_sealed_count = 0
    returned_card_count = 0
    returned_sealed_count = 0
    included_item_keys: set[tuple[str, int]] = set()
    duplicate_attribution_count = 0
    order_batches: dict[int, set[int]] = defaultdict(set)
    contributing_orders: set[int] = set()
    order_attributable_net: dict[int, int] = defaultdict(int)

    def include_allocation(item_type: str, item_id: int, order_id: int, batch_id: int, allocation: dict) -> bool:
        nonlocal duplicate_attribution_count
        order_batches[order_id].add(batch_id)
        if batch_id not in finalized_batch_ids:
            return False
        key = (item_type, item_id)
        if key in included_item_keys:
            duplicate_attribution_count += 1
            return False
        included_item_keys.add(key)
        contributing_orders.add(order_id)
        component_totals["gross_merchandise_cents"] += int(allocation["gross_cents"])
        component_totals["shipping_collected_cents"] += int(allocation["shipping_cents"])
        component_totals["marketplace_fees_cents"] += int(allocation["fees_cents"])
        component_totals["actual_postage_cents"] += int(allocation["postage_cents"])
        component_totals["other_net_cents"] += int(allocation["other_net_cents"])
        component_totals["net_proceeds_cents"] += int(allocation["net_cents"])
        order_attributable_net[order_id] += int(allocation["net_cents"])
        return True

    for row in card_rows:
        item_id = int(row["sale_item_id"])
        order_id = int(row["order_id"])
        batch_id = int(row["batch_id"])
        allocation = card_allocations.get(item_id)
        if not allocation or not include_allocation("CARD", item_id, order_id, batch_id, allocation):
            continue
        if returned.get(("CARD", item_id)):
            returned_card_count += 1
            continue
        basis_total_count += 1
        active_sold_card_count += 1
        if row["rip_status"] == "FINALIZED" and row["basis_event_exists"]:
            basis_known_count += 1
            known_basis += int(row["current_basis_cents"] or 0)

    sealed_by_order: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for row in sealed_rows:
        sealed_by_order[int(row["order_id"])].append(row)
        order_batches[int(row["order_id"])].add(int(row["batch_id"]))
    for order_id, items in sealed_by_order.items():
        effective = financial_facts(db, order_id)["effective"]
        weights = [(int(row["sale_item_id"]), int(row["merchandise_amount_cents"])) for row in items]
        component_allocations = {
            "gross_cents": _allocated(int(effective["merchandise_cents"]), weights),
            "shipping_cents": _allocated(int(effective["shipping_cents"]), weights),
            "fees_cents": _allocated(int(effective["marketplace_fees_cents"]), weights),
            "postage_cents": _allocated(int(effective["postage_cents"]), weights),
            "other_net_cents": _allocated(int(effective["other_net_cents"]), weights),
            "net_cents": _allocated(int(effective["net_proceeds_cents"]), weights),
        }
        for row in items:
            item_id = int(row["sale_item_id"])
            allocation = {name: values[item_id] for name, values in component_allocations.items()}
            if not include_allocation(
                "SEALED_UNIT", item_id, order_id, int(row["batch_id"]), allocation
            ):
                continue
            if returned.get(("SEALED_UNIT", item_id)):
                returned_sealed_count += 1
                continue
            basis_total_count += 1
            basis_known_count += 1
            active_sold_sealed_count += 1
            known_basis += int(row["current_basis_cents"])

    source_order_net = {
        order_id: int(financial_facts(db, order_id)["effective"]["net_proceeds_cents"])
        for order_id in contributing_orders
    }
    fully_scoped = {
        order_id for order_id in contributing_orders
        if order_batches[order_id] and order_batches[order_id].issubset(finalized_batch_ids)
    }
    partial_scope = contributing_orders - fully_scoped
    fully_scoped_difference = sum(
        order_attributable_net[order_id] - source_order_net[order_id]
        for order_id in fully_scoped
    )
    basis_complete = basis_known_count == basis_total_count
    canceled_order_count = 0
    if finalized_batch_ids:
        placeholders = ",".join("?" for _ in finalized_batch_ids)
        parameters = tuple(sorted(finalized_batch_ids)) * 2
        canceled_order_count = int(
            db.execute(
                f"""SELECT COUNT(DISTINCT so.id)
                       FROM sale_orders so
                      WHERE so.canceled_at IS NOT NULL
                        AND (
                          EXISTS (SELECT 1
                                    FROM sale_items si
                                    JOIN cards c ON c.id=si.card_id
                                   WHERE si.order_id=so.id
                                     AND c.batch_id IN ({placeholders}))
                          OR EXISTS (SELECT 1
                                       FROM sealed_sale_items ssi
                                      WHERE ssi.order_id=so.id
                                        AND ssi.batch_id IN ({placeholders}))
                        )""",
                parameters,
            ).fetchone()[0]
        )
    return {
        **component_totals,
        "known_sold_basis_cents": known_basis,
        "sold_basis_cents": known_basis if basis_complete else None,
        "sold_basis_known_count": basis_known_count,
        "sold_basis_total_count": basis_total_count,
        "sold_basis_complete": basis_complete,
        "realized_profit_loss_cents": component_totals["net_proceeds_cents"] - known_basis if basis_complete else None,
        "active_sold_card_count": active_sold_card_count,
        "active_sold_sealed_unit_count": active_sold_sealed_count,
        "active_returned_card_count": returned_card_count,
        "active_returned_sealed_unit_count": returned_sealed_count,
        "unique_order_count": len(contributing_orders),
        "fully_scoped_order_count": len(fully_scoped),
        "partial_scope_order_count": len(partial_scope),
        "partial_scope_order_ids": sorted(partial_scope),
        "canceled_order_count": canceled_order_count,
        "attributed_item_count": len(included_item_keys),
        "duplicate_attribution_count": duplicate_attribution_count,
        "fully_scoped_order_difference_cents": fully_scoped_difference,
        "allocation_notice": ORDER_ATTRIBUTION_NOTICE,
    }


def portfolio_economics_payload(db: sqlite3.Connection) -> dict:
    batch_ids = [
        int(row[0])
        for row in db.execute(
            "SELECT id FROM batches WHERE recycled_at IS NULL ORDER BY id"
        ).fetchall()
    ]
    reports = [batch_economics_core_payload(db, batch_id) for batch_id in batch_ids]
    finalized = [
        report for report in reports
        if report["authoritative"] and report["batch"]["economics_status"] == "FINALIZED"
    ]
    unfinalized = [
        report for report in reports
        if report["authoritative"] and report["batch"]["economics_status"] != "FINALIZED"
    ]
    legacy = [report for report in reports if not report["authoritative"]]
    finalized_ids = {int(report["batch"]["id"]) for report in finalized}
    sales = _portfolio_sales(db, finalized_ids)
    market = _combine_valuation(finalized, "market")
    listed = _combine_valuation(finalized, "listed")

    cost = sum(int(report["acquisition"]["authoritative_cost_cents"]) for report in finalized)
    operational_loss = sum(int(report["excluded"]["operational_loss_cents"]) for report in finalized)
    remaining_basis = sum(int(report["remaining"]["known_basis_cents"]) for report in finalized)
    excluded_basis = sum(int(report["excluded"]["known_basis_cents"]) for report in finalized)
    net = int(sales["net_proceeds_cents"])
    recovery = None if cost == 0 else round(net * 100 / cost, 2)
    current_position = net + int(market["known_value_cents"]) - cost
    projected_position = net + int(listed["known_value_cents"]) - cost

    active_cards = sum(int(report["remaining"]["active_card_count"]) for report in finalized)
    remaining_sealed = sum(int(report["remaining"]["remaining_sealed_unit_count"]) for report in finalized)
    known_bulk = sum(int(report["remaining"]["known_bulk_quantity"]) for report in finalized)
    bulk_quantity_unknown = any(bool(report["remaining"]["bulk_quantity_unknown"]) for report in finalized)
    market_card_valued = sum(int(report["remaining"]["market"]["valued_count"]) for report in finalized)
    listed_card_valued = sum(int(report["remaining"]["listed"]["valued_count"]) for report in finalized)
    sealed_counts = {
        key: sum(int(report["reconciliation"]["sealed_quantity"][key]) for report in finalized)
        for key in ("acquired", "opened", "sold", "remaining", "corrected_adjusted")
    }

    batch_net = sum(int(report["realized"]["net_proceeds_cents"]) for report in finalized)
    batch_cost = sum(int(report["reconciliation"]["basis"]["authoritative_cost_cents"]) for report in finalized)
    unreconciled_batches = [
        report["batch"]["batch_code"] for report in finalized
        if not report["reconciliation"]["basis"]["reconciled"]
        or (
            report["reconciliation"]["sealed_quantity"]["applicable"]
            and not report["reconciliation"]["sealed_quantity"]["reconciled"]
        )
    ]
    groups: dict[str, list[str]] = defaultdict(list)
    for report in finalized:
        reference = report["batch"]["receipt_group_reference"]
        if reference:
            groups[reference].append(report["batch"]["batch_code"])

    warnings: list[dict[str, str]] = []
    if not finalized:
        warnings.append({"code": "NO_FINALIZED_ECONOMICS", "severity": "material", "message": "No batch has Finalized Economics, so authoritative portfolio totals are empty."})
    if unfinalized:
        warnings.append({"code": "UNFINALIZED_BATCHES_EXCLUDED", "severity": "info", "message": f"{len(unfinalized)} authoritative batch(es) are not finalized and are excluded from portfolio totals."})
    if legacy:
        warnings.append({"code": "LEGACY_ESTIMATES_SEPARATE", "severity": "info", "message": f"{len(legacy)} legacy estimate-only batch(es) remain separate from authoritative totals."})
    if not sales["sold_basis_complete"]:
        warnings.append({"code": "SOLD_BASIS_INCOMPLETE", "severity": "material", "message": "Active sold basis is incomplete, so portfolio Realized P/L is Unknown."})
    if not market["complete"]:
        warnings.append({"code": "MARKET_VALUE_INCOMPLETE", "severity": "material", "message": "Unknown remaining market values make Current Economic Position incomplete."})
    if not listed["complete"]:
        warnings.append({"code": "LISTED_VALUE_INCOMPLETE", "severity": "material", "message": "Unknown remaining listed values make Projected Listed Position incomplete."})
    if remaining_sealed:
        warnings.append({"code": "SEALED_VALUE_UNKNOWN", "severity": "material", "message": "Remaining sealed inventory has no authoritative valuation fact and remains Unknown."})
    if bulk_quantity_unknown:
        warnings.append({"code": "BULK_QUANTITY_UNKNOWN", "severity": "material", "message": "One or more finalized bulk reserves have unknown physical quantity."})
    if operational_loss:
        warnings.append({"code": "OPERATIONAL_LOSS_RECORDED", "severity": "info", "message": "Operational losses/dispositions are reported separately; DEX makes no tax conclusion."})
    if sales["canceled_order_count"]:
        warnings.append({"code": "CANCELED_SALES_EXCLUDED", "severity": "info", "message": "Canceled/undone orders remain in history and are excluded from realized totals."})
    if sales["partial_scope_order_count"]:
        warnings.append({"code": "PARTIAL_FINALIZED_ORDER_ATTRIBUTION", "severity": "info", "message": "Cross-batch orders spanning excluded batches contribute only their stable Finalized Economics portion."})
    if unreconciled_batches:
        warnings.append({"code": "BATCH_RECONCILIATION_GAP", "severity": "material", "message": f"{len(unreconciled_batches)} finalized batch(es) have a basis or quantity reconciliation gap."})
    if sales["duplicate_attribution_count"] or sales["fully_scoped_order_difference_cents"]:
        warnings.append({"code": "ORDER_ATTRIBUTION_DIFFERENCE", "severity": "material", "message": "Stable order attribution did not reconcile exactly."})

    valuation_complete = bool(finalized) and market["complete"] and listed["complete"]
    return {
        "calculation_version": CALCULATION_VERSION,
        "generated_at": utcnow(),
        "state": "FINALIZED_ECONOMICS_ONLY",
        "title": "Operational Economics",
        "scope_notice": PORTFOLIO_SCOPE_NOTICE,
        "tax_notice": "Operational reporting only. DEX does not calculate tax/accounting profit or determine deductions.",
        "scope": {
            "total_batch_count": len(reports),
            "finalized_batch_count": len(finalized),
            "authoritative_unfinalized_batch_count": len(unfinalized),
            "legacy_estimate_batch_count": len(legacy),
            "finalized_batch_ids": sorted(finalized_ids),
            "excluded_unfinalized_batch_codes": [report["batch"]["batch_code"] for report in unfinalized],
            "legacy_estimate_batch_codes": [report["batch"]["batch_code"] for report in legacy],
        },
        "summary": {
            "authoritative_acquisition_cost_cents": cost,
            "effective_realized_net_proceeds_cents": net,
            "active_sold_basis_cents": sales["sold_basis_cents"],
            "realized_profit_loss_cents": sales["realized_profit_loss_cents"],
            "operational_loss_cents": operational_loss,
            "known_remaining_market_value_cents": market["known_value_cents"],
            "known_remaining_listed_value_cents": listed["known_value_cents"],
            "current_economic_position_cents": current_position,
            "current_position_complete": bool(finalized) and market["complete"],
            "projected_listed_position_cents": projected_position,
            "projected_listed_position_complete": bool(finalized) and listed["complete"],
            "cost_recovery_percent": recovery,
            "valuation_complete": valuation_complete,
        },
        "acquisition": {
            "authoritative_cost_cents": cost,
            "reporting_currency": "USD",
            "definition": "Sum of current authoritative acquisition cost for Finalized Economics batches only.",
        },
        "realized": {
            **sales,
            "cost_recovery_percent": recovery,
            "cost_recovery_definition": "effective realized net proceeds ÷ authoritative acquisition cost",
            "realized_profit_loss_definition": "effective realized net proceeds − active sold basis",
            "marketplace_tax_treatment": "Marketplace-collected sales tax is excluded from revenue and P/L.",
        },
        "remaining": {
            "known_basis_cents": remaining_basis,
            "active_card_count": active_cards,
            "remaining_sealed_unit_count": remaining_sealed,
            "known_bulk_quantity": known_bulk,
            "bulk_quantity_unknown": bulk_quantity_unknown,
            "market": {
                **market,
                "cards": {"valued_count": market_card_valued, "total_count": active_cards, "complete": market_card_valued == active_cards},
                "sealed": {"valued_count": 0, "total_count": remaining_sealed, "complete": remaining_sealed == 0, "state": "UNKNOWN" if remaining_sealed else "NOT_APPLICABLE"},
            },
            "listed": {
                **listed,
                "cards": {"valued_count": listed_card_valued, "total_count": active_cards, "complete": listed_card_valued == active_cards},
                "sealed": {"valued_count": 0, "total_count": remaining_sealed, "complete": remaining_sealed == 0, "state": "UNKNOWN" if remaining_sealed else "NOT_APPLICABLE"},
            },
            "current_economic_position_cents": current_position,
            "current_position_complete": bool(finalized) and market["complete"],
            "current_position_definition": "effective realized net proceeds + known remaining market value − authoritative acquisition cost",
            "projected_listed_position_cents": projected_position,
            "projected_listed_position_complete": bool(finalized) and listed["complete"],
            "projected_listed_position_definition": "effective realized net proceeds + known remaining listed value − authoritative acquisition cost",
        },
        "excluded": {
            "known_basis_cents": excluded_basis,
            "operational_loss_cents": operational_loss,
            "notice": "Excluded/recycled and adjusted inventory does not inflate active remaining value.",
        },
        "inventory_counts": {
            "remaining_cards": active_cards,
            "active_sold_cards": sales["active_sold_card_count"],
            "active_returned_cards": sales["active_returned_card_count"],
            "sealed_acquired": sealed_counts["acquired"],
            "sealed_opened": sealed_counts["opened"],
            "sealed_sold": sealed_counts["sold"],
            "sealed_remaining": sealed_counts["remaining"],
            "sealed_corrected_adjusted": sealed_counts["corrected_adjusted"],
            "active_sold_sealed_units": sales["active_sold_sealed_unit_count"],
            "active_returned_sealed_units": sales["active_returned_sealed_unit_count"],
            "known_bulk_quantity": known_bulk,
            "bulk_quantity_unknown": bulk_quantity_unknown,
        },
        "receipt_groups": {
            "notice": GROUP_NOTICE,
            "group_count": len(groups),
            "groups": [
                {"reference": reference, "batch_count": len(codes), "batch_codes": codes}
                for reference, codes in sorted(groups.items())
            ],
        },
        "reconciliation": {
            "authoritative_cost": {"portfolio_cents": cost, "batch_sum_cents": batch_cost, "difference_cents": cost - batch_cost, "reconciled": cost == batch_cost},
            "realized_net": {"portfolio_cents": net, "batch_sum_cents": batch_net, "difference_cents": net - batch_net, "reconciled": net == batch_net},
            "stable_order_attribution": {
                "unique_order_count": sales["unique_order_count"],
                "attributed_item_count": sales["attributed_item_count"],
                "duplicate_attribution_count": sales["duplicate_attribution_count"],
                "fully_scoped_order_difference_cents": sales["fully_scoped_order_difference_cents"],
                "reconciled": sales["duplicate_attribution_count"] == 0 and sales["fully_scoped_order_difference_cents"] == 0,
            },
            "unreconciled_batch_codes": unreconciled_batches,
            "materially_incomplete": any(warning["severity"] == "material" for warning in warnings),
        },
        "warnings": warnings,
        "batches": [
            {
                "id": int(report["batch"]["id"]),
                "batch_code": report["batch"]["batch_code"],
                "product_name": report["batch"].get("product_name", ""),
                "receipt_group_reference": report["batch"].get("receipt_group_reference", ""),
                "authoritative_cost_cents": report["acquisition"]["authoritative_cost_cents"],
                "effective_realized_net_proceeds_cents": report["realized"]["net_proceeds_cents"],
                "known_remaining_market_value_cents": report["remaining"]["market"]["known_value_cents"],
                "market_complete": report["remaining"]["market"]["complete"],
                "known_remaining_listed_value_cents": report["remaining"]["listed"]["known_value_cents"],
                "listed_complete": report["remaining"]["listed"]["complete"],
                "operational_loss_cents": report["excluded"]["operational_loss_cents"],
                "materially_incomplete": report["reconciliation"]["materially_incomplete"],
            }
            for report in finalized
        ],
    }


def portfolio_economics_export_rows(db: sqlite3.Connection) -> list[dict]:
    report = portfolio_economics_payload(db)
    summary = report["summary"]
    realized = report["realized"]
    remaining = report["remaining"]
    scope = report["scope"]
    reconciliation = report["reconciliation"]
    return [{
        "calculation_version": report["calculation_version"],
        "generated_at": report["generated_at"],
        "economics_state": report["state"],
        "finalized_batch_count": scope["finalized_batch_count"],
        "authoritative_unfinalized_batch_count": scope["authoritative_unfinalized_batch_count"],
        "legacy_estimate_batch_count": scope["legacy_estimate_batch_count"],
        "authoritative_acquisition_cost_cents": summary["authoritative_acquisition_cost_cents"],
        "effective_realized_merchandise_cents": realized["gross_merchandise_cents"],
        "effective_shipping_collected_cents": realized["shipping_collected_cents"],
        "effective_marketplace_fees_cents": realized["marketplace_fees_cents"],
        "effective_actual_postage_cents": realized["actual_postage_cents"],
        "effective_other_net_cents": realized["other_net_cents"],
        "effective_realized_net_proceeds_cents": summary["effective_realized_net_proceeds_cents"],
        "active_sold_basis_cents": summary["active_sold_basis_cents"],
        "sold_basis_known_count": realized["sold_basis_known_count"],
        "sold_basis_total_count": realized["sold_basis_total_count"],
        "sold_basis_complete": int(realized["sold_basis_complete"]),
        "realized_profit_loss_cents": summary["realized_profit_loss_cents"],
        "cost_recovery_percent": summary["cost_recovery_percent"],
        "operational_loss_cents": summary["operational_loss_cents"],
        "remaining_known_basis_cents": remaining["known_basis_cents"],
        "remaining_card_count": remaining["active_card_count"],
        "remaining_sealed_unit_count": remaining["remaining_sealed_unit_count"],
        "remaining_known_bulk_quantity": remaining["known_bulk_quantity"],
        "bulk_quantity_unknown": int(remaining["bulk_quantity_unknown"]),
        "remaining_market_value_cents": remaining["market"]["known_value_cents"],
        "remaining_market_valued_count": remaining["market"]["valued_count"],
        "remaining_market_total_count": remaining["market"]["total_count"],
        "remaining_market_complete": int(remaining["market"]["complete"]),
        "remaining_market_freshness": remaining["market"]["freshness_label"],
        "remaining_listed_value_cents": remaining["listed"]["known_value_cents"],
        "remaining_listed_valued_count": remaining["listed"]["valued_count"],
        "remaining_listed_total_count": remaining["listed"]["total_count"],
        "remaining_listed_complete": int(remaining["listed"]["complete"]),
        "remaining_listed_freshness": remaining["listed"]["freshness_label"],
        "current_economic_position_cents": summary["current_economic_position_cents"],
        "current_position_complete": int(summary["current_position_complete"]),
        "projected_listed_position_cents": summary["projected_listed_position_cents"],
        "projected_listed_position_complete": int(summary["projected_listed_position_complete"]),
        "unique_order_count": realized["unique_order_count"],
        "attributed_item_count": realized["attributed_item_count"],
        "duplicate_attribution_count": realized["duplicate_attribution_count"],
        "realized_reconciliation_difference_cents": reconciliation["realized_net"]["difference_cents"],
        "materially_incomplete": int(reconciliation["materially_incomplete"]),
        "warning_codes": " | ".join(warning["code"] for warning in report["warnings"]),
        "receipt_group_notice": report["receipt_groups"]["notice"],
    }]
