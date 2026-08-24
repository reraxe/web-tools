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


ENGINE_VERSION = "dex-receipt-semantic-v1-remediation2"
RULES_VERSION = "receipt-semantic-rules-v2-remediation2"

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


def _is_transaction_discount(words: str, amount: int | None) -> bool:
    """Require financial adjustment evidence, not policy prose containing credit."""

    if amount is None:
        return False
    return bool(
        re.search(
            r"\b(?:discount|coupon|savings|promo\s+credit|credit\s+applied|store\s+credit)\b",
            words,
        )
        or re.search(r"\b\d+(?:\.\d+)?%\s+off\b", words)
    )


def _is_policy_prose(words: str, amount: int | None) -> bool:
    """Recognize return/exchange policy language without inventing a credit event."""

    if amount is not None:
        return False
    policy_subject = re.search(r"\b(?:returns?|refunds?|exchanges?|store\s+credit|credit\s+policy)\b", words)
    policy_context = re.search(
        r"\b(?:within|policy|only|accepted|eligible|required|receipt|purchase\s+date|all\s+sales\s+final|no\s+returns?)\b",
        words,
    )
    return bool(policy_subject and policy_context)


def _has_tax_label(words: str) -> bool:
    """Recognize explicit and conservative OCR-near tax labels."""

    if re.search(r"\b(?:sales|state|county|local|city|nj)?\s*tax\b", words):
        return True
    if re.search(r"\bvat\b", words):
        return True
    tokens = words.split()
    # These bounded near-spellings cover common single-character OCR damage.
    # They deliberately do not attempt to infer arbitrary short labels.
    return any(re.fullmatch(r"(?:tx|t[a4][xk]|7ax|ta[kx])", token) for token in tokens)


def _is_tender_identity(words: str, *, has_product_context: bool) -> bool:
    strong_context = bool(re.search(
        r"\b(?:payment|paid|sale|contactless|ending|last\s+four|apple\s+pay|google\s+pay|card\s+ending)\b",
        words,
    ))
    brand = bool(re.search(
        r"\b(?:visa|mastercard|master\s+card|mc|amex|american\s+express|discover|paypal|debit|credit\s+card)\b",
        words,
    ))
    masked_or_last_four = bool(re.search(r"(?:\*{2,}\s*)?\b\d{4}\b", words))
    standalone_method = bool(re.fullmatch(
        r"(?:visa|mastercard|master\s+card|mc|amex|american\s+express|discover|paypal|cash|debit|credit\s+card|"
        r"apple\s+pay|google\s+pay|contactless)(?:\s+(?:sale|payment))?",
        words,
    ))
    return bool(
        standalone_method
        or (brand and (strong_context or masked_or_last_four) and not has_product_context)
        or re.fullmatch(r"(?:apple\s+pay|google\s+pay|contactless|card\s+ending\s+\d{4})", words)
    )


def _is_payment_support_metadata(words: str) -> bool:
    return bool(
        re.match(r"^(?:auth(?:orization)?\s+code|approval\s+code)\b", words)
        or re.match(r"^aid\b", words)
        or re.fullmatch(r"(?:no\s+cvm|cvm(?:\s+result)?(?:\s+\w+)*)", words)
    )


def _is_address_or_transaction_metadata(text: str, words: str) -> bool:
    if re.search(
        r"\b\d{1,6}\s+(?:[A-Za-z0-9.'-]+\s+){0,6}"
        r"(?:street|st|avenue|ave|road|rd|boulevard|blvd|lane|ln|drive|dr|"
        r"highway|hwy|broadway|parkway|pkwy|court|ct|terrace|ter|circle|cir|"
        r"way|place|pl|route|rte)\b",
        text,
        re.I,
    ):
        return True
    if re.search(r"\b[A-Za-z .'-]+,?\s+[A-Z]{2}\s+\d{5}(?:-\d{4})?\b", text):
        return True
    if re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", text):
        return True
    return bool(re.match(
        r"^(?:order|receipt|invoice|transaction|register|terminal|cashier|clerk|store|phone|tel|date|time)\b",
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

    if _is_policy_prose(words, amount):
        return make("INFORMATIONAL_FOOTER", 0.97, "RETURN_OR_CREDIT_POLICY_PROSE")

    component_signals = [
        _has_tax_label(words),
        _is_transaction_discount(words, amount),
        bool(re.search(r"\b(?:fee|surcharge|service\s+charge|handling)\b", words)),
        bool(re.search(r"\b(?:shipping|delivery|freight)\b", words)),
    ]
    if sum(component_signals) > 1:
        return make("UNKNOWN", 0.30, "CONFLICTING_COMPONENT_LABELS", conflicting=True)

    # Financial summaries and tender signals intentionally precede every
    # merchandise heuristic. The label comparison excludes only a trailing
    # currency amount, so product names containing words such as Cash, Visa,
    # Balance, or Card do not match these bounded phrases accidentally.
    if _is_payment_support_metadata(words):
        return make("STRUCTURAL", 0.98, "PAYMENT_SUPPORT_METADATA")
    if _is_tender_identity(words, has_product_context=_has_product_context(words)):
        return make("TENDER_PAYMENT_METHOD", 0.98, "TENDER_IDENTITY_OR_CONTEXT")
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
        r"(?:(?:grand\s+|order\s+|purchase\s+)?total|final\s+paid|(?:amount|amt)\s+due|balance\s+due|charged)",
        financial_label,
    ):
        return make("TOTAL", 0.99, "TOTAL_LABEL")
    if re.fullmatch(r"tx", financial_label) and has_trailing_amount:
        return make("TAX", 0.88, "TAX_ABBREVIATION", "AMOUNT_LABEL")
    if _has_tax_label(words):
        return make("TAX", 0.98, "TAX_LABEL", "PERCENTAGE_PRESENT" if "%" in words else "AMOUNT_LABEL")
    if _is_transaction_discount(words, amount):
        return make("DISCOUNT_CREDIT", 0.97, "DISCOUNT_OR_CREDIT_LABEL", "NEGATIVE_AMOUNT" if amount is not None and amount < 0 else "SIGNED_AMOUNT_UNKNOWN")
    if re.search(r"\b(?:fee|surcharge|service\s+charge|handling)\b", words):
        return make("FEE_SURCHARGE", 0.96, "FEE_OR_SURCHARGE_LABEL")
    if re.search(r"\b(?:shipping|delivery|freight)\b", words):
        return make("SHIPPING", 0.96, "SHIPPING_LABEL")

    if re.search(r"\b(?:thank\s+you|returns?\s+(?:accepted|within)|visit\s+us|www\.|http|customer\s+service|all\s+sales\s+final)\b", text, re.I):
        return make("INFORMATIONAL_FOOTER", 0.92, "FOOTER_PHRASE")
    if re.fullmatch(r"(?:customer|merchant)\s+copy", words):
        return make("INFORMATIONAL_FOOTER", 0.96, "COPY_FOOTER_LABEL")
    if _is_address_or_transaction_metadata(text, words):
        return make("STRUCTURAL", 0.96, "ADDRESS_OR_TRANSACTION_METADATA")
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
    if has_trailing_amount and "%" in text:
        return make(
            "UNKNOWN", 0.32,
            "PERCENT_AMOUNT_FINANCIAL_UNKNOWN",
            "AMBIGUOUS_FINANCIAL_LINE",
        )
    if amount is not None and amount >= 0:
        return make("MERCHANDISE", 0.90, "POSITIVE_LINE_AMOUNT", "NO_COMPONENT_LABEL")
    if amount is not None and amount < 0:
        return make("UNKNOWN", 0.45, "UNLABELED_NEGATIVE_AMOUNT")
    if source_line_index <= 6 and len(words.split()) <= 8 and amount is None:
        return make("STRUCTURAL", 0.86, "EARLY_HEADER_OR_MERCHANT_TEXT")
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


def active_extraction_job_ids(
    db: sqlite3.Connection,
    *,
    acquisition_id: int | None = None,
    document_id: int | None = None,
) -> tuple[int, ...]:
    """Return the one current extraction attempt for each attached document.

    Extraction attempts are append-only.  The current attempt is derived from
    the newest job for each document that is still attached.  A failed current
    attempt therefore does not revive an older successful attempt, and removed
    document history can never regain active authority.
    """

    clauses = [
        "d.storage_status='STORED'",
        "j.id=(SELECT MAX(newer.id) FROM receipt_extraction_jobs newer "
        "WHERE newer.document_id=j.document_id)",
        "j.disposition NOT IN ('REJECTED','SUPERSEDED')",
    ]
    params: list[object] = []
    if acquisition_id is not None:
        clauses.append("j.acquisition_id=?")
        params.append(int(acquisition_id))
    if document_id is not None:
        clauses.append("j.document_id=?")
        params.append(int(document_id))
    rows = db.execute(
        "SELECT j.id FROM receipt_extraction_jobs j "
        "JOIN acquisition_documents d ON d.id=j.document_id "
        f"WHERE {' AND '.join(clauses)} ORDER BY j.id",
        params,
    ).fetchall()
    return tuple(int(row["id"]) for row in rows)


def semantic_line_payload(row: Mapping, *, active: bool = True) -> dict:
    item = dict(row)
    item["evidence"] = json.loads(item.get("evidence") or "{}")
    item["operator_confirmation_required"] = bool(item["operator_confirmation_required"])
    item["active"] = bool(active)
    item["product_match_eligible"] = (
        active
        and
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
    active_jobs = active_extraction_job_ids(db, acquisition_id=acquisition_id)
    if job_id is not None:
        if int(job_id) not in active_jobs:
            return []
        active_jobs = (int(job_id),)
    if not active_jobs:
        return []
    placeholders = ",".join("?" for _ in active_jobs)
    clauses = [
        "NOT EXISTS (SELECT 1 FROM receipt_semantic_lines n WHERE n.supersedes_semantic_line_id=s.id)",
        f"s.job_id IN ({placeholders})",
        "EXISTS (SELECT 1 FROM receipt_extraction_jobs active_job "
        "WHERE active_job.id=s.job_id AND active_job.status='COMPLETED')",
    ]
    params: list[object] = list(active_jobs)
    if acquisition_id is not None:
        clauses.append("s.acquisition_id=?")
        params.append(int(acquisition_id))
    rows = db.execute(
        f"SELECT s.* FROM receipt_semantic_lines s WHERE {' AND '.join(clauses)} "
        "ORDER BY s.job_id,s.source_page,s.source_line_index,s.id",
        params,
    ).fetchall()
    return [semantic_line_payload(row) for row in rows]


def semantic_history_lines(db: sqlite3.Connection, acquisition_id: int) -> list[dict]:
    """Return immutable non-current assertions with traceable supersession facts."""

    current = current_semantic_lines(db, acquisition_id=acquisition_id)
    current_ids = {int(item["id"]) for item in current}
    active_jobs = set(active_extraction_job_ids(db, acquisition_id=acquisition_id))
    active_jobs_by_document = {
        int(row["document_id"]): dict(row)
        for row in db.execute(
            "SELECT id,document_id,job_uuid FROM receipt_extraction_jobs WHERE id IN ("
            + (",".join("?" for _ in active_jobs) if active_jobs else "NULL")
            + ")",
            tuple(sorted(active_jobs)),
        ).fetchall()
    }
    rows = db.execute(
        """SELECT s.*,j.job_uuid,j.status AS job_status,d.storage_status AS document_status
             FROM receipt_semantic_lines s
             JOIN receipt_extraction_jobs j ON j.id=s.job_id
             JOIN acquisition_documents d ON d.id=s.document_id
            WHERE s.acquisition_id=?
            ORDER BY s.recorded_at DESC,s.id DESC""",
        (int(acquisition_id),),
    ).fetchall()
    history: list[dict] = []
    for row in rows:
        if int(row["id"]) in current_ids:
            continue
        item = semantic_line_payload(row, active=False)
        successor = db.execute(
            "SELECT semantic_uuid FROM receipt_semantic_lines WHERE supersedes_semantic_line_id=?",
            (int(row["id"]),),
        ).fetchone()
        event = db.execute(
            """SELECT event_type,reason_code,notes,recorded_at
                 FROM receipt_semantic_events
                WHERE semantic_line_id=? AND successor_semantic_line_id IS NOT NULL
                ORDER BY recorded_at DESC,event_id DESC LIMIT 1""",
            (int(row["id"]),),
        ).fetchone()
        active_job = active_jobs_by_document.get(int(row["document_id"]))
        if row["document_status"] != "STORED":
            inactive_reason = "REMOVED_DOCUMENT"
        elif row["job_status"] != "COMPLETED":
            inactive_reason = "FAILED_EXTRACTION"
        elif int(row["job_id"]) not in active_jobs:
            inactive_reason = "SUPERSEDED_EXTRACTION"
        else:
            inactive_reason = "SUPERSEDED_DECISION"
        item.update({
            "inactive_reason": inactive_reason,
            "superseded_by_semantic_uuid": successor["semantic_uuid"] if successor else None,
            "superseded_by_job_uuid": (
                active_job["job_uuid"]
                if active_job and int(active_job["id"]) != int(row["job_id"])
                else None
            ),
            "operator_action": event["event_type"] if event else None,
            "operator_reason_code": event["reason_code"] if event else "",
            "operator_notes": event["notes"] if event else "",
            "superseded_at": event["recorded_at"] if event else None,
        })
        history.append(item)
    return history


def semantic_review_payload(db: sqlite3.Connection, acquisition_id: int) -> dict:
    lines = current_semantic_lines(db, acquisition_id=acquisition_id)
    history = semantic_history_lines(db, acquisition_id)
    counts = {semantic_class: 0 for semantic_class in SEMANTIC_CLASSES}
    for line in lines:
        counts[line["semantic_class"]] += 1
    return {
        "taxonomy_version": RULES_VERSION,
        "engine_version": ENGINE_VERSION,
        "lines": lines,
        "history": history,
        "total_stored_assertion_count": len(lines) + len(history),
        "active_assertion_count": len(lines),
        "historical_assertion_count": len(history),
        "counts": counts,
        "needs_confirmation_count": sum(1 for line in lines if line["operator_confirmation_required"]),
        "product_match_eligible_count": sum(1 for line in lines if line["product_match_eligible"]),
        "authority_rule": "Parser semantics are suggestions. Operator confirmation is separate and creates no inventory or accounting authority.",
    }


def semantic_allows_receipt_line(db: sqlite3.Connection, receipt_line_id: int) -> bool:
    """Preserve HF3 behavior for legacy jobs; gate newly classified jobs."""

    row = db.execute(
        """SELECT r.job_id,j.status FROM receipt_lines r
             JOIN receipt_extraction_jobs j ON j.id=r.job_id WHERE r.id=?""",
        (int(receipt_line_id),)
    ).fetchone()
    if not row:
        return False
    if row["status"] != "COMPLETED" or int(row["job_id"]) not in active_extraction_job_ids(db):
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
    job_status = db.execute(
        "SELECT status FROM receipt_extraction_jobs WHERE id=?", (int(current["job_id"]),)
    ).fetchone()
    if not job_status or job_status["status"] != "COMPLETED":
        raise ValueError("Receipt semantic line is historical; review the current interpretation")
    if int(current["job_id"]) not in active_extraction_job_ids(
        db, acquisition_id=int(current["acquisition_id"]), document_id=int(current["document_id"])
    ):
        raise ValueError("Receipt semantic line is historical; review the current interpretation")
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
