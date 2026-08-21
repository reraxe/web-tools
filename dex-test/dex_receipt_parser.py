"""Structured, non-authoritative receipt parsing and arithmetic analysis."""

from __future__ import annotations

import itertools
import re
import time
from datetime import datetime

from dex_receipt_semantics import classify_receipt_pages


PARSER_VERSION = "receipt-structured-math-v1"


def money_cents(value: str) -> int:
    cleaned = value.strip().replace(",", "").replace("$", "").replace("−", "-")
    negative = cleaned.startswith("-") or (cleaned.startswith("(") and cleaned.endswith(")"))
    cleaned = cleaned.strip("-() ")
    if not re.fullmatch(r"\d+(?:\.\d{1,2})?", cleaned):
        raise ValueError("Invalid money")
    dollars, _, decimals = cleaned.partition(".")
    cents = int(dollars) * 100 + int((decimals + "00")[:2])
    return -cents if negative else cents


def confidence_band(value: float) -> str:
    return "HIGH" if value >= 0.85 else "MEDIUM" if value >= 0.60 else "LOW"


def _candidate(field: str, value: object, value_type: str, confidence: float,
               page: int, location: str) -> dict:
    return {
        "field_name": field, "normalized_value": str(value), "value_type": value_type,
        "confidence": round(confidence, 4), "confidence_band": confidence_band(confidence),
        "source_page": page, "source_location": location[:160],
    }


def _date(value: str) -> str | None:
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%m-%d-%y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _normalize_label(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def _component_kind(label: str) -> str | None:
    normalized = _normalize_label(label)
    if "subtotal" in normalized:
        return "SUBTOTAL"
    if normalized in ("total", "final paid", "amount paid", "amount due", "grand total", "charged"):
        return "FINAL_PAID"
    if re.search(r"\b(?:sales|state|county|local)?\s*tax\b", normalized):
        return "TAX"
    if "fee" in normalized or "surcharge" in normalized or "handling" in normalized:
        return "FEE"
    if (
        "discount" in normalized or "credit" in normalized or "coupon" in normalized
        or re.search(r"\b\d+(?:\s+\d+)?\s+off\b", normalized)
    ):
        return "DISCOUNT"
    if "shipping" in normalized or "delivery" in normalized:
        return "SHIPPING"
    if "duties" in normalized or normalized == "duty" or "import charge" in normalized:
        return "DUTIES"
    if "brokerage" in normalized or "customs broker" in normalized:
        return "BROKERAGE"
    return None


def _amount_at_end(line: str) -> tuple[str, int] | None:
    match = re.match(
        r"^(.*?)\s+(-?\(?\s*\$?\s*[\d,]+(?:\.\d{2})\s*\)?)\s*$", line
    )
    if not match:
        return None
    try:
        return match.group(1).strip(" .:-"), money_cents(match.group(2).replace(" ", ""))
    except ValueError:
        return None


def _parse_item(line: str, page: int, location: str) -> dict | None:
    if line.upper().startswith("ITEM |"):
        parts = [part.strip() for part in line.split("|")[1:] if part.strip()]
        if not parts:
            return None
        result = {
            "description": parts[0][:300], "quantity": None, "unit_price_cents": None,
            "line_total_cents": None, "currency": "", "extracted_identifier": "",
            "manufacturer_product_code": "", "confidence": 0.94,
            "source_page": page, "source_location": location,
        }
        for part in parts[1:]:
            key, _, raw = part.partition(" ")
            key, raw = key.upper().rstrip(":"), raw.strip().lstrip(":").strip()
            try:
                if key in ("QTY", "QUANTITY"):
                    result["quantity"] = int(raw)
                elif key == "UNIT":
                    result["unit_price_cents"] = money_cents(raw)
                elif key == "TOTAL":
                    result["line_total_cents"] = money_cents(raw)
                elif key in ("UPC", "EAN", "GTIN"):
                    result["extracted_identifier"] = re.sub(r"\D", "", raw)
                elif key in ("CODE", "SKU", "MPN"):
                    result["manufacturer_product_code"] = raw[:100]
            except (TypeError, ValueError):
                result["confidence"] = 0.62
        if result["line_total_cents"] is None and result["quantity"] and result["unit_price_cents"] is not None:
            result["line_total_cents"] = int(result["quantity"]) * int(result["unit_price_cents"])
        result["confidence_band"] = confidence_band(float(result["confidence"]))
        return result

    amount = _amount_at_end(line)
    if not amount:
        return None
    description, total = amount
    if not description or _component_kind(description):
        return None
    quantity = None
    unit = None
    prefix = re.match(r"^(\d+)\s*[xX]?\s+(.+)$", description)
    suffix = re.match(r"^(.+?)\s+[xX]\s*(\d+)\s*$", description)
    at_price = re.match(r"^(\d+)\s+(.+?)\s+@\s*\$?([\d,]+(?:\.\d{1,2})?)$", description)
    if at_price:
        quantity = int(at_price.group(1))
        description = at_price.group(2).strip()
        unit = money_cents(at_price.group(3))
    elif suffix:
        description, quantity = suffix.group(1).strip(), int(suffix.group(2))
    elif prefix and int(prefix.group(1)) <= 999:
        quantity, description = int(prefix.group(1)), prefix.group(2).strip()
    inline_identifier = re.search(r"\b(?:UPC|EAN|GTIN)\s*[:#]?\s*(\d{8,14})\b", description, re.I)
    result = {
        "description": description[:300], "quantity": quantity,
        "unit_price_cents": unit if unit is not None else (total // quantity if quantity and total % quantity == 0 else None),
        "line_total_cents": total, "currency": "USD" if "$" in line else "",
        "extracted_identifier": inline_identifier.group(1) if inline_identifier else "",
        "manufacturer_product_code": "", "confidence": 0.9,
        "source_page": page, "source_location": location,
    }
    result["confidence_band"] = confidence_band(result["confidence"])
    return result


def _subset_solutions(components: list[dict], target: int) -> list[tuple[int, ...]]:
    if len(components) > 12:
        return []
    solutions: list[tuple[int, ...]] = []
    for size in range(len(components) + 1):
        for indexes in itertools.combinations(range(len(components)), size):
            if sum(int(components[index]["signed_cents"]) for index in indexes) == target:
                solutions.append(indexes)
    return solutions


def _analyze_math(lines: list[dict], components: list[dict], subtotal: int | None,
                  final_paid: int | None) -> dict:
    merchandise_total = sum(int(item["line_total_cents"] or 0) for item in lines)
    ordinary = [item for item in components if item["kind"] not in ("SUBTOTAL", "FINAL_PAID")]
    result = {
        "version": PARSER_VERSION, "status": "INCOMPLETE", "ambiguous": False,
        "merchandise_total_cents": merchandise_total,
        "printed_subtotal_cents": subtotal, "final_paid_cents": final_paid,
        "components": [dict(item) for item in ordinary], "equations": [],
        "difference_cents": None, "allocation_ready": False,
    }
    if subtotal is None or final_paid is None:
        return result
    subtotal_delta = subtotal - merchandise_total
    included_solutions = _subset_solutions(ordinary, subtotal_delta)
    if not included_solutions:
        result.update(status="UNRECONCILED", difference_cents=final_paid - subtotal)
        return result
    preferred = [
        solution for solution in included_solutions
        if all(ordinary[index]["sequence"] < next(
            (item["sequence"] for item in components if item["kind"] == "SUBTOTAL"), 10**9
        ) for index in solution)
    ]
    included_solutions = preferred or included_solutions
    complete: list[tuple[tuple[int, ...], tuple[int, ...]]] = []
    for included in included_solutions:
        remaining = [item for index, item in enumerate(ordinary) if index not in included]
        outside_solutions = _subset_solutions(remaining, final_paid - subtotal)
        for outside in outside_solutions:
            outside_original = tuple(
                index for index, item in enumerate(ordinary)
                if item in [remaining[position] for position in outside]
            )
            complete.append((included, outside_original))
    unique = list(dict.fromkeys(complete))
    subtotal_sequence = next(
        (item["sequence"] for item in components if item["kind"] == "SUBTOTAL"), 0
    )
    if len(unique) > 1:
        coverage = [
            sum(1 for index in outside if ordinary[index]["sequence"] > subtotal_sequence)
            for _, outside in unique
        ]
        best = max(coverage)
        unique = [solution for solution, score in zip(unique, coverage) if score == best]
    if len(unique) != 1:
        result.update(
            status="AMBIGUOUS" if unique else "UNRECONCILED",
            ambiguous=len(unique) > 1,
            difference_cents=final_paid - subtotal,
        )
        return result
    included, outside = unique[0]
    for index, item in enumerate(result["components"]):
        item["math_role"] = (
            "INCLUDED_IN_SUBTOTAL" if index in included
            else "OUTSIDE_SUBTOTAL" if index in outside
            else "INFORMATIONAL_OR_DUPLICATE"
        )
    result["equations"] = [
        {
            "label": "Printed subtotal",
            "left_cents": merchandise_total + sum(ordinary[index]["signed_cents"] for index in included),
            "right_cents": subtotal,
            "difference_cents": 0,
        },
        {
            "label": "Final paid",
            "left_cents": subtotal + sum(ordinary[index]["signed_cents"] for index in outside),
            "right_cents": final_paid,
            "difference_cents": 0,
        },
    ]
    result.update(status="RECONCILED_EXACT", difference_cents=0, allocation_ready=True)
    return result


def parse_receipt_pages(pages: list[tuple[int, str]]) -> dict:
    started = time.perf_counter()
    located: list[tuple[int, int, int, str]] = []
    sequence = 0
    for page, text in pages:
        for line_number, raw in enumerate(text.splitlines(), 1):
            line = " ".join(raw.replace("\t", " ").split())
            if line:
                sequence += 1
                located.append((sequence, page, line_number, line))
    if not located:
        return {
            "candidates": [], "lines": [], "semantic_candidate_lines": [], "semantic_lines": [],
            "receipt_math": {"status": "INCOMPLETE"},
            "metrics": {"structured_parsing_ms": 0.0},
        }

    semantic_lines = classify_receipt_pages(pages, parser_version=PARSER_VERSION)
    semantic_by_source_index = {
        int(item["source_line_index"]): item for item in semantic_lines
    }

    candidates: dict[str, dict] = {}
    receipt_lines: list[dict] = []
    merchandise_lines: list[dict] = []
    components: list[dict] = []
    subtotal = None
    final_paid = None
    structural_sequences: set[int] = set()
    currency = ""

    for seq, page, line_number, line in located:
        location = f"line {line_number}"
        semantic_class = semantic_by_source_index.get(seq, {}).get("semantic_class")
        amount = _amount_at_end(line)
        if amount:
            label, cents = amount
            kind = _component_kind(label)
            if kind:
                if kind == "DISCOUNT" and cents > 0:
                    cents = -cents
                component = {
                    "kind": kind, "label": label[:120], "signed_cents": cents,
                    "sequence": seq, "source_page": page, "source_location": location,
                    "confidence": 0.95,
                    "scope": (
                        "LINE_ITEM"
                        if kind == "DISCOUNT" and re.search(r"\b(?:item|line)\b", _normalize_label(label))
                        else "PURCHASE"
                    ),
                }
                components.append(component)
                structural_sequences.add(seq)
                if kind == "SUBTOTAL":
                    subtotal = abs(cents)
                elif kind == "FINAL_PAID":
                    final_paid = abs(cents)

        date_match = re.search(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", line)
        if date_match and "purchased_on" not in candidates:
            parsed = _date(date_match.group(1).replace("-", "/") if re.match(r"\d{1,2}-", date_match.group(1)) else date_match.group(1))
            if parsed:
                candidates["purchased_on"] = _candidate("purchased_on", parsed, "DATE", 0.92, page, location)
        order_match = re.search(r"(?:order|receipt|invoice)(?:\s*(?:number|no\.?|#))?\s*[#:]*\s*([A-Za-z0-9][A-Za-z0-9._/-]{2,})", line, re.I)
        if order_match:
            candidates["order_reference"] = _candidate("order_reference", order_match.group(1), "TEXT", 0.91, page, location)
        if semantic_class == "TENDER_PAYMENT_METHOD" and re.search(r"\b(?:credit|debit)(?:\s+card)?\b", line, re.I):
            candidates["payment_method"] = _candidate("payment_method", "CREDIT_DEBIT_CARD", "TEXT", 0.9, page, location)
        elif semantic_class == "TENDER_PAYMENT_METHOD" and re.search(r"\bpaypal\b", line, re.I):
            candidates["payment_method"] = _candidate("payment_method", "PAYPAL", "TEXT", 0.94, page, location)
        elif semantic_class == "TENDER_PAYMENT_METHOD" and re.search(r"\bcash\b", line, re.I):
            candidates["payment_method"] = _candidate("payment_method", "CASH", "TEXT", 0.9, page, location)
        currency_match = re.search(r"(?:currency|charged\s+in)\s*[:#]\s*([A-Z]{3})\b", line, re.I)
        if currency_match:
            currency = currency_match.group(1).upper()
            candidates["original_currency"] = _candidate("original_currency", currency, "CURRENCY", 0.97, page, location)
            candidates["source_scope"] = _candidate("source_scope", "DOMESTIC" if currency == "USD" else "INTERNATIONAL", "SCOPE", 0.94, page, location)
        foreign_match = re.search(r"(?:original|foreign)\s+(?:amount|total)\s*[:#]\s*(?:[A-Z]{3})?\s*([\d,]+(?:\.\d{1,2})?)", line, re.I)
        if foreign_match:
            candidates["original_foreign_amount_minor"] = _candidate(
                "original_foreign_amount_minor", money_cents(foreign_match.group(1)), "INTEGER", 0.94, page, location
            )

    for seq, page, line_number, line in located:
        if seq in structural_sequences:
            continue
        parsed = _parse_item(line, page, f"line {line_number}")
        semantic = semantic_by_source_index.get(seq, {})
        if parsed and parsed["line_total_cents"] is not None and parsed["line_total_cents"] >= 0:
            parsed["_sequence"] = seq
            parsed["source_line_index"] = seq
            receipt_lines.append(parsed)
            if semantic.get("semantic_class") == "MERCHANDISE":
                merchandise_lines.append(parsed)

    # Line-level discounts remain receipt evidence, not authoritative inventory
    # allocation.  Link only by source adjacency and preserve that provenance so
    # Review can disclose what DEX inferred without pretending the label is fact.
    for component in components:
        if component.get("scope") != "LINE_ITEM":
            continue
        preceding = [item for item in merchandise_lines if int(item["_sequence"]) < int(component["sequence"])]
        if preceding:
            related = max(preceding, key=lambda item: int(item["_sequence"]))
            component["applies_to_source_sequence"] = int(related["_sequence"])
            component["applies_to_description"] = related["description"]
    for item in receipt_lines:
        item.pop("_sequence", None)

    first = located[0]
    merchant_candidates = [
        line for seq, _, _, line in located[:5]
        if seq not in structural_sequences
        and not re.search(r"\b(?:receipt|invoice|order|date|www\.|tel\.?|phone)\b", line, re.I)
        and not _amount_at_end(line)
    ]
    explicit_merchant = next((
        re.sub(r"^(?:merchant|seller)\s*[:#]\s*", "", line, flags=re.I)
        for _, _, _, line in located if re.match(r"^(?:merchant|seller)\s*[:#]", line, re.I)
    ), "")
    merchant = explicit_merchant or (merchant_candidates[0] if merchant_candidates else "")
    if merchant:
        candidates["merchant_name"] = _candidate("merchant_name", merchant[:180], "TEXT", 0.96 if explicit_merchant else 0.9, first[1], f"line {first[2]}")
    candidates.setdefault("source_scope", _candidate("source_scope", "DOMESTIC", "SCOPE", 0.86, 1, "USD receipt context"))

    receipt_math = _analyze_math(merchandise_lines, components, subtotal, final_paid)
    if subtotal is not None:
        candidates["purchase_subtotal_cents"] = _candidate("purchase_subtotal_cents", subtotal, "CENTS", 0.96, 1, "printed subtotal")
    if final_paid is not None and currency not in ("", "USD"):
        candidates.setdefault("original_foreign_amount_minor", _candidate(
            "original_foreign_amount_minor", final_paid, "INTEGER", 0.93, 1, "printed foreign-currency total"
        ))
    elif final_paid is not None:
        candidates["final_usd_paid_cents"] = _candidate("final_usd_paid_cents", final_paid, "CENTS", 0.97, 1, "printed final paid")
    if receipt_math.get("status") == "RECONCILED_EXACT":
        outside = [item for item in receipt_math["components"] if item.get("math_role") == "OUTSIDE_SUBTOTAL"]
        field_map = {
            "TAX": "acquisition_tax_cents", "SHIPPING": "inbound_shipping_cents",
            "FEE": "acquisition_fees_cents", "DISCOUNT": "acquisition_discount_cents",
            "DUTIES": "import_duties_cents", "BROKERAGE": "brokerage_cents",
        }
        for kind, field in field_map.items():
            values = [int(item["signed_cents"]) for item in outside if item["kind"] == kind]
            if values:
                value = sum(values)
                if kind == "DISCOUNT":
                    value = abs(value)
                if value >= 0:
                    candidates[field] = _candidate(field, value, "CENTS", 0.95, 1, f"receipt math: {kind.lower()} outside subtotal")

    return {
        "candidates": list(candidates.values()), "lines": merchandise_lines,
        "semantic_candidate_lines": receipt_lines,
        "semantic_lines": semantic_lines,
        "receipt_math": receipt_math,
        "metrics": {"structured_parsing_ms": round((time.perf_counter() - started) * 1000, 2)},
        "parser_version": PARSER_VERSION,
    }
