"""Read-only estimated economics for legacy Dex batches.

Phase 2 deliberately derives estimates from existing facts. It never assigns cost
basis, converts a batch, repairs data, or writes to SQLite.
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Iterator

from dex_economics import CALCULATION_VERSION, allocate_cents, allocate_weighted_cents


ESTIMATE_NOTICE = "Estimate only. Cost basis not finalized."
LEGACY_SALE_NOTICE = (
    "Historical item and batch attribution uses the existing legacy sale split and is estimated."
)


@contextmanager
def open_readonly_database(path: Path) -> Iterator[sqlite3.Connection]:
    """Open an existing SQLite database in enforced read-only/query-only mode."""

    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA query_only = ON")
    try:
        yield connection
    finally:
        connection.close()


def dollars_to_cents(value: object) -> int | None:
    if value is None:
        return None
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None
    return int(amount * 100)


def _valuation(cards: list[sqlite3.Row], field: str, timestamp_field: str | None) -> dict:
    known_values: list[int] = []
    timestamps: list[str] = []
    freshness_unknown = False
    for card in cards:
        cents = dollars_to_cents(card[field])
        if cents is None:
            continue
        known_values.append(cents)
        if timestamp_field:
            timestamp = card[timestamp_field]
            if timestamp:
                timestamps.append(timestamp)
            else:
                freshness_unknown = True
        else:
            freshness_unknown = True
    freshness = None
    if known_values and not freshness_unknown and len(timestamps) == len(known_values):
        freshness = min(timestamps)
    return {
        "known_value_cents": sum(known_values),
        "valued_count": len(known_values),
        "total_count": len(cards),
        "complete": len(known_values) == len(cards),
        "freshness": freshness,
        "freshness_label": freshness if freshness else "Freshness Unknown",
    }


def _order_allocations(connection: sqlite3.Connection, order_ids: set[int]) -> dict[int, dict]:
    if not order_ids:
        return {}
    placeholders = ",".join("?" for _ in order_ids)
    rows = connection.execute(
        f"""
        SELECT si.id AS sale_item_id, si.card_id, si.order_id, si.sale_price,
               c.batch_id, o.subtotal, o.shipping_collected, o.platform_fees,
               o.postage_cost
        FROM sale_items si
        JOIN cards c ON c.id = si.card_id
        JOIN sale_orders o ON o.id = si.order_id
        WHERE si.order_id IN ({placeholders})
        ORDER BY si.order_id, si.id
        """,
        tuple(sorted(order_ids)),
    ).fetchall()
    by_order: dict[int, list[sqlite3.Row]] = {}
    for row in rows:
        by_order.setdefault(row["order_id"], []).append(row)

    allocations: dict[int, dict] = {}
    for order_id, items in by_order.items():
        weights = [
            (row["sale_item_id"], max(0, dollars_to_cents(row["sale_price"]) or 0))
            for row in items
        ]
        order = items[0]
        gross_total = dollars_to_cents(order["subtotal"]) or 0
        net_total = (
            gross_total
            + (dollars_to_cents(order["shipping_collected"]) or 0)
            - (dollars_to_cents(order["platform_fees"]) or 0)
            - (dollars_to_cents(order["postage_cost"]) or 0)
        )
        gross = {item.stable_id: item.cents for item in allocate_weighted_cents(gross_total, weights)}
        net = {item.stable_id: item.cents for item in allocate_weighted_cents(net_total, weights)}
        for row in items:
            allocations[row["sale_item_id"]] = {
                "order_id": order_id,
                "batch_id": row["batch_id"],
                "card_id": row["card_id"],
                "gross_cents": gross[row["sale_item_id"]],
                "net_cents": net[row["sale_item_id"]],
            }
    return allocations


def estimate_legacy_batch(connection: sqlite3.Connection, batch_id: int) -> dict | None:
    """Return a versioned estimate from current facts without mutating them."""

    batch = connection.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
    if not batch:
        return None
    cards = connection.execute(
        """
        SELECT c.*, si.id AS sale_item_id, si.order_id, si.sale_price
        FROM cards c
        LEFT JOIN sale_items si ON si.card_id = c.id
        WHERE c.batch_id = ?
        ORDER BY c.id
        """,
        (batch_id,),
    ).fetchall()

    total_cost_cents = dollars_to_cents(batch["total_cost"])
    cost_known = total_cost_cents is not None and total_cost_cents > 0
    estimated_basis: dict[int, int] = {}
    if cost_known and cards:
        estimated_basis = {
            item.stable_id: item.cents
            for item in allocate_cents(total_cost_cents, [card["id"] for card in cards])
        }

    order_ids = {card["order_id"] for card in cards if card["order_id"] is not None}
    order_allocations = _order_allocations(connection, order_ids)
    realized_items = [
        order_allocations[card["sale_item_id"]]
        for card in cards
        if card["sale_item_id"] in order_allocations
    ]
    gross_cents = sum(item["gross_cents"] for item in realized_items)
    net_cents = sum(item["net_cents"] for item in realized_items)
    sold_basis_cents = (
        sum(estimated_basis.get(card["id"], 0) for card in cards if card["sale_item_id"] in order_allocations)
        if cost_known
        else None
    )

    active_cards = [card for card in cards if card["status"] != "SOLD" and card["recycled_at"] is None]
    recycled_cards = [card for card in cards if card["recycled_at"] is not None]
    active_market = _valuation(active_cards, "market_average", "market_updated_at")
    active_listed = _valuation(active_cards, "listing_price", None)
    recycled_market = _valuation(recycled_cards, "market_average", "market_updated_at")
    recycled_listed = _valuation(recycled_cards, "listing_price", None)
    recycled_basis = (
        sum(estimated_basis.get(card["id"], 0) for card in recycled_cards)
        if cost_known
        else None
    )

    incomplete_sales = [
        card["sku"] for card in cards if card["status"] == "SOLD" and card["sale_item_id"] is None
    ]
    warnings: list[dict[str, str]] = []
    if not cost_known:
        warnings.append({
            "code": "COST_UNKNOWN",
            "severity": "material",
            "message": "Cost Unknown / Incomplete. The recorded legacy total_cost is not trustworthy.",
        })
    if batch["status"] == "OPEN":
        warnings.append({
            "code": "OPEN_BATCH",
            "severity": "material",
            "message": "This batch is still open, so cards or costs may not be fully represented.",
        })
    if not active_market["complete"]:
        warnings.append({
            "code": "MARKET_VALUE_INCOMPLETE",
            "severity": "material",
            "message": "Unknown-priced active cards make remaining market value materially incomplete.",
        })
    if incomplete_sales:
        warnings.append({
            "code": "INCOMPLETE_SALES",
            "severity": "material",
            "message": "One or more sold cards have no complete sale-item history.",
        })
    if recycled_cards:
        warnings.append({
            "code": "RECYCLED_EXCLUDED",
            "severity": "info",
            "message": "Recycled cards are shown separately and excluded from active remaining value.",
        })
    notes = str(batch["notes"] or "")
    if re.search(r"\b(unscanned|bulk|missing|lost)\b", notes, re.I):
        warnings.append({
            "code": "POSSIBLE_UNTRACKED_INVENTORY",
            "severity": "material",
            "message": "Batch notes indicate possible unscanned bulk or missing inventory; economics may be materially understated.",
        })

    realized_profit = net_cents - sold_basis_cents if sold_basis_cents is not None else None
    recovery = (
        round((net_cents / total_cost_cents) * 100, 2)
        if cost_known and total_cost_cents
        else None
    )
    current_position = (
        net_cents + active_market["known_value_cents"] - total_cost_cents
        if cost_known
        else None
    )
    listed_position = (
        net_cents + active_listed["known_value_cents"] - total_cost_cents
        if cost_known
        else None
    )
    return {
        "calculation_version": CALCULATION_VERSION,
        "state": "ESTIMATED",
        "notice": ESTIMATE_NOTICE,
        "batch": {"id": batch["id"], "batch_code": batch["batch_code"], "status": batch["status"]},
        "acquisition": {
            "cost_known": cost_known,
            "authoritative_cost_cents": None,
            "estimated_cost_cents": total_cost_cents if cost_known else None,
            "source": "legacy batches.total_cost",
            "label": "Estimated Acquisition Cost" if cost_known else "Cost Unknown / Incomplete",
        },
        "realized": {
            "gross_merchandise_cents": gross_cents,
            "net_proceeds_cents": net_cents,
            "estimated_sold_basis_cents": sold_basis_cents,
            "estimated_profit_loss_cents": realized_profit,
            "cost_recovery_percent": recovery,
            "sold_card_count": len(realized_items),
            "allocation_notice": LEGACY_SALE_NOTICE,
        },
        "remaining": {
            "active_card_count": len(active_cards),
            "estimated_active_basis_cents": (
                sum(estimated_basis.get(card["id"], 0) for card in active_cards)
                if cost_known else None
            ),
            "market": active_market,
            "listed": active_listed,
            "current_position_cents": current_position,
            "current_position_complete": cost_known and active_market["complete"],
            "projected_listed_position_cents": listed_position,
            "projected_listed_position_complete": cost_known and active_listed["complete"],
        },
        "excluded_recycled": {
            "card_count": len(recycled_cards),
            "estimated_basis_cents": recycled_basis,
            "market": recycled_market,
            "listed": recycled_listed,
        },
        "reconciliation": {
            "recorded_card_count": len(cards),
            "active_card_count": len(active_cards),
            "sold_card_count": len(realized_items),
            "recycled_card_count": len(recycled_cards),
            "incomplete_sale_skus": incomplete_sales,
            "materially_incomplete": any(item["severity"] == "material" for item in warnings),
        },
        "warnings": warnings,
    }
