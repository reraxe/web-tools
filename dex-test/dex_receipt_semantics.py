"""Non-authoritative, auditable receipt-line semantic classification.

This module classifies every normalized source line before product matching.
Semantic meaning is deliberately separate from inventory/business-purpose
classification and from landed-cost allocation.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Mapping


ENGINE_VERSION = "dex-receipt-semantic-v1"
RULES_VERSION = "receipt-semantic-rules-v1"

SEMANTIC_CLASSES = (
    "MERCHANDISE",
    "DISCOUNT_CREDIT",
    "FEE_SURCHARGE",
    "TAX",
    "SHIPPING",
    "SUBTOTAL",
    "TOTAL",
    "TENDER_PAYMENT_METHOD",
    "PAYMENT_SUMMARY",
    "INFORMATIONAL_FOOTER",
    "STRUCTURAL",
    "UNKNOWN",
)

CONFIDENCE_STATES = (
    "HIGH_CONFIDENCE_SUGGESTION",
    "UNRESOLVED",
    "CONFLICTING",
    "OPERATOR_CONFIRMED",
)

PRODUCT_MATCH_ELIGIBLE_CLASSES = frozenset({"MERCHANDISE"})


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_source_text(value: object) -> str:
    return " ".join(str(value or "").replace("−", "-").replace("\t", " ").split())[:500]


def _normalized_words(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9%]+", " ", value.lower()).split())


def _signed_amount(line: str) -> int | None:
    match = re.search(r"(-?\(?\s*\$?\s*[\d,]+(?:\.\d{2})\s*\)?)\s*$", line)
    if not match:
        return None
    raw = match.group(1).replace("$", "").replace(",", "").replace(" ", "")
    negative = raw.startswith("-") or (raw.startswith("(") and raw.endswith(")"))
    raw = raw.strip("-()")
    try:
        dollars, cents = raw.split(".", 1)
        value = int(dollars) * 100 + int((cents + "00")[:2])
    except (ValueError, TypeError):
        return None
    return -value if negative else value


def _financial_label_words(line: str) -> str:
    """Return normalized label text with one trailing currency amount removed."""

    label = re.sub(
        r"\s+[-+]?\(?\s*\$?\s*(?:[\d,]+(?:\.\d{2})?|\.\d{2})\s*\)?\s*$",
        "",
        line,
    )
    return _normalized_words(label)


def _has_product_context(words: str) -> bool:
    return bool(re.search(
        r"\b(?:booster|pack|box|deck|card|promo|starter|character|figure|sleeves?|playmat|bundle|display|set)\b",
        words,
    ))


def _result(
    *,
    source_line_index: int,
    source_page: int | None,
    source_location: str,
    normalized_text: str,
    semantic_class: str,
    confidence: float,
    parser_version: str,
    evidence_codes: list[str],
    conflicting: bool = False,
) -> dict:
    if conflicting:
        confidence_state = "CONFLICTING"
        status = "CONFLICTING"
        confirmation_required = True
    elif semantic_class == "UNKNOWN" or confidence < 0.60:
        confidence_state = "UNRESOLVED"
        status = "UNRESOLVED"
        confirmation_required = True
    else:
        confidence_state = "HIGH_CONFIDENCE_SUGGESTION"
        status = "PROPOSED"
        confirmation_required = confidence < 0.85
    return {
        "source_line_index": int(source_line_index),
        "source_page": source_page,
        "source_location": source_location[:160],
        "normalized_text": normalized_text,
        "source_line_sha256": hashlib.sha256(normalized_text.encode("utf-8")).hexdigest(),
        "signed_amount_cents": _signed_amount(normalized_text),
        "semantic_class": semantic_class,
        "numeric_confidence": round(float(confidence), 4),
        "confidence_state": confidence_state,
        "parser_version": parser_version,
        "rules_version": RULES_VERSION,
        "engine_version": ENGINE_VERSION,
        "operator_confirmation_required": confirmation_required,
        "semantic_status": status,
        "evidence": {"codes": evidence_codes, "arithmetic_used_as_authority": False},
    }


def classify_source_line(
    line: str,
    *,
    source_line_index: int,
    source_page: int | None,
    source_location: str,
    parser_version: str,
) -> dict:
    """Classify one normalized source line using deterministic local rules."""

    text = normalize_source_text(line)
    words = _normalized_words(text)
    financial_label = _financial_label_words(text)
    amount = _signed_amount(text)
    has_trailing_amount = financial_label != words

    def make(kind: str, confidence: float, *codes: str, conflicting: bool = False) -> dict:
        return _result(
            source_line_index=source_line_index,
            source_page=source_page,
            source_location=source_location,
            normalized_text=text,
            semantic_class=kind,
            confidence=confidence,
            parser_version=parser_version,
            evidence_codes=list(codes),
            conflicting=conflicting,
        )

    if not text:
        return make("STRUCTURAL", 0.96, "EMPTY_OR_SEPARATOR")
    if re.fullmatch(r"[-_=*.:|\s]{3,}", text):
        return make("STRUCTURAL", 0.98, "SEPARATOR")

    component_signals = [
        bool(re.search(r"\b(?:state|county|local|sales)?\s*tax\b", words)),
        bool(re.search(r"\b(?:discount|coupon|savings|promo\s+credit|store\s+credit)\b", words) or re.search(r"\b\d+(?:\.\d+)?%\s+off\b", words)),
        bool(re.search(r"\b(?:fee|surcharge|service\s+charge|handling)\b", words)),
        bool(re.search(r"\b(?:shipping|delivery|freight)\b", words)),
    ]
    if sum(component_signals) > 1:
        return make("UNKNOWN", 0.30, "CONFLICTING_COMPONENT_LABELS", conflicting=True)

    # Financial summaries and tender signals intentionally precede every
    # merchandise heuristic. The label comparison excludes only a trailing
    # currency amount, so product names containing words such as Cash, Visa,
    # Balance, or Card do not match these bounded phrases accidentally.
    if re.fullmatch(
        r"(?:total\s+by\s+(?:cash|card|credit|debit)|"
        r"(?:amount|amt)\s+tendered|cash\s+tendered|tendered?|"
        r"(?:card|cash|amount|amt)\s+paid|payment|paid|"
        r"change(?:\s+due)?|cash\s+back)",
        financial_label,
    ):
        return make("PAYMENT_SUMMARY", 0.97, "PAYMENT_SUMMARY_PHRASE")
    if re.fullmatch(
        r"(?:(?:credit\s+debit|debit\s+credit)|debit|credit)(?:\s+card)?(?:\s+(?:sale|payment))?",
        financial_label,
    ) or re.fullmatch(
        r"(?:visa|mastercard|mc|amex|discover|cash|paypal)(?:\s+(?:sale|payment))?",
        financial_label,
    ) or re.fullmatch(
        r"(?:card|credit\s+card|debit\s+card|debit)\s+payment",
        financial_label,
    ):
        return make("TENDER_PAYMENT_METHOD", 0.97, "TENDER_PHRASE")

    if "subtotal" in words:
        return make("SUBTOTAL", 0.99, "SUBTOTAL_LABEL")
    if re.fullmatch(
        r"(?:(?:grand\s+)?total|final\s+paid|(?:amount|amt)\s+due|balance\s+due|charged)",
        financial_label,
    ):
        return make("TOTAL", 0.99, "TOTAL_LABEL")
    if re.fullmatch(r"tx", financial_label) and has_trailing_amount:
        return make("TAX", 0.88, "TAX_ABBREVIATION", "AMOUNT_LABEL")
    if re.search(r"\b(?:state|county|local|sales)?\s*tax\b", words):
        return make("TAX", 0.98, "TAX_LABEL", "PERCENTAGE_PRESENT" if "%" in words else "AMOUNT_LABEL")
    if re.search(r"\b(?:discount|coupon|savings|promo\s+credit|store\s+credit)\b", words) or re.search(r"\b\d+(?:\.\d+)?%\s+off\b", words):
        return make("DISCOUNT_CREDIT", 0.97, "DISCOUNT_OR_CREDIT_LABEL", "NEGATIVE_AMOUNT" if amount is not None and amount < 0 else "SIGNED_AMOUNT_UNKNOWN")
    if re.search(r"\b(?:fee|surcharge|service\s+charge|handling)\b", words):
        return make("FEE_SURCHARGE", 0.96, "FEE_OR_SURCHARGE_LABEL")
    if re.search(r"\b(?:shipping|delivery|freight)\b", words):
        return make("SHIPPING", 0.96, "SHIPPING_LABEL")

    if re.search(r"\b(?:thank\s+you|returns?\s+(?:accepted|within)|visit\s+us|www\.|http|customer\s+service|all\s+sales\s+final)\b", text, re.I):
        return make("INFORMATIONAL_FOOTER", 0.92, "FOOTER_PHRASE")
    if re.search(r"[?]{2,}|\b(?:unreadable|illegible|smudged)\b", text, re.I):
        return make("UNKNOWN", 0.20, "UNREADABLE_OR_NOISY_OCR")
    if has_trailing_amount and re.fullmatch(
        r"(?:card|cash|visa|mc|debit|credit)\s+(?:pymt|pmt|pd)",
        financial_label,
    ):
        return make("UNKNOWN", 0.30, "AMBIGUOUS_FINANCIAL_LINE")
    if text.upper().startswith("ITEM |"):
        return make("MERCHANDISE", 0.94, "STRUCTURED_ITEM_PREFIX")
    if re.search(r"\b(?:receipt|invoice|transaction|items?|description|qty|quantity|price)\b", words) and amount is None:
        return make("STRUCTURAL", 0.86, "HEADER_OR_SECTION_LABEL")
    if has_trailing_amount and not _has_product_context(financial_label) and re.search(
        r"\b(?:payment|pymt|pmt|paid|tender|tendered|tndr|due|change|cashback)\b",
        financial_label,
    ):
        return make("UNKNOWN", 0.30, "AMBIGUOUS_FINANCIAL_LINE")
    if amount is not None and amount >= 0:
        return make("MERCHANDISE", 0.90, "POSITIVE_LINE_AMOUNT", "NO_COMPONENT_LABEL")
    if amount is not None and amount < 0:
        return make("UNKNOWN", 0.45, "UNLABELED_NEGATIVE_AMOUNT")
    if len(words.split()) <= 8 and amount is None:
        return make("STRUCTURAL", 0.68, "SHORT_NONFINANCIAL_LINE")
    return make("UNKNOWN", 0.35, "NO_DETERMINISTIC_RULE")


def classify_receipt_pages(pages: list[tuple[int, str]], *, parser_version: str) -> list[dict]:
    results: list[dict] = []
    source_index = 0
    for page, text in pages:
        for line_number, raw in enumerate(str(text or "").splitlines(), 1):
            normalized = normalize_source_text(raw)
            if not normalized:
                continue
            source_index += 1
            results.append(classify_source_line(
                normalized,
                source_line_index=source_index,
                source_page=int(page) if page is not None else None,
                source_location=f"line {line_number}",
                parser_version=parser_version,
            ))
    return results


def _current_successor(db: sqlite3.Connection, semantic_line_id: int) -> sqlite3.Row | None:
    return db.execute(
        "SELECT * FROM receipt_semantic_lines WHERE supersedes_semantic_line_id=? ORDER BY id DESC LIMIT 1",
        (semantic_line_id,),
    ).fetchone()


def semantic_line_payload(row: Mapping) -> dict:
    item = dict(row)
    item["evidence"] = json.loads(item.get("evidence") or "{}")
    item["operator_confirmation_required"] = bool(item["operator_confirmation_required"])
    item["product_match_eligible"] = (
        item["semantic_class"] in PRODUCT_MATCH_ELIGIBLE_CLASSES
        and item["confidence_state"] not in ("UNRESOLVED", "CONFLICTING")
        and item["semantic_status"] != "SUPERSEDED"
    )
    item["authoritative"] = False
    return item


def persist_initial_semantics(
    db: sqlite3.Connection,
    *,
    job_id: int,
    acquisition_id: int,
    document_id: int,
    semantic_lines: list[Mapping],
    receipt_line_ids_by_source_index: Mapping[int, int],
) -> None:
    """Persist every classified source line and its immutable creation event."""

    now = utcnow()
    for item in semantic_lines:
        source_index = int(item["source_line_index"])
        semantic_uuid = f"RCPT-SEM-{uuid.uuid4()}"
        cursor = db.execute(
            """INSERT INTO receipt_semantic_lines
               (semantic_uuid,job_id,acquisition_id,document_id,receipt_line_id,
                source_line_index,source_page,source_location,normalized_text,
                source_line_sha256,signed_amount_cents,semantic_class,numeric_confidence,
                confidence_state,parser_version,rules_version,engine_version,
                operator_confirmation_required,semantic_status,recorded_at,evidence)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                semantic_uuid, job_id, acquisition_id, document_id,
                receipt_line_ids_by_source_index.get(source_index), source_index,
                item.get("source_page"), str(item.get("source_location") or "")[:160],
                str(item.get("normalized_text") or "")[:500], item["source_line_sha256"],
                item.get("signed_amount_cents"), item["semantic_class"],
                item.get("numeric_confidence"), item["confidence_state"],
                item["parser_version"], item["rules_version"], item["engine_version"],
                1 if item.get("operator_confirmation_required") else 0,
                item["semantic_status"], now,
                json.dumps(item.get("evidence") or {}, sort_keys=True),
            ),
        )
        semantic_id = int(cursor.lastrowid)
        db.execute(
            """INSERT INTO receipt_semantic_events
               (event_id,request_id,semantic_line_id,job_id,acquisition_id,event_type,
                from_semantic_class,to_semantic_class,effective_at,recorded_at,payload)
               VALUES (?,?,?,?,?,'CLASSIFIED',NULL,?,?,?,?)""",
            (
                f"RCPT-SEM-EVT-{uuid.uuid4()}",
                f"SEMANTIC-CLASSIFIED-{job_id}-{source_index}", semantic_id, job_id,
                acquisition_id, item["semantic_class"], now, now,
                json.dumps({
                    "semantic_uuid": semantic_uuid,
                    "confidence_state": item["confidence_state"],
                    "semantic_authority": False,
                    "inventory_authority": False,
                    "allocation_changed": False,
                }, sort_keys=True),
            ),
        )


def current_semantic_lines(
    db: sqlite3.Connection,
    *,
    acquisition_id: int | None = None,
    job_id: int | None = None,
) -> list[dict]:
    clauses = ["NOT EXISTS (SELECT 1 FROM receipt_semantic_lines n WHERE n.supersedes_semantic_line_id=s.id)"]
    params: list[object] = []
    if acquisition_id is not None:
        clauses.append("s.acquisition_id=?")
        params.append(int(acquisition_id))
    if job_id is not None:
        clauses.append("s.job_id=?")
        params.append(int(job_id))
    rows = db.execute(
        f"SELECT s.* FROM receipt_semantic_lines s WHERE {' AND '.join(clauses)} "
        "ORDER BY s.job_id,s.source_page,s.source_line_index,s.id",
        params,
    ).fetchall()
    return [semantic_line_payload(row) for row in rows]


def semantic_review_payload(db: sqlite3.Connection, acquisition_id: int) -> dict:
    lines = current_semantic_lines(db, acquisition_id=acquisition_id)
    counts = {semantic_class: 0 for semantic_class in SEMANTIC_CLASSES}
    for line in lines:
        counts[line["semantic_class"]] += 1
    return {
        "taxonomy_version": RULES_VERSION,
        "engine_version": ENGINE_VERSION,
        "lines": lines,
        "counts": counts,
        "needs_confirmation_count": sum(1 for line in lines if line["operator_confirmation_required"]),
        "product_match_eligible_count": sum(1 for line in lines if line["product_match_eligible"]),
        "authority_rule": "Parser semantics are suggestions. Operator confirmation is separate and creates no inventory or accounting authority.",
    }


def semantic_allows_receipt_line(db: sqlite3.Connection, receipt_line_id: int) -> bool:
    """Preserve HF3 behavior for legacy jobs; gate newly classified jobs."""

    row = db.execute(
        "SELECT job_id FROM receipt_lines WHERE id=?", (int(receipt_line_id),)
    ).fetchone()
    if not row:
        return False
    semantic_count = int(db.execute(
        "SELECT COUNT(*) FROM receipt_semantic_lines WHERE job_id=?", (row["job_id"],)
    ).fetchone()[0])
    if semantic_count == 0:
        return True
    current = db.execute(
        """SELECT s.* FROM receipt_semantic_lines s
             WHERE s.receipt_line_id=?
               AND NOT EXISTS (
                   SELECT 1 FROM receipt_semantic_lines n
                    WHERE n.supersedes_semantic_line_id=s.id
               )
             ORDER BY s.id DESC LIMIT 1""",
        (int(receipt_line_id),),
    ).fetchone()
    return bool(
        current
        and current["semantic_class"] in PRODUCT_MATCH_ELIGIBLE_CLASSES
        and current["confidence_state"] not in ("UNRESOLVED", "CONFLICTING")
    )


def decide_semantic_line(db: sqlite3.Connection, semantic_uuid: str, payload: Mapping) -> dict:
    request_id = str(payload.get("request_id") or "").strip()[:120]
    if not request_id:
        raise ValueError("request_id is required")
    replay = db.execute(
        "SELECT payload FROM receipt_semantic_events WHERE request_id=?", (request_id,)
    ).fetchone()
    if replay:
        recorded = json.loads(replay["payload"] or "{}")
        successor = db.execute(
            "SELECT * FROM receipt_semantic_lines WHERE semantic_uuid=?",
            (recorded.get("successor_semantic_uuid"),),
        ).fetchone()
        if successor:
            result = semantic_line_payload(successor)
            result["idempotent_replay"] = True
            return result

    current = db.execute(
        "SELECT * FROM receipt_semantic_lines WHERE semantic_uuid=?", (semantic_uuid,)
    ).fetchone()
    if not current:
        raise ValueError("Receipt semantic line not found")
    if _current_successor(db, int(current["id"])):
        raise ValueError("Receipt semantic line changed; refresh before recording this decision")

    action = str(payload.get("action") or "").strip().upper()
    reason_code = str(payload.get("reason_code") or "").strip()[:80]
    notes = str(payload.get("notes") or "").strip()[:1000]
    if action == "CONFIRM":
        semantic_class = current["semantic_class"]
        confidence_state = "OPERATOR_CONFIRMED"
        semantic_status = "CONFIRMED"
        confirmation_required = 0
        event_type = "OPERATOR_CONFIRMED"
    elif action == "CHANGE":
        semantic_class = str(payload.get("semantic_class") or "").strip().upper()
        if semantic_class not in SEMANTIC_CLASSES:
            raise ValueError("Choose a supported semantic class")
        if not reason_code:
            raise ValueError("A correction reason is required")
        confidence_state = "OPERATOR_CONFIRMED"
        semantic_status = "CONFIRMED"
        confirmation_required = 0
        event_type = "OPERATOR_CORRECTED"
    elif action == "MARK_UNRESOLVED":
        semantic_class = "UNKNOWN"
        if not reason_code:
            raise ValueError("A reason is required when leaving receipt meaning unresolved")
        confidence_state = "UNRESOLVED"
        semantic_status = "UNRESOLVED"
        confirmation_required = 1
        event_type = "MARKED_UNRESOLVED"
    else:
        raise ValueError("Choose Confirm, Change classification, or Mark unresolved")

    now = utcnow()
    successor_uuid = f"RCPT-SEM-{uuid.uuid4()}"
    cursor = db.execute(
        """INSERT INTO receipt_semantic_lines
           (semantic_uuid,job_id,acquisition_id,document_id,receipt_line_id,
            source_line_index,source_page,source_location,normalized_text,
            source_line_sha256,signed_amount_cents,semantic_class,numeric_confidence,
            confidence_state,parser_version,rules_version,engine_version,
            operator_confirmation_required,semantic_status,recorded_at,
            supersedes_semantic_line_id,evidence)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            successor_uuid, current["job_id"], current["acquisition_id"], current["document_id"],
            current["receipt_line_id"], current["source_line_index"], current["source_page"],
            current["source_location"], current["normalized_text"], current["source_line_sha256"],
            current["signed_amount_cents"], semantic_class, current["numeric_confidence"],
            confidence_state, current["parser_version"], current["rules_version"],
            current["engine_version"], confirmation_required, semantic_status, now,
            current["id"], current["evidence"],
        ),
    )
    successor_id = int(cursor.lastrowid)
    db.execute(
        "UPDATE receipt_semantic_lines SET semantic_status='SUPERSEDED' WHERE id=?",
        (current["id"],),
    )
    db.execute(
        """INSERT INTO receipt_semantic_events
           (event_id,request_id,semantic_line_id,successor_semantic_line_id,job_id,
            acquisition_id,event_type,from_semantic_class,to_semantic_class,
            effective_at,recorded_at,reason_code,notes,payload)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            f"RCPT-SEM-EVT-{uuid.uuid4()}", request_id, current["id"], successor_id,
            current["job_id"], current["acquisition_id"], event_type,
            current["semantic_class"], semantic_class,
            str(payload.get("effective_at") or now)[:40], now, reason_code, notes,
            json.dumps({
                "successor_semantic_uuid": successor_uuid,
                "semantic_authority": False,
                "inventory_authority": False,
                "allocation_changed": False,
            }, sort_keys=True),
        ),
    )
    result = semantic_line_payload(db.execute(
        "SELECT * FROM receipt_semantic_lines WHERE id=?", (successor_id,)
    ).fetchone())
    result["idempotent_replay"] = False
    return result
