"""DEX v2.2-test Inbound 2.0 Phase 1 foundation.

This module owns draft acquisitions and their append-only lifecycle. It does not
create processing batches, sealed units, receipts, UPC mappings, or economics
facts. Later phases project explicitly confirmed lines into the established
Phase 3-7C batch model.
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import date, datetime, timezone
from typing import Mapping


ACQUISITION_STATES = (
    "ACQUISITION_INCOMPLETE",
    "RECONCILIATION_REQUIRED",
    "READY_FOR_INTAKE",
    "INTAKE_IN_PROGRESS",
    "INTAKE_COMPLETE",
    "CANCELED",
)
PRODUCT_CLASSES = ("SINGLE_CARDS", "PACK_PRODUCT", "SEALED_PRODUCT")
QUANTITY_CERTAINTIES = ("UNKNOWN", "ESTIMATED", "KNOWN")
SINGLES_COST_MODES = ("", "KNOWN_LINE_COSTS", "LUMP_SUM")
INTENDED_ACTIONS = (
    "DECIDE_LATER",
    "KEEP_SEALED",
    "RIP_OPEN",
    "SCAN_IDENTIFY",
    "INVENTORY_SINGLES",
)
ALLOCATION_METHODS = (
    "ACTUAL_LINE_COST",
    "EQUAL",
    "SUBTOTAL_WEIGHTED",
    "QUANTITY_WEIGHTED",
    "MANUAL",
    "SINGLE_LINE_100_PERCENT",
    "RECEIPT_VALUE_PROPORTIONAL",
)
PAYMENT_METHODS = ("CREDIT_DEBIT_CARD", "CASH", "PAYPAL", "STORE_CREDIT", "OTHER")
PRIMARY_WIZARD_STEPS = ("ACQUIRE", "PRODUCTS", "REVIEW")
RECEIPT_LINE_CLASSIFICATIONS = (
    "INVENTORY",
    "SHIPPING_FEE",
    "BUSINESS_NONINVENTORY",
    "PERSONAL_NONBUSINESS",
    "DUPLICATE_EXTRACTION",
    "UNRESOLVED",
)
DISCREPANCY_REASON_CODES = (
    "ROUNDING",
    "COMPONENTS_INCOMPLETE",
    "MERCHANT_TOTAL_CONTROLS",
    "NONINVENTORY_INCLUDED",
    "EXPLICIT_ZERO_COST",
    "OTHER",
)
ACQUISITION_REMOVAL_REASON_CODES = (
    "DUPLICATE_ENTRY",
    "ORDER_CANCELED",
    "RETURNED_TO_VENDOR",
    "ACQUISITION_NOT_COMPLETED",
    "TEST_OR_TRAINING_ENTRY",
    "OTHER",
)
MATERIAL_DISCREPANCY_CENTS = 500
MATERIAL_DISCREPANCY_PERCENT = 2.0
EXTREME_DISCREPANCY_PERCENT = 50.0
INBOUND_CALCULATION_VERSION = "inbound-acquisition-v1"
DECISION_LEVELS = ("AUTOMATIC", "AUTOMATIC_VISIBLE", "NEEDS_ATTENTION")
WIZARD_STEPS = (
    "ACQUIRE",
    "PRODUCTS",
    "SOURCE",
    "ECONOMICS",
    "RECONCILIATION",
    "REVIEW",
)

AUTOSAVE_FIELDS = (
    "wizard_step",
    "source_scope",
    "payment_method",
    "merchant_name",
    "merchant_country",
    "purchased_on",
    "order_reference",
    "original_currency",
    "original_foreign_amount_minor",
    "purchase_subtotal_cents",
    "acquisition_tax_cents",
    "inbound_shipping_cents",
    "acquisition_fees_cents",
    "import_duties_cents",
    "brokerage_cents",
    "acquisition_discount_cents",
    "final_usd_paid_cents",
    "discrepancy_reason_code",
    "discrepancy_notes",
)
CENT_FIELDS = {
    "original_foreign_amount_minor",
    "purchase_subtotal_cents",
    "acquisition_tax_cents",
    "inbound_shipping_cents",
    "acquisition_fees_cents",
    "import_duties_cents",
    "brokerage_cents",
    "acquisition_discount_cents",
    "final_usd_paid_cents",
}
COMPONENT_FIELDS = (
    "purchase_subtotal_cents",
    "acquisition_tax_cents",
    "inbound_shipping_cents",
    "acquisition_fees_cents",
    "import_duties_cents",
    "brokerage_cents",
    "acquisition_discount_cents",
)
LINE_AUTOSAVE_FIELDS = (
    "product_class",
    "game",
    "product_name",
    "set_code",
    "pack_type",
    "quantity",
    "quantity_certainty",
    "singles_cost_mode",
    "intended_action",
    "assigned_landed_cost_cents",
    "allocation_method",
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _text(value: object, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _required_request_id(payload: Mapping[str, object]) -> str:
    request_id = _text(payload.get("request_id"), 120)
    if not request_id:
        raise ValueError("A unique request_id is required")
    return request_id


def _confirmed(value: object) -> bool:
    return value is True or value == 1 or str(value or "").strip().lower() in {"true", "yes", "on"}


def _optional_cents(value: object, label: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer number of cents")
    return value


def _optional_quantity(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("Quantity must be a positive whole number")
    return value


def _acquisition_row(db: sqlite3.Connection, acquisition_id: int) -> sqlite3.Row:
    row = db.execute("SELECT * FROM acquisitions WHERE id=?", (acquisition_id,)).fetchone()
    if not row:
        raise ValueError("Acquisition not found")
    return row


def _line_row(db: sqlite3.Connection, line_id: int) -> sqlite3.Row:
    row = db.execute("SELECT * FROM acquisition_lines WHERE id=?", (line_id,)).fetchone()
    if not row:
        raise ValueError("Acquisition line not found")
    return row


def _require_revision(row: sqlite3.Row, payload: Mapping[str, object]) -> None:
    supplied = payload.get("expected_revision")
    if isinstance(supplied, bool) or not isinstance(supplied, int):
        raise ValueError("expected_revision is required")
    if supplied != int(row["revision"]):
        raise ValueError("Acquisition changed since it was loaded; reload before saving")


def _require_draft_mutable(row: sqlite3.Row) -> None:
    if row["state"] not in ("ACQUISITION_INCOMPLETE", "RECONCILIATION_REQUIRED"):
        raise ValueError("Only an incomplete or reconciliation-required acquisition can be autosaved")


def acquisition_removal_eligibility(db: sqlite3.Connection, acquisition_id: int) -> dict:
    """Describe removal safety without mutating acquisition or economic facts."""

    row = _acquisition_row(db, acquisition_id)
    line_ids = [
        int(item[0])
        for item in db.execute(
            "SELECT id FROM acquisition_lines WHERE acquisition_id=? ORDER BY id",
            (acquisition_id,),
        ).fetchall()
    ]
    batch_ids: list[int] = []
    if line_ids:
        placeholders = ",".join("?" for _ in line_ids)
        batch_ids = [
            int(item[0])
            for item in db.execute(
                f"SELECT id FROM batches WHERE acquisition_line_id IN ({placeholders}) ORDER BY id",
                tuple(line_ids),
            ).fetchall()
        ]
    downstream_counts = {
        "batches": len(batch_ids),
        "cards": 0,
        "sealed_units": 0,
        "sale_items": 0,
        "sealed_sale_items": 0,
        "rip_sessions": 0,
        "economic_events": 0,
    }
    if batch_ids:
        placeholders = ",".join("?" for _ in batch_ids)
        params = tuple(batch_ids)
        downstream_counts["cards"] = int(db.execute(
            f"SELECT COUNT(*) FROM cards WHERE batch_id IN ({placeholders})", params
        ).fetchone()[0])
        downstream_counts["sealed_units"] = int(db.execute(
            f"SELECT COUNT(*) FROM sealed_units WHERE batch_id IN ({placeholders})", params
        ).fetchone()[0])
        downstream_counts["rip_sessions"] = int(db.execute(
            f"SELECT COUNT(*) FROM rip_sessions WHERE batch_id IN ({placeholders})", params
        ).fetchone()[0])
        downstream_counts["economic_events"] = int(db.execute(
            f"SELECT COUNT(*) FROM economic_events WHERE batch_id IN ({placeholders})", params
        ).fetchone()[0])
        downstream_counts["sale_items"] = int(db.execute(
            f"""SELECT COUNT(*) FROM sale_items si JOIN cards c ON c.id=si.card_id
                 WHERE c.batch_id IN ({placeholders})""", params
        ).fetchone()[0])
        downstream_counts["sealed_sale_items"] = int(db.execute(
            f"""SELECT COUNT(*) FROM sealed_sale_items ssi
                 JOIN sealed_units su ON su.id=ssi.sealed_unit_id
                 WHERE su.batch_id IN ({placeholders})""", params
        ).fetchone()[0])
    internal_economic_counts = {
        "confirmed_line_allocations": int(db.execute(
            "SELECT COUNT(*) FROM acquisition_lines WHERE acquisition_id=? AND allocation_status='CONFIRMED'",
            (acquisition_id,),
        ).fetchone()[0]),
        "accepted_receipt_allocations": int(db.execute(
            "SELECT COUNT(*) FROM receipt_allocation_proposals WHERE acquisition_id=? AND status='ACCEPTED'",
            (acquisition_id,),
        ).fetchone()[0]),
    }
    downstream_protected = any(downstream_counts.values())
    internal_economic_history = any(internal_economic_counts.values())
    draft = row["state"] in ("ACQUISITION_INCOMPLETE", "RECONCILIATION_REQUIRED")
    confirmed = row["state"] == "READY_FOR_INTAKE"
    recycled = bool(row["recycled_at"])
    return {
        "protected_history": downstream_protected,
        "protected_downstream_history": downstream_protected,
        "internal_economic_history": internal_economic_history,
        "internal_economic_counts": internal_economic_counts,
        "downstream_counts": downstream_counts,
        "can_recycle_draft": draft and not downstream_protected and not internal_economic_history and not recycled,
        "can_cancel_confirmed": confirmed and not downstream_protected and not recycled,
        "can_restore": recycled and not downstream_protected and row["pre_recycle_state"] in (
            "ACQUISITION_INCOMPLETE", "RECONCILIATION_REQUIRED"
        ),
        "permanent_purge_supported": False,
        "blocked_message": (
            "This acquisition has downstream inventory or economic history. Use the relevant correction or reversal workflow."
            if downstream_protected
            else "Reverse or invalidate the confirmed draft allocation before moving this acquisition to Recycle Bin."
            if internal_economic_history and draft
            else ""
        ),
    }


def _removal_reason(payload: Mapping[str, object], *, notes_required: bool) -> tuple[str, str]:
    reason = _text(payload.get("reason_code"), 40).upper()
    notes = _text(payload.get("notes"), 500)
    if reason not in ACQUISITION_REMOVAL_REASON_CODES:
        raise ValueError("Choose a supported acquisition removal reason")
    if (notes_required or reason == "OTHER") and not notes:
        raise ValueError("An operator note is required for this acquisition action")
    return reason, notes


def _event(
    db: sqlite3.Connection,
    *,
    request_id: str,
    acquisition_id: int,
    event_type: str,
    line_id: int | None = None,
    from_state: str | None = None,
    to_state: str | None = None,
    reason_code: str = "",
    notes: str = "",
    payload: Mapping[str, object] | None = None,
) -> str:
    event_id = f"ACQEVT-{uuid.uuid4()}"
    now = utcnow()
    db.execute(
        """INSERT INTO acquisition_events
           (event_id,request_id,acquisition_id,acquisition_line_id,event_type,
            from_state,to_state,effective_at,recorded_at,reason_code,notes,payload)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            event_id,
            request_id,
            acquisition_id,
            line_id,
            event_type,
            from_state,
            to_state,
            now,
            now,
            reason_code,
            notes,
            json.dumps(dict(payload or {}), separators=(",", ":"), sort_keys=True),
        ),
    )
    return event_id


def _replay_acquisition(
    db: sqlite3.Connection, request_id: str, expected_acquisition_id: int
) -> dict | None:
    event = db.execute(
        "SELECT acquisition_id FROM acquisition_events WHERE request_id=?", (request_id,)
    ).fetchone()
    if event:
        if int(event["acquisition_id"]) != expected_acquisition_id:
            raise ValueError("request_id already belongs to a different acquisition")
        result = acquisition_payload(db, int(event["acquisition_id"]))
        result["idempotent_replay"] = True
        return result
    return None


def _component_total(row: Mapping[str, object]) -> int:
    return (
        int(row.get("purchase_subtotal_cents") or 0)
        + int(row.get("acquisition_tax_cents") or 0)
        + int(row.get("inbound_shipping_cents") or 0)
        + int(row.get("acquisition_fees_cents") or 0)
        + int(row.get("import_duties_cents") or 0)
        + int(row.get("brokerage_cents") or 0)
        - int(row.get("acquisition_discount_cents") or 0)
    )


def reconciliation_payload(row: Mapping[str, object], lines: list[Mapping[str, object]]) -> dict:
    component_total = _component_total(row)
    final_paid = row.get("final_usd_paid_cents")
    difference = None if final_paid is None else int(final_paid) - component_total
    denominator = max(abs(int(final_paid or 0)), abs(component_total), 1)
    percent = None if difference is None else round(abs(difference) * 100 / denominator, 2)
    material = bool(
        difference
        and (abs(int(difference)) >= MATERIAL_DISCREPANCY_CENTS or float(percent or 0) >= MATERIAL_DISCREPANCY_PERCENT)
    )
    extreme = bool(difference and float(percent or 0) >= EXTREME_DISCREPANCY_PERCENT)
    confirmed_lines = [line for line in lines if line.get("allocation_status") == "CONFIRMED" and not line.get("canceled_at")]
    assigned_total = sum(int(line.get("assigned_landed_cost_cents") or 0) for line in confirmed_lines)
    allocation_difference = None if final_paid is None else int(final_paid) - assigned_total
    return {
        "component_total_cents": component_total,
        "final_usd_paid_cents": final_paid,
        "difference_cents": difference,
        "difference_percent": percent,
        "severity": "EXTREME" if extreme else "MATERIAL" if material else "NOTICE" if difference else "NONE",
        "material": material,
        "extreme": extreme,
        "material_rule": "$5.00 OR 2%",
        "extreme_rule": "50% or greater difference",
        "assigned_line_cost_cents": assigned_total,
        "allocation_difference_cents": allocation_difference,
        "allocation_reconciled": allocation_difference == 0 if allocation_difference is not None else False,
        "allocation_notice": "Every suggested allocation must disclose its method and remains non-authoritative until explicitly confirmed.",
    }


def _attention_payload(
    row: Mapping[str, object],
    active_lines: list[Mapping[str, object]],
    reconciliation: Mapping[str, object],
    warnings: list[dict[str, str]],
) -> dict:
    warning_codes = list(dict.fromkeys(item["code"] for item in warnings))
    ready = row.get("state") == "READY_FOR_INTAKE"
    final_paid = row.get("final_usd_paid_cents")
    zero_exception = final_paid == 0 and not ready
    allocation_unresolved = bool(
        len(active_lines) > 1 and not reconciliation.get("allocation_reconciled")
    )
    discrepancy = bool(reconciliation.get("difference_cents"))
    incomplete = bool(warnings)
    needs_attention = not ready and (zero_exception or allocation_unresolved or discrepancy or incomplete)

    if ready:
        state = "AUTOMATIC_VISIBLE"
        level = None
        headline = "Authoritative acquisition confirmed"
        message = "DEX preserved the calculation method and confirmed acquisition audit trail."
        resolve_mode = None
    elif needs_attention:
        state = "NEEDS_ATTENTION"
        level = "CRITICAL" if final_paid is None or reconciliation.get("extreme") else "REVIEW"
        if final_paid is None:
            headline = "Authoritative cost is Unknown"
            message = "Enter the actual final USD paid before this acquisition can be confirmed."
            resolve_mode = "INCOMPLETE_FACTS"
        elif allocation_unresolved:
            headline = "Product-line cost allocation needs attention"
            message = "DEX does not yet have enough authoritative evidence to split landed cost safely."
            resolve_mode = "MULTI_LINE_ALLOCATION"
        elif discrepancy:
            headline = "Purchase totals need attention"
            message = "Component total and final USD paid conflict and require a recorded resolution."
            resolve_mode = "PURCHASE_DISCREPANCY"
        elif zero_exception:
            headline = "Explicit zero-dollar acquisition needs attention"
            message = "Confirm that $0.00 is intentional rather than a missing cost."
            resolve_mode = "ZERO_COST"
        else:
            headline = "Acquisition setup needs attention"
            message = "Complete the unresolved business facts before confirmation."
            resolve_mode = "INCOMPLETE_FACTS"
    else:
        state = "AUTOMATIC_VISIBLE"
        level = None
        headline = "DEX completed the deterministic accounting"
        message = "Review the visible landed-cost assignment and confirm the acquisition."
        resolve_mode = None

    return {
        "decision_level": state,
        "attention_level": level,
        "headline": headline,
        "message": message,
        "reason_codes": warning_codes,
        "resolve_mode": resolve_mode,
        "requires_operator_judgment": state == "NEEDS_ATTENTION",
        "attention_center_compatible": True,
        "global_attention_item_created": False,
    }


def acquisition_payload(db: sqlite3.Connection, acquisition_id: int) -> dict:
    from dex_documents import document_summary
    from dex_receipts import receipt_intelligence_payload

    row = dict(_acquisition_row(db, acquisition_id))
    lines = [
        dict(item)
        for item in db.execute(
            "SELECT * FROM acquisition_lines WHERE acquisition_id=? ORDER BY line_sequence",
            (acquisition_id,),
        ).fetchall()
    ]
    catalog_ids = sorted({int(line["catalog_product_id"]) for line in lines if line.get("catalog_product_id")})
    catalog_products: dict[int, dict] = {}
    if catalog_ids:
        placeholders = ",".join("?" for _ in catalog_ids)
        for item in db.execute(
            f"SELECT * FROM catalog_products WHERE id IN ({placeholders})", tuple(catalog_ids)
        ).fetchall():
            product = dict(item)
            product["identifiers"] = []
            catalog_products[int(item["id"])] = product
        for item in db.execute(
            f"""SELECT id,identifier_uuid,normalized_identifier,raw_identifier,identifier_type,
                       catalog_product_id,mapping_status,provenance,created_at,verified_at,updated_at
                  FROM product_identifiers
                 WHERE catalog_product_id IN ({placeholders}) AND mapping_status='ACTIVE'
                 ORDER BY identifier_type,normalized_identifier""",
            tuple(catalog_ids),
        ).fetchall():
            product = catalog_products.get(int(item["catalog_product_id"]))
            if product is not None:
                product["identifiers"].append(dict(item))
    for line in lines:
        line["catalog_product"] = catalog_products.get(int(line["catalog_product_id"])) if line.get("catalog_product_id") else None
    events = [
        dict(item)
        for item in db.execute(
            "SELECT * FROM acquisition_events WHERE acquisition_id=? ORDER BY recorded_at,event_id",
            (acquisition_id,),
        ).fetchall()
    ]
    for event in events:
        event["payload"] = json.loads(event["payload"] or "{}")
    active_lines = [line for line in lines if not line.get("canceled_at")]
    for line in lines:
        cents = line.get("assigned_landed_cost_cents")
        quantity = line.get("quantity")
        line["per_unit_cost"] = None
        if cents is not None and quantity:
            base, remainder = divmod(int(cents), int(quantity))
            line["per_unit_cost"] = {
                "base_cents": base,
                "remainder_units": remainder,
                "quantity": int(quantity),
                "minimum_cents": base,
                "maximum_cents": base + (1 if remainder else 0),
                "exact_when_uniform": remainder == 0,
            }
    receipt_intelligence = receipt_intelligence_payload(db, acquisition_id)
    receipt_proposal = receipt_intelligence.get("allocation_proposal")
    receipt_allocation_safe = bool(
        receipt_proposal and receipt_proposal.get("status") in ("APPLIED", "ACCEPTED")
        and receipt_proposal.get("difference_cents") == 0
    )
    reconciliation_lines = [dict(line) for line in lines]
    if receipt_allocation_safe:
        proposed = {int(item["acquisition_line_id"]): int(item["landed_cost_cents"]) for item in receipt_proposal["allocations"]}
        for line in reconciliation_lines:
            if int(line["id"]) in proposed and not line.get("canceled_at"):
                line["assigned_landed_cost_cents"] = proposed[int(line["id"])]
                line["allocation_method"] = "RECEIPT_VALUE_PROPORTIONAL"
                line["allocation_status"] = "CONFIRMED"
    reconciliation = reconciliation_payload(row, reconciliation_lines)
    warnings: list[dict[str, str]] = []
    if not row.get("source_scope"):
        warnings.append({"code": "SOURCE_REQUIRED", "message": "Choose Domestic or International purchase source."})
    if not row.get("merchant_name"):
        warnings.append({"code": "MERCHANT_REQUIRED", "message": "Enter the merchant or seller."})
    if not row.get("purchased_on"):
        warnings.append({"code": "PURCHASE_DATE_REQUIRED", "message": "Enter the purchase date."})
    if not row.get("payment_method"):
        warnings.append({"code": "PAYMENT_METHOD_REQUIRED", "message": "Choose the payment method."})
    if row.get("final_usd_paid_cents") is None:
        warnings.append({"code": "COST_UNKNOWN", "message": "Final USD cost is Unknown / Setup incomplete."})
    if not active_lines:
        warnings.append({"code": "NO_PRODUCT_LINES", "message": "Add at least one product line."})
    for line in active_lines:
        label = f"Product line {line['line_sequence']}"
        if not line.get("game"):
            warnings.append({"code": "PRODUCT_DETAILS_INCOMPLETE", "message": f"{label} needs a TCG."})
        if line.get("product_class") == "SINGLE_CARDS" and not line.get("set_code"):
            warnings.append({"code": "SINGLES_SET_REQUIRED", "message": f"{label} needs a set."})
        if line.get("product_class") != "SINGLE_CARDS" and not line.get("product_name"):
            warnings.append({"code": "PRODUCT_DETAILS_INCOMPLETE", "message": f"{label} needs a product type."})
        if not line.get("quantity"):
            warnings.append({"code": "QUANTITY_UNKNOWN", "message": f"{label} needs an estimated or known quantity."})
        if line.get("product_class") in ("PACK_PRODUCT", "SEALED_PRODUCT") and line.get("quantity_certainty") != "KNOWN":
            warnings.append({"code": "PHYSICAL_QUANTITY_UNCONFIRMED", "message": f"{label} needs a known physical quantity."})
        if line.get("product_class") == "SINGLE_CARDS" and line.get("singles_cost_mode") not in ("KNOWN_LINE_COSTS", "LUMP_SUM"):
            warnings.append({"code": "SINGLES_COST_MODE_UNKNOWN", "message": f"{label} needs a singles cost method."})
        automatic_single_line = len(active_lines) == 1 and row.get("final_usd_paid_cents") is not None
        if line.get("allocation_status") != "CONFIRMED" and not automatic_single_line and not receipt_allocation_safe:
            warnings.append({"code": "LINE_COST_UNCONFIRMED", "message": f"{label} landed cost is not confirmed."})
    if row.get("final_usd_paid_cents") is not None and not reconciliation["allocation_reconciled"] and len(active_lines) != 1:
        warnings.append({"code": "ALLOCATION_NOT_RECONCILED", "message": "Confirmed product-line costs do not equal final USD paid."})
    if reconciliation["difference_cents"] and not row.get("discrepancy_reason_code"):
        warnings.append({"code": "DISCREPANCY_REASON_REQUIRED", "message": "Choose a reason for the component-to-final difference."})
    if row.get("final_usd_paid_cents") == 0 and row.get("discrepancy_reason_code") != "EXPLICIT_ZERO_COST":
        warnings.append({"code": "ZERO_COST_REASON_REQUIRED", "message": "An intentional $0.00 acquisition requires the Explicit zero-cost reason."})
    if reconciliation["material"] and not row.get("discrepancy_notes"):
        warnings.append({"code": "MATERIAL_NOTE_REQUIRED", "message": "Material differences require an explanatory note."})
    warnings.extend(receipt_intelligence.get("warnings", []))
    automatic_preview = None
    if len(active_lines) == 1 and row.get("final_usd_paid_cents") is not None:
        line = active_lines[0]
        cents = int(row["final_usd_paid_cents"])
        quantity = line.get("quantity")
        per_unit = None
        if quantity:
            base, remainder = divmod(cents, int(quantity))
            per_unit = {
                "base_cents": base,
                "remainder_units": remainder,
                "quantity": int(quantity),
                "minimum_cents": base,
                "maximum_cents": base + (1 if remainder else 0),
                "exact_when_uniform": remainder == 0,
            }
        automatic_preview = {
            "line_id": int(line["id"]),
            "assigned_landed_cost_cents": cents,
            "allocation_method": "SINGLE_LINE_100_PERCENT",
            "allocation_method_label": "Single line — 100% of authoritative landed cost",
            "per_unit_cost": per_unit,
            "will_record_audit_event": line.get("allocation_status") != "CONFIRMED",
            "calculation_version": INBOUND_CALCULATION_VERSION,
            "decision_level": "AUTOMATIC_VISIBLE",
        }
    attention = _attention_payload(row, active_lines, reconciliation, warnings)
    source_documents = document_summary(db, acquisition_id)
    removal = acquisition_removal_eligibility(db, acquisition_id)
    from dex_intake_bridge import intake_status
    routing = intake_status(db, acquisition_id)
    return {
        "acquisition": row,
        "lines": lines,
        "events": events,
        "reconciliation": reconciliation,
        "readiness": {
            "ready_to_confirm": not warnings,
            "warnings": warnings,
            "authoritative_cost_label": (
                f"${int(row['final_usd_paid_cents']) / 100:,.2f}"
                if row.get("final_usd_paid_cents") is not None
                else "Unknown / Setup incomplete"
            ),
        },
        "automatic_single_line_allocation_preview": automatic_preview,
        "attention": attention,
        "source_documents": source_documents,
        "receipt_intelligence": receipt_intelligence,
        "removal": removal,
        "projection": {
            "status": "PROJECTED" if any(item["batch_id"] for item in routing["lines"]) else "NOT_IMPLEMENTED_PHASE_1",
            "batch_ids": [item["batch_id"] for item in routing["lines"] if item["batch_id"]],
            "notice": "Confirmed lines project into the established batch, sealed-unit, rip, and scanning model through explicit intake routing.",
        },
        "intake_routing": routing,
    }


def list_acquisitions(db: sqlite3.Connection) -> list[dict]:
    rows = db.execute(
        """SELECT a.*,
                  (SELECT COUNT(*) FROM acquisition_lines l WHERE l.acquisition_id=a.id AND l.canceled_at IS NULL) AS active_line_count
             FROM acquisitions a WHERE a.recycled_at IS NULL
             ORDER BY a.updated_at DESC,a.id DESC"""
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["removal"] = acquisition_removal_eligibility(db, int(row["id"]))
        result.append(item)
    return result


def list_recycled_acquisitions(db: sqlite3.Connection, search: str = "") -> list[dict]:
    term = _text(search, 100)
    params: list[object] = []
    clause = ""
    if term:
        clause = "AND (a.acquisition_code LIKE ? OR a.merchant_name LIKE ? OR a.order_reference LIKE ?)"
        params.extend([f"%{term}%"] * 3)
    rows = db.execute(
        f"""SELECT a.*,
                   (SELECT COUNT(*) FROM acquisition_lines l WHERE l.acquisition_id=a.id) AS line_count,
                   (SELECT COUNT(*) FROM acquisition_documents d WHERE d.acquisition_id=a.id) AS document_count
              FROM acquisitions a
             WHERE a.recycled_at IS NOT NULL {clause}
             ORDER BY a.recycled_at DESC,a.id DESC""",
        params,
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["removal"] = acquisition_removal_eligibility(db, int(row["id"]))
        result.append(item)
    return result


def foundation_contract() -> dict:
    return {
        "version": "v2.2-test",
        "phase": "INBOUND_2_PHASE_6_DOWNSTREAM_INTAKE_BRIDGE",
        "default_state": "ACQUISITION_INCOMPLETE",
        "states": list(ACQUISITION_STATES),
        "product_classes": list(PRODUCT_CLASSES),
        "receipt_line_classifications": list(RECEIPT_LINE_CLASSIFICATIONS),
        "allocation_methods": list(ALLOCATION_METHODS),
        "wizard_steps": list(PRIMARY_WIZARD_STEPS),
        "legacy_persisted_wizard_steps": list(WIZARD_STEPS),
        "payment_methods": list(PAYMENT_METHODS),
        "decision_levels": list(DECISION_LEVELS),
        "calculation_version": INBOUND_CALCULATION_VERSION,
        "discrepancy_rules": {
            "material_cents": MATERIAL_DISCREPANCY_CENTS,
            "material_percent": MATERIAL_DISCREPANCY_PERCENT,
            "material_operator": "OR",
            "extreme_percent": EXTREME_DISCREPANCY_PERCENT,
        },
        "phase_2_boundaries": {
            "operator_workflow_replaced": True,
            "legacy_batch_workflow_available": True,
            "upc_catalog": True,
            "documents_or_extraction": True,
            "source_documents": True,
            "receipt_extraction": False,
            "sam": False,
            "batch_projection": True,
            "manual_entry_available_during_document_outage": True,
            "failed_document_uploads_retryable_later": True,
        },
    }


def _normalized_acquisition_fields(payload: Mapping[str, object]) -> dict:
    prohibited = {
        "state",
        "financial_facts_confirmed",
        "reconciliation_confirmed",
        "confirmed_at",
        "reporting_currency",
        "acquisition_uuid",
        "acquisition_code",
    }
    if prohibited.intersection(payload):
        raise ValueError("Autosave cannot confirm authoritative facts, reconciliation, state, or identity")
    values: dict[str, object] = {}
    for field in AUTOSAVE_FIELDS:
        if field not in payload:
            continue
        value = payload[field]
        if field == "wizard_step":
            step = _text(value, 30).upper()
            if step not in WIZARD_STEPS:
                raise ValueError("Wizard step is not supported")
            values[field] = step
        elif field in CENT_FIELDS:
            values[field] = _optional_cents(value, field.replace("_", " ").title())
        elif field == "source_scope":
            scope = _text(value, 20).upper()
            if scope and scope not in ("DOMESTIC", "INTERNATIONAL"):
                raise ValueError("Purchase source must be DOMESTIC or INTERNATIONAL")
            values[field] = scope or None
        elif field == "payment_method":
            payment_method = _text(value, 30).upper()
            if payment_method and payment_method not in PAYMENT_METHODS:
                raise ValueError("Payment method is not supported")
            values[field] = payment_method
        elif field == "original_currency":
            currency = _text(value, 3).upper()
            if currency and not re.fullmatch(r"[A-Z]{3}", currency):
                raise ValueError("Original currency must be a three-letter code")
            values[field] = currency
        elif field == "purchased_on":
            text = _text(value, 10)
            if text:
                try:
                    date.fromisoformat(text)
                except ValueError as exc:
                    raise ValueError("Purchase date must use YYYY-MM-DD") from exc
            values[field] = text or None
        elif field == "discrepancy_reason_code":
            reason = _text(value, 40).upper()
            if reason and reason not in DISCREPANCY_REASON_CODES:
                raise ValueError("Discrepancy reason code is not supported")
            values[field] = reason
        else:
            values[field] = _text(value, 500 if field == "discrepancy_notes" else 180)
    if values.get("original_foreign_amount_minor") is not None and not (
        values.get("original_currency") or payload.get("original_currency")
    ):
        raise ValueError("Original currency is required with a foreign amount")
    return values


def create_acquisition(db: sqlite3.Connection, payload: Mapping[str, object]) -> dict:
    request_id = _required_request_id(payload)
    existing = db.execute(
        "SELECT id FROM acquisitions WHERE creation_request_id=?", (request_id,)
    ).fetchone()
    if existing:
        result = acquisition_payload(db, int(existing["id"]))
        result["idempotent_replay"] = True
        return result
    values = _normalized_acquisition_fields(payload)
    now = utcnow()
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    sequence = int(
        db.execute(
            "SELECT COUNT(*) FROM acquisitions WHERE acquisition_code LIKE ?", (f"ACQ-{day}-%",)
        ).fetchone()[0]
    ) + 1
    acquisition_uuid = f"ACQ-{uuid.uuid4()}"
    base = {
        "acquisition_uuid": acquisition_uuid,
        "acquisition_code": f"ACQ-{day}-{sequence:04d}",
        "creation_request_id": request_id,
        "created_at": now,
        "updated_at": now,
        **values,
    }
    columns = ",".join(base)
    cursor = db.execute(
        f"INSERT INTO acquisitions ({columns}) VALUES ({','.join('?' for _ in base)})",
        tuple(base.values()),
    )
    acquisition_id = int(cursor.lastrowid)
    _event(
        db,
        request_id=f"{request_id}:created",
        acquisition_id=acquisition_id,
        event_type="CREATED",
        to_state="ACQUISITION_INCOMPLETE",
        payload={"acquisition_uuid": acquisition_uuid},
    )
    return acquisition_payload(db, acquisition_id)


def autosave_acquisition(db: sqlite3.Connection, acquisition_id: int, payload: Mapping[str, object]) -> dict:
    request_id = _required_request_id(payload)
    replay = _replay_acquisition(db, request_id, acquisition_id)
    if replay:
        return replay
    row = _acquisition_row(db, acquisition_id)
    _require_revision(row, payload)
    _require_draft_mutable(row)
    updates = _normalized_acquisition_fields(payload)
    if not updates:
        raise ValueError("No draft acquisition fields were supplied")
    from dex_receipts import record_manual_overrides
    record_manual_overrides(db, acquisition_id, updates, request_id)
    previous_state = str(row["state"])
    progress_only = set(updates) == {"wizard_step"}
    if not progress_only:
        updates.update({
            "state": "ACQUISITION_INCOMPLETE",
            "financial_facts_confirmed": 0,
            "reconciliation_confirmed": 0,
            "confirmed_at": None,
        })
    updates.update({"revision": int(row["revision"]) + 1, "updated_at": utcnow()})
    db.execute(
        f"UPDATE acquisitions SET {','.join(f'{field}=?' for field in updates)} WHERE id=?",
        (*updates.values(), acquisition_id),
    )
    _event(
        db,
        request_id=request_id,
        acquisition_id=acquisition_id,
        event_type="DRAFT_AUTOSAVED",
        from_state=previous_state,
        to_state=previous_state if progress_only else "ACQUISITION_INCOMPLETE",
        payload={"fields": sorted(field for field in updates if field not in {"revision", "updated_at"})},
    )
    return acquisition_payload(db, acquisition_id)


def cancel_acquisition_line(db: sqlite3.Connection, line_id: int, payload: Mapping[str, object]) -> dict:
    """Remove a draft line from the active wizard while retaining its history."""

    request_id = _required_request_id(payload)
    line = _line_row(db, line_id)
    acquisition_id = int(line["acquisition_id"])
    acquisition = _acquisition_row(db, acquisition_id)
    replay = _replay_acquisition(db, request_id, acquisition_id)
    if replay:
        return replay
    _require_revision(acquisition, payload)
    _require_draft_mutable(acquisition)
    if line["canceled_at"]:
        raise ValueError("Product line is already removed")
    now = utcnow()
    db.execute("UPDATE acquisition_lines SET canceled_at=?,updated_at=? WHERE id=?", (now, now, line_id))
    db.execute(
        """UPDATE acquisitions SET state='ACQUISITION_INCOMPLETE',financial_facts_confirmed=0,
                  reconciliation_confirmed=0,confirmed_at=NULL,revision=revision+1,updated_at=? WHERE id=?""",
        (now, acquisition_id),
    )
    _event(
        db,
        request_id=request_id,
        acquisition_id=acquisition_id,
        line_id=line_id,
        event_type="LINE_AUTOSAVED",
        from_state=str(acquisition["state"]),
        to_state="ACQUISITION_INCOMPLETE",
        reason_code="DRAFT_LINE_REMOVED",
        payload={"canceled_at": now},
    )
    return acquisition_payload(db, acquisition_id)


def _normalized_line_fields(payload: Mapping[str, object], current: Mapping[str, object] | None = None) -> dict:
    existing = dict(current or {})
    values: dict[str, object] = {}
    for field in LINE_AUTOSAVE_FIELDS:
        if field not in payload and field in existing:
            continue
        if field not in payload:
            continue
        value = payload[field]
        if field == "product_class":
            normalized = _text(value, 30).upper()
            if normalized not in PRODUCT_CLASSES:
                raise ValueError("Product class must be SINGLE_CARDS, PACK_PRODUCT, or SEALED_PRODUCT")
            values[field] = normalized
        elif field == "quantity":
            values[field] = _optional_quantity(value)
        elif field == "quantity_certainty":
            normalized = _text(value, 20).upper()
            if normalized not in QUANTITY_CERTAINTIES:
                raise ValueError("Quantity certainty is not supported")
            values[field] = normalized
        elif field == "singles_cost_mode":
            normalized = _text(value, 30).upper()
            if normalized not in SINGLES_COST_MODES:
                raise ValueError("Singles cost mode is not supported")
            values[field] = normalized
        elif field == "intended_action":
            normalized = _text(value, 30).upper()
            if normalized not in INTENDED_ACTIONS:
                raise ValueError("Intended action is not supported")
            values[field] = normalized
        elif field == "assigned_landed_cost_cents":
            values[field] = _optional_cents(value, "Suggested landed cost")
        elif field == "allocation_method":
            normalized = _text(value, 30).upper()
            if normalized and normalized not in ALLOCATION_METHODS:
                raise ValueError("Allocation method is not supported")
            values[field] = normalized
        else:
            values[field] = _text(value, 180 if field == "product_name" else 60)
    if "assigned_landed_cost_cents" in values or "allocation_method" in values:
        values["allocation_status"] = "SUGGESTED"
    return values


def add_acquisition_line(db: sqlite3.Connection, acquisition_id: int, payload: Mapping[str, object]) -> dict:
    request_id = _required_request_id(payload)
    acquisition = _acquisition_row(db, acquisition_id)
    replay = _replay_acquisition(db, request_id, acquisition_id)
    if replay:
        return replay
    _require_revision(acquisition, payload)
    _require_draft_mutable(acquisition)
    values = _normalized_line_fields(payload)
    if "product_class" not in values:
        raise ValueError("Product class is required")
    if values["product_class"] == "SINGLE_CARDS":
        values.setdefault("quantity_certainty", "KNOWN")
        values.setdefault("singles_cost_mode", "LUMP_SUM")
        values.setdefault("intended_action", "SCAN_IDENTIFY")
    else:
        values.setdefault("quantity_certainty", "KNOWN")
    sequence = int(
        db.execute(
            "SELECT COALESCE(MAX(line_sequence),0)+1 FROM acquisition_lines WHERE acquisition_id=?",
            (acquisition_id,),
        ).fetchone()[0]
    )
    now = utcnow()
    base = {
        "line_uuid": f"ACQLINE-{uuid.uuid4()}",
        "acquisition_id": acquisition_id,
        "line_sequence": sequence,
        "created_at": now,
        "updated_at": now,
        **values,
    }
    cursor = db.execute(
        f"INSERT INTO acquisition_lines ({','.join(base)}) VALUES ({','.join('?' for _ in base)})",
        tuple(base.values()),
    )
    line_id = int(cursor.lastrowid)
    db.execute(
        """UPDATE acquisitions SET state='ACQUISITION_INCOMPLETE',financial_facts_confirmed=0,
                  reconciliation_confirmed=0,confirmed_at=NULL,revision=revision+1,updated_at=? WHERE id=?""",
        (now, acquisition_id),
    )
    _event(
        db,
        request_id=request_id,
        acquisition_id=acquisition_id,
        line_id=line_id,
        event_type="LINE_ADDED",
        from_state=str(acquisition["state"]),
        to_state="ACQUISITION_INCOMPLETE",
        payload={"line_uuid": base["line_uuid"], "product_class": values["product_class"]},
    )
    return acquisition_payload(db, acquisition_id)


def autosave_acquisition_line(db: sqlite3.Connection, line_id: int, payload: Mapping[str, object]) -> dict:
    request_id = _required_request_id(payload)
    line = _line_row(db, line_id)
    acquisition = _acquisition_row(db, int(line["acquisition_id"]))
    replay = _replay_acquisition(db, request_id, int(acquisition["id"]))
    if replay:
        return replay
    _require_revision(acquisition, payload)
    _require_draft_mutable(acquisition)
    if "allocation_status" in payload:
        raise ValueError("Autosave cannot confirm a product-line allocation")
    updates = _normalized_line_fields(payload, dict(line))
    if not updates:
        raise ValueError("No draft product-line fields were supplied")
    if {"assigned_landed_cost_cents", "allocation_method"}.intersection(updates):
        updates["allocation_status"] = "UNALLOCATED"
    identity_fields = {"product_class", "game", "product_name", "set_code", "pack_type"}
    catalog_link_removed = bool(
        line["catalog_product_id"]
        and any(field in updates and updates[field] != line[field] for field in identity_fields)
    )
    if catalog_link_removed:
        updates["catalog_product_id"] = None
    updates["updated_at"] = utcnow()
    db.execute(
        f"UPDATE acquisition_lines SET {','.join(f'{field}=?' for field in updates)} WHERE id=?",
        (*updates.values(), line_id),
    )
    db.execute(
        """UPDATE acquisitions SET state='ACQUISITION_INCOMPLETE',financial_facts_confirmed=0,
                  reconciliation_confirmed=0,confirmed_at=NULL,revision=revision+1,updated_at=? WHERE id=?""",
        (utcnow(), acquisition["id"]),
    )
    _event(
        db,
        request_id=request_id,
        acquisition_id=int(acquisition["id"]),
        line_id=line_id,
        event_type="LINE_AUTOSAVED",
        from_state=str(acquisition["state"]),
        to_state="ACQUISITION_INCOMPLETE",
        payload={
            "fields": sorted(field for field in updates if field != "updated_at"),
            "catalog_link_removed": catalog_link_removed,
        },
    )
    return acquisition_payload(db, int(acquisition["id"]))


def confirm_line_allocation(db: sqlite3.Connection, line_id: int, payload: Mapping[str, object]) -> dict:
    request_id = _required_request_id(payload)
    line = _line_row(db, line_id)
    acquisition = _acquisition_row(db, int(line["acquisition_id"]))
    replay = _replay_acquisition(db, request_id, int(acquisition["id"]))
    if replay:
        return replay
    _require_revision(acquisition, payload)
    _require_draft_mutable(acquisition)
    if not _confirmed(payload.get("confirm_allocation")):
        raise ValueError("Explicit product-line allocation confirmation is required")
    cents = _optional_cents(
        payload.get("assigned_landed_cost_cents", line["assigned_landed_cost_cents"]),
        "Assigned landed cost",
    )
    if cents is None:
        raise ValueError("Assigned landed cost is required")
    method = _text(payload.get("allocation_method", line["allocation_method"]), 30).upper()
    if method not in ALLOCATION_METHODS:
        raise ValueError("A disclosed allocation method is required")
    now = utcnow()
    db.execute(
        """UPDATE acquisition_lines SET assigned_landed_cost_cents=?,allocation_method=?,
                  allocation_status='CONFIRMED',updated_at=? WHERE id=?""",
        (cents, method, now, line_id),
    )
    db.execute(
        """UPDATE acquisitions SET state='ACQUISITION_INCOMPLETE',financial_facts_confirmed=0,
                  reconciliation_confirmed=0,confirmed_at=NULL,revision=revision+1,updated_at=? WHERE id=?""",
        (now, acquisition["id"]),
    )
    _event(
        db,
        request_id=request_id,
        acquisition_id=int(acquisition["id"]),
        line_id=line_id,
        event_type="ALLOCATION_CONFIRMED",
        from_state=str(acquisition["state"]),
        to_state="ACQUISITION_INCOMPLETE",
        payload={
            "assigned_landed_cost_cents": cents,
            "allocation_method": method,
            "automatic": False,
            "calculation_version": INBOUND_CALCULATION_VERSION,
        },
    )
    return acquisition_payload(db, int(acquisition["id"]))


def _validate_lines_for_confirmation(lines: list[dict]) -> None:
    active = [line for line in lines if not line["canceled_at"]]
    if not active:
        raise ValueError("At least one active product line is required")
    for line in active:
        label = f"Product line {line['line_sequence']}"
        if not line["game"]:
            raise ValueError(f"{label} requires a TCG")
        if line["product_class"] == "SINGLE_CARDS" and not line["set_code"]:
            raise ValueError(f"{label} requires a set")
        if line["product_class"] != "SINGLE_CARDS" and not line["product_name"]:
            raise ValueError(f"{label} requires a product type")
        if not line["quantity"]:
            raise ValueError(f"{label} requires a quantity")
        if line["product_class"] in ("PACK_PRODUCT", "SEALED_PRODUCT") and line["quantity_certainty"] != "KNOWN":
            raise ValueError(f"{label} requires a known physical quantity")
        if line["product_class"] == "SINGLE_CARDS":
            if line["quantity_certainty"] not in ("ESTIMATED", "KNOWN"):
                raise ValueError(f"{label} requires an estimated or known quantity")
            if line["singles_cost_mode"] not in ("KNOWN_LINE_COSTS", "LUMP_SUM"):
                raise ValueError(f"{label} requires a singles cost mode")
        if line["allocation_status"] != "CONFIRMED" or line["assigned_landed_cost_cents"] is None:
            raise ValueError(f"{label} landed-cost allocation is not confirmed")
        if line["allocation_method"] not in ALLOCATION_METHODS:
            raise ValueError(f"{label} allocation method is not disclosed")


def mark_reconciliation_required(db: sqlite3.Connection, acquisition_id: int, payload: Mapping[str, object]) -> dict:
    request_id = _required_request_id(payload)
    replay = _replay_acquisition(db, request_id, acquisition_id)
    if replay:
        return replay
    row = _acquisition_row(db, acquisition_id)
    _require_revision(row, payload)
    if row["state"] != "ACQUISITION_INCOMPLETE":
        raise ValueError("Only an incomplete acquisition can enter reconciliation")
    count = int(db.execute("SELECT COUNT(*) FROM acquisition_lines WHERE acquisition_id=? AND canceled_at IS NULL", (acquisition_id,)).fetchone()[0])
    if not count:
        raise ValueError("Add at least one product line before reconciliation")
    now = utcnow()
    db.execute(
        "UPDATE acquisitions SET state='RECONCILIATION_REQUIRED',revision=revision+1,updated_at=? WHERE id=?",
        (now, acquisition_id),
    )
    _event(
        db,
        request_id=request_id,
        acquisition_id=acquisition_id,
        event_type="STATE_TRANSITION",
        from_state="ACQUISITION_INCOMPLETE",
        to_state="RECONCILIATION_REQUIRED",
    )
    return acquisition_payload(db, acquisition_id)


def confirm_acquisition(db: sqlite3.Connection, acquisition_id: int, payload: Mapping[str, object]) -> dict:
    from dex_receipts import (
        accept_allocation_on_confirmation,
        accept_confirmed_provenance,
        allocation_for_confirmation,
        receipt_intelligence_payload,
    )

    request_id = _required_request_id(payload)
    replay = _replay_acquisition(db, request_id, acquisition_id)
    if replay:
        return replay
    row = _acquisition_row(db, acquisition_id)
    _require_revision(row, payload)
    _require_draft_mutable(row)
    if not row["source_scope"] or not row["merchant_name"] or not row["purchased_on"] or not row["payment_method"]:
        raise ValueError("Purchase source, merchant, purchase date, and payment method are required")
    if row["final_usd_paid_cents"] is None:
        raise ValueError("Final USD paid is required; missing authoritative cost is never treated as $0.00")
    if not _confirmed(payload.get("confirm_authoritative_financial_facts")):
        raise ValueError("Explicit authoritative financial-facts confirmation is required")
    if not _confirmed(payload.get("confirm_reconciliation")):
        raise ValueError("Explicit reconciliation confirmation is required")
    lines = [dict(item) for item in db.execute("SELECT * FROM acquisition_lines WHERE acquisition_id=? ORDER BY line_sequence", (acquisition_id,)).fetchall()]
    active_lines = [line for line in lines if not line["canceled_at"]]
    receipt_intelligence = receipt_intelligence_payload(db, acquisition_id)
    if receipt_intelligence.get("warnings"):
        raise ValueError("Receipt intelligence still needs attention before confirmation")
    receipt_proposal = allocation_for_confirmation(db, acquisition_id, int(row["final_usd_paid_cents"])) if len(active_lines) > 1 else None
    automatic_line: dict | None = None
    if len(active_lines) == 1 and active_lines[0]["allocation_status"] != "CONFIRMED":
        line = active_lines[0]
        line["assigned_landed_cost_cents"] = int(row["final_usd_paid_cents"])
        line["allocation_method"] = "SINGLE_LINE_100_PERCENT"
        line["allocation_status"] = "CONFIRMED"
        automatic_line = line
    elif len(active_lines) > 1 and receipt_proposal is not None:
        proposed = {int(item["acquisition_line_id"]): int(item["landed_cost_cents"]) for item in receipt_proposal["allocations"]}
        for line in active_lines:
            if int(line["id"]) in proposed:
                line["assigned_landed_cost_cents"] = proposed[int(line["id"])]
                line["allocation_method"] = "RECEIPT_VALUE_PROPORTIONAL"
                line["allocation_status"] = "CONFIRMED"
    _validate_lines_for_confirmation(lines)
    reconciliation = reconciliation_payload(dict(row), lines)
    if not reconciliation["allocation_reconciled"]:
        raise ValueError("Confirmed product-line landed costs must equal final USD paid exactly")
    difference = reconciliation["difference_cents"]
    reason = str(row["discrepancy_reason_code"] or "")
    notes = str(row["discrepancy_notes"] or "")
    if int(row["final_usd_paid_cents"]) == 0:
        if reason != "EXPLICIT_ZERO_COST":
            raise ValueError("Explicit $0.00 acquisitions require the EXPLICIT_ZERO_COST reason")
        if not _confirmed(payload.get("confirm_zero_cost")):
            raise ValueError("Explicit $0.00 acquisitions require special confirmation")
    if difference and not reason:
        raise ValueError("A discrepancy reason is required for every nonzero difference")
    if reconciliation["material"]:
        if not notes:
            raise ValueError("Material discrepancies require explanatory notes")
        if not _confirmed(payload.get("confirm_material_discrepancy")):
            raise ValueError("Material discrepancy confirmation is required")
        if payload.get("reentered_final_usd_paid_cents") != row["final_usd_paid_cents"]:
            raise ValueError("Re-enter final USD paid exactly to confirm a material discrepancy")
    if reconciliation["extreme"] and not _confirmed(payload.get("confirm_extreme_discrepancy")):
        raise ValueError("Extreme 50%+ discrepancy requires severe-escalation confirmation")
    now = utcnow()
    automatic_allocation_event_id = None
    if automatic_line is not None:
        db.execute(
            """UPDATE acquisition_lines
                  SET assigned_landed_cost_cents=?,allocation_method='SINGLE_LINE_100_PERCENT',
                      allocation_status='CONFIRMED',updated_at=?
                WHERE id=?""",
            (int(row["final_usd_paid_cents"]), now, int(automatic_line["id"])),
        )
        quantity = int(automatic_line["quantity"] or 0)
        cents = int(row["final_usd_paid_cents"])
        per_unit = None
        if quantity:
            base, remainder = divmod(cents, quantity)
            per_unit = {
                "base_cents": base,
                "remainder_units": remainder,
                "quantity": quantity,
                "minimum_cents": base,
                "maximum_cents": base + (1 if remainder else 0),
                "exact_when_uniform": remainder == 0,
            }
        automatic_allocation_event_id = _event(
            db,
            request_id=f"{request_id}:single-line-allocation",
            acquisition_id=acquisition_id,
            line_id=int(automatic_line["id"]),
            event_type="ALLOCATION_CONFIRMED",
            from_state=str(row["state"]),
            to_state=str(row["state"]),
            reason_code="SINGLE_LINE_100_PERCENT",
            payload={
                "calculation_version": INBOUND_CALCULATION_VERSION,
                "allocation_method": "SINGLE_LINE_100_PERCENT",
                "automatic": True,
                "source_facts": {
                    "final_usd_paid_cents": cents,
                    "active_product_line_count": 1,
                    "quantity": quantity,
                    "line_uuid": automatic_line["line_uuid"],
                },
                "result": {
                    "assigned_landed_cost_cents": cents,
                    "per_unit_cost": per_unit,
                },
            },
        )
    if receipt_proposal is not None:
        accept_allocation_on_confirmation(db, acquisition_id, receipt_proposal, request_id)
        automatic_allocation_event_id = f"RECEIPT-PROPOSAL-{receipt_proposal['id']}"
    accept_confirmed_provenance(db, acquisition_id, request_id)
    db.execute(
        """UPDATE acquisitions SET state='READY_FOR_INTAKE',financial_facts_confirmed=1,
                  reconciliation_confirmed=1,confirmed_at=?,revision=revision+1,updated_at=? WHERE id=?""",
        (now, now, acquisition_id),
    )
    _event(
        db,
        request_id=request_id,
        acquisition_id=acquisition_id,
        event_type="AUTHORITATIVE_CONFIRMATION",
        from_state=str(row["state"]),
        to_state="READY_FOR_INTAKE",
        reason_code=reason,
        notes=notes,
        payload={
            "calculation_version": INBOUND_CALCULATION_VERSION,
            "reconciliation": reconciliation,
            "automatic_allocation_event_id": automatic_allocation_event_id,
            "operator_confirmed_acquisition": True,
        },
    )
    return acquisition_payload(db, acquisition_id)


def cancel_acquisition(db: sqlite3.Connection, acquisition_id: int, payload: Mapping[str, object]) -> dict:
    request_id = _required_request_id(payload)
    replay = _replay_acquisition(db, request_id, acquisition_id)
    if replay:
        return replay
    row = _acquisition_row(db, acquisition_id)
    _require_revision(row, payload)
    if row["state"] not in ("ACQUISITION_INCOMPLETE", "RECONCILIATION_REQUIRED", "READY_FOR_INTAKE"):
        raise ValueError("Only an active draft or Ready for Intake acquisition can be canceled")
    removal = acquisition_removal_eligibility(db, acquisition_id)
    if removal["protected_downstream_history"]:
        raise ValueError(removal["blocked_message"])
    reason, notes = _removal_reason(payload, notes_required=row["state"] == "READY_FOR_INTAKE")
    now = utcnow()
    db.execute(
        """UPDATE acquisitions SET state='CANCELED',canceled_at=?,cancel_reason_code=?,
                  cancel_notes=?,revision=revision+1,updated_at=? WHERE id=?""",
        (now, reason, notes, now, acquisition_id),
    )
    _event(
        db,
        request_id=request_id,
        acquisition_id=acquisition_id,
        event_type="CANCELED",
        from_state=str(row["state"]),
        to_state="CANCELED",
        reason_code=reason,
        notes=notes,
    )
    return acquisition_payload(db, acquisition_id)


def recycle_draft_acquisition(db: sqlite3.Connection, acquisition_id: int, payload: Mapping[str, object]) -> dict:
    request_id = _required_request_id(payload)
    replay = _replay_acquisition(db, request_id, acquisition_id)
    if replay:
        return replay
    row = _acquisition_row(db, acquisition_id)
    _require_revision(row, payload)
    removal = acquisition_removal_eligibility(db, acquisition_id)
    if not removal["can_recycle_draft"]:
        raise ValueError(removal["blocked_message"] or "Only an unprotected incomplete acquisition can move to Recycle Bin")
    reason, notes = _removal_reason(payload, notes_required=False)
    now = utcnow()
    db.execute(
        """UPDATE acquisitions
              SET state='CANCELED',canceled_at=?,cancel_reason_code=?,cancel_notes=?,
                  recycled_at=?,recycle_reason_code=?,recycle_notes=?,pre_recycle_state=?,
                  revision=revision+1,updated_at=?
            WHERE id=?""",
        (now, reason, notes, now, reason, notes, row["state"], now, acquisition_id),
    )
    _event(
        db,
        request_id=request_id,
        acquisition_id=acquisition_id,
        event_type="CANCELED",
        from_state=str(row["state"]),
        to_state="CANCELED",
        reason_code=reason,
        notes=notes,
        payload={"disposition": "RECYCLED_DRAFT", "hard_deleted": False},
    )
    return acquisition_payload(db, acquisition_id)


def restore_recycled_acquisition(db: sqlite3.Connection, acquisition_id: int, payload: Mapping[str, object]) -> dict:
    request_id = _required_request_id(payload)
    replay = _replay_acquisition(db, request_id, acquisition_id)
    if replay:
        return replay
    row = _acquisition_row(db, acquisition_id)
    _require_revision(row, payload)
    removal = acquisition_removal_eligibility(db, acquisition_id)
    if not removal["can_restore"]:
        raise ValueError(removal["blocked_message"] or "This acquisition is not eligible for restore")
    restore_state = str(row["pre_recycle_state"])
    now = utcnow()
    db.execute(
        """UPDATE acquisitions
              SET state=?,canceled_at=NULL,cancel_reason_code='',cancel_notes='',
                  recycled_at=NULL,recycle_reason_code='',recycle_notes='',pre_recycle_state=NULL,
                  revision=revision+1,updated_at=?
            WHERE id=?""",
        (restore_state, now, acquisition_id),
    )
    _event(
        db,
        request_id=request_id,
        acquisition_id=acquisition_id,
        event_type="STATE_TRANSITION",
        from_state="CANCELED",
        to_state=restore_state,
        reason_code="RESTORED_FROM_RECYCLE",
        payload={"restored_tombstone": True},
    )
    return acquisition_payload(db, acquisition_id)
