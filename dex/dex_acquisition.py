"""Phase 3 acquisition facts and informational receipt-group calculations."""

from __future__ import annotations

import re
import sqlite3
from decimal import Decimal, InvalidOperation
from typing import Mapping

from dex_economics import ACQUISITION_MODES, CALCULATION_VERSION


EDITABLE_FIELDS = (
    "economics_mode",
    "product_name",
    "product_code",
    "receipt_group_reference",
    "invoice_reference",
    "original_currency",
    "original_foreign_amount_minor",
    "final_usd_paid_cents",
    "units_acquired",
    "purchase_subtotal_cents",
    "acquisition_tax_cents",
    "inbound_shipping_cents",
    "acquisition_fees_cents",
    "acquisition_discount_cents",
    "cost_reconciliation_acknowledged",
)

COST_COMPONENT_FIELDS = (
    "purchase_subtotal_cents",
    "acquisition_tax_cents",
    "inbound_shipping_cents",
    "acquisition_fees_cents",
    "acquisition_discount_cents",
)

DECIMAL_INPUTS = {
    "original_foreign_amount_minor": "original_foreign_amount",
    "final_usd_paid_cents": "final_usd_paid",
    "purchase_subtotal_cents": "purchase_subtotal",
    "acquisition_tax_cents": "acquisition_tax",
    "inbound_shipping_cents": "inbound_shipping",
    "acquisition_fees_cents": "acquisition_fees",
    "acquisition_discount_cents": "acquisition_discount",
}


def _text(value: object, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _optional_cents(value: object, label: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a monetary amount")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label} must be a monetary amount") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{label} cannot be negative")
    quantized = amount.quantize(Decimal("0.01"))
    if quantized != amount:
        raise ValueError(f"{label} cannot have more than two decimal places")
    return int(quantized * 100)


def _optional_integer(value: object, label: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a whole number")
    try:
        number = int(str(value))
    except ValueError as exc:
        raise ValueError(f"{label} must be a whole number") from exc
    if str(number) != str(value).strip() and not isinstance(value, int):
        raise ValueError(f"{label} must be a whole number")
    if number < 0:
        raise ValueError(f"{label} cannot be negative")
    return number


def format_cents(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value == 1
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def normalize_acquisition_input(
    payload: Mapping[str, object],
    existing: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Normalize a full or partial acquisition edit into database-ready facts."""

    current = dict(existing or {})
    mode = _text(payload.get("economics_mode", current.get("economics_mode", "LEGACY")), 40).upper()
    allowed_modes = {"LEGACY", *ACQUISITION_MODES}
    if mode not in allowed_modes:
        raise ValueError("Acquisition mode is not supported")

    values: dict[str, object] = {
        "economics_mode": mode,
        "product_name": _text(payload.get("product_name", current.get("product_name", "")), 180),
        "product_code": _text(payload.get("product_code", current.get("product_code", "")), 80).upper(),
        "receipt_group_reference": _text(
            payload.get("receipt_group_reference", current.get("receipt_group_reference", "")), 100
        ).upper(),
        "invoice_reference": _text(payload.get("invoice_reference", current.get("invoice_reference", "")), 100),
        "original_currency": _text(
            payload.get("original_currency", current.get("original_currency", "")), 3
        ).upper(),
    }

    if values["original_currency"] and not re.fullmatch(r"[A-Z]{3}", str(values["original_currency"])):
        raise ValueError("Original currency must be a three-letter currency code")

    for cents_field, decimal_field in DECIMAL_INPUTS.items():
        if cents_field in payload:
            raw = payload[cents_field]
            if raw is None or raw == "":
                values[cents_field] = None
            elif isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
                raise ValueError(f"{cents_field} must be a non-negative integer number of minor units")
            else:
                values[cents_field] = raw
        elif decimal_field in payload:
            values[cents_field] = _optional_cents(payload[decimal_field], decimal_field.replace("_", " ").title())
        else:
            values[cents_field] = current.get(cents_field)

    units_raw = payload.get("units_acquired", current.get("units_acquired"))
    values["units_acquired"] = _optional_integer(units_raw, "Units acquired")

    if values["original_foreign_amount_minor"] is not None and not values["original_currency"]:
        raise ValueError("Original currency is required when an original amount is entered")

    if mode != "LEGACY" and not values["product_name"]:
        raise ValueError("Product or lot name is required for acquisition economics")
    if mode == "SEALED_RIP":
        if not values["units_acquired"]:
            raise ValueError("Sealed acquisitions require at least one unit acquired")
    elif mode in ("SINGLES_KNOWN_COST", "SINGLES_LUMP_SUM"):
        if values["units_acquired"] not in (None, 0):
            raise ValueError("Purchased singles use card records rather than sealed units acquired")
        values["units_acquired"] = 0

    component_total = (
        int(values["purchase_subtotal_cents"] or 0)
        + int(values["acquisition_tax_cents"] or 0)
        + int(values["inbound_shipping_cents"] or 0)
        + int(values["acquisition_fees_cents"] or 0)
        - int(values["acquisition_discount_cents"] or 0)
    )
    if component_total < 0:
        raise ValueError("Acquisition discounts cannot exceed the entered acquisition costs")
    final_usd = values["final_usd_paid_cents"]
    difference = None if final_usd is None else int(final_usd) - component_total
    acknowledged = _truthy(
        payload.get(
            "cost_reconciliation_acknowledged",
            current.get("cost_reconciliation_acknowledged", 0),
        )
    )
    if difference in (None, 0):
        acknowledged = False
    if difference not in (None, 0) and not acknowledged:
        direction = "above" if difference > 0 else "below"
        raise ValueError(
            f"Cost components are {format_cents(abs(difference))} {direction} the final USD amount. "
            "Correct the components or explicitly acknowledge the difference."
        )
    values["cost_reconciliation_acknowledged"] = 1 if acknowledged else 0
    values["reporting_currency"] = "USD"
    values["component_total_cents"] = component_total
    values["reconciliation_difference_cents"] = difference
    return values


def acquisition_payload(db: sqlite3.Connection, batch_id: int) -> dict | None:
    batch = db.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
    if not batch:
        return None
    item = dict(batch)
    component_total = (
        int(item.get("purchase_subtotal_cents") or 0)
        + int(item.get("acquisition_tax_cents") or 0)
        + int(item.get("inbound_shipping_cents") or 0)
        + int(item.get("acquisition_fees_cents") or 0)
        - int(item.get("acquisition_discount_cents") or 0)
    )
    final_usd = item.get("final_usd_paid_cents")
    difference = None if final_usd is None else int(final_usd) - component_total
    reference = item.get("receipt_group_reference") or ""
    related: list[dict] = []
    if reference:
        related = [
            dict(row)
            for row in db.execute(
                """SELECT id, batch_code, product_name, product_code, economics_mode,
                          final_usd_paid_cents, units_acquired, status
                   FROM batches
                   WHERE receipt_group_reference = ? AND id != ?
                   ORDER BY id""",
                (reference, batch_id),
            ).fetchall()
        ]
    group_batches = [
        {
            "id": item["id"],
            "batch_code": item["batch_code"],
            "product_name": item.get("product_name") or "",
            "product_code": item.get("product_code") or "",
            "economics_mode": item.get("economics_mode") or "LEGACY",
            "final_usd_paid_cents": final_usd,
            "units_acquired": item.get("units_acquired"),
            "status": item["status"],
        },
        *related,
    ] if reference else []
    known_group_cost = sum(
        int(row["final_usd_paid_cents"])
        for row in group_batches
        if row.get("final_usd_paid_cents") is not None
    )
    known_group_count = sum(row.get("final_usd_paid_cents") is not None for row in group_batches)
    return {
        "calculation_version": CALCULATION_VERSION,
        "batch_id": item["id"],
        "batch_code": item["batch_code"],
        "economics_mode": item.get("economics_mode") or "LEGACY",
        "economics_status": item.get("economics_status") or "ESTIMATED",
        "product_name": item.get("product_name") or "",
        "product_code": item.get("product_code") or "",
        "invoice_reference": item.get("invoice_reference") or "",
        "reporting_currency": "USD",
        "original_currency": item.get("original_currency") or "",
        "original_foreign_amount_minor": item.get("original_foreign_amount_minor"),
        "units_acquired": item.get("units_acquired"),
        "authoritative_cost": {
            "known": final_usd is not None,
            "final_usd_paid_cents": final_usd,
            "label": format_cents(int(final_usd)) if final_usd is not None else "Cost Unknown / Incomplete",
        },
        "cost_breakdown": {
            field: item.get(field) for field in COST_COMPONENT_FIELDS
        } | {
            "component_total_cents": component_total,
            "difference_cents": difference,
            "reconciled": difference == 0 if difference is not None else False,
            "acknowledged": bool(item.get("cost_reconciliation_acknowledged")),
        },
        "receipt_group": {
            "reference": reference,
            "batches": group_batches,
            "known_assigned_cost_cents": known_group_cost,
            "cost_coverage": {"known": known_group_count, "total": len(group_batches)},
            "notice": (
                "Informational grouping only. Shared shipping, tax, discounts, and fees are not allocated automatically."
                if reference else "No Receipt/Acquisition Group assigned."
            ),
        },
        "updated_at": item.get("acquisition_updated_at"),
    }
