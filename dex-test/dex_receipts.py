"""DEX v2.2-test receipt intelligence and proposed accounting.

Extraction results are non-authoritative candidates. Raw OCR/text is never
stored or logged. Text-layer PDFs and JPG/PNG images are processed privately
and locally through the same provider-neutral extraction contract.
"""

from __future__ import annotations

import io
import json
import re
import sqlite3
import time
import uuid
from abc import ABC, abstractmethod
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from typing import Mapping

from pypdf import PdfReader

from dex_catalog import normalize_identifier
from dex_documents import DocumentStore, read_document
from dex_receipt_ocr import (
    ReceiptOcrFailed,
    ReceiptOcrUnavailable,
    extract_image_text,
    provider_health as image_ocr_health,
)
from dex_receipt_parser import PARSER_VERSION, parse_receipt_pages
from dex_receipt_semantics import (
    active_extraction_job_ids,
    current_semantic_lines,
    persist_initial_semantics,
    semantic_allows_receipt_line,
    semantic_review_payload,
)


EXTRACTION_VERSION = "receipt-local-zero-entry-v1"
ALLOCATION_VERSION = "receipt-landed-allocation-v1"
RECEIPT_CLASSIFICATIONS = (
    "INVENTORY", "SHIPPING_FEE", "BUSINESS_NONINVENTORY", "PERSONAL_NONBUSINESS",
    "DUPLICATE_EXTRACTION", "UNRESOLVED",
)
CRITICAL_FIELDS = {"final_usd_paid_cents", "purchase_subtotal_cents", "acquisition_tax_cents"}
FACT_FIELD_TYPES = {
    "merchant_name": "TEXT", "purchased_on": "DATE", "order_reference": "TEXT",
    "source_scope": "SCOPE", "merchant_country": "TEXT", "original_currency": "CURRENCY",
    "original_foreign_amount_minor": "INTEGER", "purchase_subtotal_cents": "CENTS",
    "acquisition_tax_cents": "CENTS", "inbound_shipping_cents": "CENTS",
    "acquisition_fees_cents": "CENTS", "import_duties_cents": "CENTS",
    "brokerage_cents": "CENTS", "acquisition_discount_cents": "CENTS",
    "final_usd_paid_cents": "CENTS", "payment_method": "TEXT",
}
AMOUNT_LABELS = {
    "subtotal": "purchase_subtotal_cents",
    "tax": "acquisition_tax_cents",
    "sales tax": "acquisition_tax_cents",
    "shipping": "inbound_shipping_cents",
    "shipping & handling": "inbound_shipping_cents",
    "handling": "acquisition_fees_cents",
    "fees": "acquisition_fees_cents",
    "fee": "acquisition_fees_cents",
    "duties": "import_duties_cents",
    "duty": "import_duties_cents",
    "import charges": "import_duties_cents",
    "brokerage": "brokerage_cents",
    "discount": "acquisition_discount_cents",
    "discounts": "acquisition_discount_cents",
    "credits": "acquisition_discount_cents",
    "total": "final_usd_paid_cents",
    "final paid": "final_usd_paid_cents",
    "amount paid": "final_usd_paid_cents",
    "charged": "final_usd_paid_cents",
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExtractionError(ValueError):
    code = "EXTRACTION_FAILED"


class UnsupportedExtractionFormat(ExtractionError):
    code = "FORMAT_PROVIDER_UNAVAILABLE"


class ReceiptExtractor(ABC):
    provider_name: str
    provider_version: str

    @abstractmethod
    def health(self) -> dict: ...

    @abstractmethod
    def extract(self, document: Mapping, data: bytes) -> dict: ...


def _money_cents(text: str) -> int:
    cleaned = text.strip().replace(",", "").replace("$", "")
    negative = cleaned.startswith("-") or (cleaned.startswith("(") and cleaned.endswith(")"))
    cleaned = cleaned.strip("-() ")
    if not re.fullmatch(r"\d+(?:\.\d{1,2})?", cleaned):
        raise ValueError("Invalid money")
    dollars, _, decimals = cleaned.partition(".")
    cents = int(dollars) * 100 + int((decimals + "00")[:2])
    return -cents if negative else cents


def _confidence_band(value: float) -> str:
    return "HIGH" if value >= 0.85 else "MEDIUM" if value >= 0.60 else "LOW"


def _candidate(field: str, value: object, confidence: float, page: int, location: str) -> dict:
    return {
        "field_name": field,
        "normalized_value": str(value),
        "value_type": FACT_FIELD_TYPES[field],
        "confidence": round(float(confidence), 4),
        "confidence_band": _confidence_band(confidence),
        "source_page": page,
        "source_location": location[:160],
    }


def _normalize_name(value: object) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).split())


class LocalPdfTextReceiptExtractor(ReceiptExtractor):
    """Compatibility name for the combined local PDF + image provider."""

    provider_name = "LOCAL_RECEIPT_INTELLIGENCE"
    provider_version = EXTRACTION_VERSION

    def health(self) -> dict:
        ocr = image_ocr_health()
        return {
            "provider": self.provider_name,
            "version": self.provider_version,
            "configured": True,
            "available": True,
            "private_local_processing": True,
            "external_transmission": False,
            "operational_formats": ["application/pdf", *ocr["operational_formats"]],
            "provider_ready_formats": [] if ocr["available"] else ["image/jpeg", "image/png"],
            "image_ocr": ocr,
        }

    def extract(self, document: Mapping, data: bytes) -> dict:
        mime = document.get("detected_mime_type")
        metrics: dict[str, object] = {}
        if mime == "application/pdf":
            started = time.perf_counter()
            try:
                reader = PdfReader(io.BytesIO(data))
                if reader.is_encrypted:
                    raise ExtractionError("Encrypted PDFs cannot be extracted")
                pages = [(index + 1, page.extract_text() or "") for index, page in enumerate(reader.pages)]
            except ExtractionError:
                raise
            except Exception as exc:
                raise ExtractionError("PDF text extraction failed") from exc
            metrics["pdf_text_extraction_ms"] = round((time.perf_counter() - started) * 1000, 2)
        elif mime in ("image/jpeg", "image/png"):
            try:
                image_result = extract_image_text(data)
            except ReceiptOcrUnavailable as exc:
                raise UnsupportedExtractionFormat(str(exc)) from exc
            except ReceiptOcrFailed as exc:
                failed = ExtractionError(str(exc))
                failed.code = exc.code
                raise failed from exc
            pages = image_result["pages"]
            metrics.update(image_result["metrics"])
        else:
            raise UnsupportedExtractionFormat("This receipt format is not supported by the installed local provider")
        parsed = self._parse_pages(pages)
        parsed["metrics"] = {**metrics, **parsed.get("metrics", {})}
        parsed["parser_version"] = PARSER_VERSION
        return parsed

    def _parse_pages(self, pages: list[tuple[int, str]]) -> dict:
        return parse_receipt_pages(pages)

    @staticmethod
    def _date(value: str) -> str | None:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
            try:
                return datetime.strptime(value, fmt).date().isoformat()
            except ValueError:
                continue
        return None

    @staticmethod
    def _parse_item(line: str, page: int, location: str) -> dict | None:
        parts = [part.strip() for part in line.split("|")[1:] if part.strip()]
        if not parts:
            return None
        description = parts[0]
        values: dict[str, object] = {
            "description": description[:300], "quantity": None, "unit_price_cents": None,
            "line_total_cents": None, "currency": "", "extracted_identifier": "",
            "manufacturer_product_code": "", "confidence": 0.92,
            "source_page": page, "source_location": location,
        }
        for part in parts[1:]:
            key, _, raw = part.partition(" ")
            key = key.upper().rstrip(":")
            raw = raw.strip().lstrip(":").strip()
            try:
                if key in ("QTY", "QUANTITY"):
                    values["quantity"] = int(raw)
                elif key == "UNIT":
                    values["unit_price_cents"] = _money_cents(raw)
                elif key == "TOTAL":
                    values["line_total_cents"] = _money_cents(raw)
                elif key in ("UPC", "EAN", "GTIN"):
                    values["extracted_identifier"] = re.sub(r"\D", "", raw)
                elif key in ("CODE", "SKU", "MPN"):
                    values["manufacturer_product_code"] = raw[:100]
                elif key == "CURRENCY":
                    values["currency"] = raw.upper()[:3]
            except (ValueError, TypeError):
                values["confidence"] = 0.58
        if values["line_total_cents"] is None and values["quantity"] and values["unit_price_cents"] is not None:
            values["line_total_cents"] = int(values["quantity"]) * int(values["unit_price_cents"])
        values["confidence_band"] = _confidence_band(float(values["confidence"]))
        return values


def get_receipt_extractor() -> ReceiptExtractor:
    return LocalPdfTextReceiptExtractor()


def extraction_provider_contract(extractor: ReceiptExtractor) -> dict:
    return {
        "phase": "INBOUND_2_PHASE_5_RECEIPT_INTELLIGENCE",
        "active": extractor.health(),
        "external_providers": [],
        "external_transmission_enabled": False,
        "credentials_required_or_stored": False,
        "raw_ocr_stored": False,
        "confidence_bands": {"HIGH": ">= 0.85", "MEDIUM": "0.60-0.8499", "LOW": "< 0.60"},
        "authority_rule": "Confidence guides presentation only; final operator acquisition confirmation is authoritative.",
    }


def _event(db: sqlite3.Connection, acquisition_id: int, request_id: str, event_type: str,
           job_id: int | None = None, candidate_id: int | None = None,
           receipt_line_id: int | None = None, reason_code: str = "", notes: str = "",
           payload: dict | None = None) -> None:
    now = utcnow()
    db.execute(
        """INSERT INTO receipt_extraction_events
           (event_id,request_id,acquisition_id,job_id,candidate_id,receipt_line_id,event_type,
            effective_at,recorded_at,reason_code,notes,payload)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (f"RCPT-EVT-{uuid.uuid4()}", request_id, acquisition_id, job_id, candidate_id, receipt_line_id,
         event_type, now, now, reason_code[:80], notes[:1000], json.dumps(payload or {}, separators=(",", ":"), sort_keys=True)),
    )


def _acquisition(db: sqlite3.Connection, acquisition_id: int) -> dict:
    row = db.execute("SELECT * FROM acquisitions WHERE id=?", (acquisition_id,)).fetchone()
    if row is None:
        raise ValueError("Acquisition not found")
    return dict(row)


def _require_revision(acquisition: Mapping, payload: Mapping) -> None:
    if payload.get("expected_revision") is None or int(payload["expected_revision"]) != int(acquisition["revision"]):
        raise ValueError("Acquisition changed in another session; refresh before applying receipt intelligence")
    if acquisition["state"] not in ("ACQUISITION_INCOMPLETE", "RECONCILIATION_REQUIRED"):
        raise ValueError("Confirmed acquisition facts cannot be changed by receipt extraction")


def _supersede_prior_job_suggestions(
    db: sqlite3.Connection, acquisition_id: int, document_id: int, current_job_id: int
) -> None:
    """Retire mutable suggestions from earlier successful interpretations.

    Source rows and events remain intact.  Only their existing lifecycle fields
    change so later confirmation cannot accidentally accept provenance from an
    inactive extraction generation.
    """

    now = utcnow()
    prior_candidate_ids = [
        int(row["id"])
        for row in db.execute(
            """SELECT c.id FROM receipt_candidate_facts c
                 JOIN receipt_extraction_jobs j ON j.id=c.job_id
                WHERE c.acquisition_id=? AND j.document_id=? AND j.id<>?
                  AND c.disposition='PENDING'""",
            (acquisition_id, document_id, current_job_id),
        ).fetchall()
    ]
    if not prior_candidate_ids:
        return
    placeholders = ",".join("?" for _ in prior_candidate_ids)
    db.execute(
        f"UPDATE receipt_candidate_facts SET disposition='SUPERSEDED',updated_at=? "
        f"WHERE id IN ({placeholders})",
        (now, *prior_candidate_ids),
    )
    db.execute(
        f"UPDATE acquisition_field_provenance SET status='SUPERSEDED',updated_at=? "
        f"WHERE candidate_id IN ({placeholders}) AND status='PROPOSED'",
        (now, *prior_candidate_ids),
    )


def _job_payload(db: sqlite3.Connection, job_id: int) -> dict:
    row = db.execute("SELECT * FROM receipt_extraction_jobs WHERE id=?", (job_id,)).fetchone()
    if row is None:
        raise ValueError("Extraction job not found")
    job = dict(row)
    job["candidates"] = [candidate_payload(item) for item in db.execute(
        "SELECT * FROM receipt_candidate_facts WHERE job_id=? ORDER BY field_name,id", (job_id,)
    ).fetchall()]
    job["receipt_lines"] = [receipt_line_payload(db, item) for item in db.execute(
        "SELECT * FROM receipt_lines WHERE job_id=? ORDER BY line_sequence,id", (job_id,)
    ).fetchall()]
    job["semantic_lines"] = current_semantic_lines(db, job_id=job_id)
    job["raw_text_available"] = False
    analysis_row = db.execute(
        """SELECT payload FROM receipt_extraction_events
            WHERE job_id=? AND event_type='RECEIPT_ANALYSIS_COMPLETED'
            ORDER BY recorded_at DESC,event_id DESC LIMIT 1""",
        (job_id,),
    ).fetchone()
    analysis = json.loads(analysis_row["payload"] or "{}") if analysis_row else {}
    job["receipt_math"] = analysis.get("receipt_math")
    job["performance"] = analysis.get("performance", {})
    job["parser_version"] = analysis.get("parser_version")
    job["capability_unavailable"] = job.get("error_code") in (
        "FORMAT_PROVIDER_UNAVAILABLE", "LOCAL_OCR_UNAVAILABLE",
    )
    job["retry_plausible"] = bool(
        job.get("status") in ("FAILED", "NO_FACTS")
        and not job["capability_unavailable"]
    )
    return job


def extraction_job_payload(db: sqlite3.Connection, job_uuid: str) -> dict:
    row = db.execute("SELECT id FROM receipt_extraction_jobs WHERE job_uuid=?", (job_uuid,)).fetchone()
    if row is None:
        raise ValueError("Extraction job not found")
    return _job_payload(db, int(row["id"]))


def candidate_payload(row: Mapping) -> dict:
    item = dict(row)
    value = item["normalized_value"]
    if item["value_type"] in ("CENTS", "INTEGER"):
        value = int(value)
    item["value"] = value
    item["authoritative"] = False
    return item


def receipt_line_payload(db: sqlite3.Connection, row: Mapping) -> dict:
    item = dict(row)
    matches = [dict(match) for match in db.execute(
        """SELECT m.*,l.product_name,l.set_code,l.game,l.catalog_product_id
             FROM receipt_line_matches m JOIN acquisition_lines l ON l.id=m.acquisition_line_id
            WHERE m.receipt_line_id=? ORDER BY m.confidence DESC,m.id""", (item["id"],)
    ).fetchall()]
    item["matches"] = matches
    item["best_match"] = matches[0] if matches else None
    return item


def queue_extraction(db: sqlite3.Connection, document_id: int, payload: Mapping,
                     store: DocumentStore, extractor: ReceiptExtractor) -> dict:
    request_id = str(payload.get("request_id") or "").strip()
    if not request_id:
        raise ValueError("request_id is required")
    existing = db.execute("SELECT id FROM receipt_extraction_jobs WHERE request_id=?", (request_id,)).fetchone()
    if existing:
        result = _job_payload(db, int(existing["id"]))
        result["idempotent_replay"] = True
        return result
    document_row = db.execute("SELECT * FROM acquisition_documents WHERE id=?", (document_id,)).fetchone()
    if document_row is None:
        raise ValueError("Source document not found")
    document = dict(document_row)
    acquisition_id = int(document["acquisition_id"])
    acquisition = _acquisition(db, acquisition_id)
    _require_revision(acquisition, payload)
    if document["storage_status"] != "STORED" or document["integrity_status"] == "FAILED":
        raise ValueError("Only an available, integrity-valid source document can be extracted")
    now = utcnow()
    cursor = db.execute(
        """INSERT INTO receipt_extraction_jobs
           (job_uuid,request_id,acquisition_id,document_id,retry_of_job_id,provider_name,provider_version,
            status,queued_at,started_at,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,'PROCESSING',?,?,?,?)""",
        (f"RCPT-JOB-{uuid.uuid4()}", request_id, acquisition_id, document_id, payload.get("retry_of_job_id"),
         extractor.provider_name, extractor.provider_version, now, now, now, now),
    )
    job_id = int(cursor.lastrowid)
    _event(db, acquisition_id, f"{request_id}:queued", "EXTRACTION_QUEUED", job_id=job_id,
           payload={"document_id": document_id, "provider": extractor.provider_name, "version": extractor.provider_version})
    extraction_started = time.perf_counter()
    try:
        verified_document, data = read_document(db, document_id, store)
        extracted = extractor.extract(verified_document, data)
        _persist_extraction(db, job_id, acquisition_id, document_id, extracted)
        status = "COMPLETED" if extracted["candidates"] or extracted["lines"] else "NO_FACTS"
        db.execute("UPDATE receipt_extraction_jobs SET status=?,completed_at=?,updated_at=? WHERE id=?", (status, utcnow(), utcnow(), job_id))
        if status == "COMPLETED":
            _supersede_prior_job_suggestions(db, acquisition_id, document_id, job_id)
            _supersede_allocation_proposals(db, acquisition_id)
        _event(db, acquisition_id, f"{request_id}:completed", "EXTRACTION_COMPLETED", job_id=job_id,
               payload={"candidate_count": len(extracted["candidates"]), "receipt_line_count": len(extracted["lines"]), "status": status})
        _event(
            db, acquisition_id, f"{request_id}:math", "RECEIPT_MATH_ANALYZED", job_id=job_id,
            payload={
                "receipt_math": extracted.get("receipt_math", {"status": "INCOMPLETE"}),
                "parser_version": extracted.get("parser_version", PARSER_VERSION),
                "authoritative": False,
            },
        )
        matching_started = time.perf_counter()
        _prepare_catalog_lines(db, acquisition_id, job_id, f"{request_id}:catalog-lines")
        _match_receipt_lines(db, acquisition_id, job_id, f"{request_id}:matching")
        matching_ms = (time.perf_counter() - matching_started) * 1000
        if payload.get("auto_apply", True):
            current = _acquisition(db, acquisition_id)
            apply_proposed_facts(db, acquisition_id, {
                "request_id": f"{request_id}:auto-apply", "expected_revision": current["revision"], "high_confidence_only": True,
            })
            current = _acquisition(db, acquisition_id)
            try:
                generate_allocation_proposal(db, acquisition_id, {
                    "request_id": f"{request_id}:allocation", "expected_revision": current["revision"], "auto_apply": True,
                })
            except ValueError:
                pass
        performance = {
            **dict(extracted.get("metrics", {})),
            "matching_reconciliation_ms": round(matching_ms, 2),
            "total_receipt_to_review_ms": round((time.perf_counter() - extraction_started) * 1000, 2),
        }
        _event(
            db, acquisition_id, f"{request_id}:analysis", "RECEIPT_ANALYSIS_COMPLETED",
            job_id=job_id,
            payload={
                "receipt_math": extracted.get("receipt_math", {"status": "INCOMPLETE"}),
                "performance": performance,
                "parser_version": extracted.get("parser_version", PARSER_VERSION),
                "raw_ocr_persisted": False,
                "external_transmission": False,
            },
        )
    except Exception as exc:
        failed = utcnow()
        code = getattr(exc, "code", "EXTRACTION_FAILED")
        message = str(exc) if isinstance(exc, ExtractionError) else "Private local extraction failed"
        db.execute("UPDATE receipt_extraction_jobs SET status='FAILED',failed_at=?,error_code=?,error_message=?,updated_at=? WHERE id=?",
                   (failed, code, message[:500], failed, job_id))
        _event(db, acquisition_id, f"{request_id}:failed", "EXTRACTION_FAILED", job_id=job_id,
               reason_code=code, notes=message, payload={"document_id": document_id})
    return _job_payload(db, job_id)


def _persist_extraction(db: sqlite3.Connection, job_id: int, acquisition_id: int, document_id: int, extracted: Mapping) -> None:
    now = utcnow()
    for fact in extracted.get("candidates", []):
        if fact.get("field_name") not in FACT_FIELD_TYPES or fact.get("value_type") != FACT_FIELD_TYPES[fact["field_name"]]:
            raise ExtractionError("Extractor returned an unsupported normalized candidate")
        db.execute(
            """INSERT INTO receipt_candidate_facts
               (candidate_uuid,job_id,acquisition_id,field_name,normalized_value,value_type,confidence,
                confidence_band,source_page,source_location,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (f"RCPT-CAND-{uuid.uuid4()}", job_id, acquisition_id, fact["field_name"], fact["normalized_value"],
             fact["value_type"], fact["confidence"], fact["confidence_band"], fact.get("source_page"),
             fact.get("source_location", "")[:160], now, now),
        )
    receipt_line_ids_by_source_index: dict[int, int] = {}
    persisted_lines = extracted.get("semantic_candidate_lines", extracted.get("lines", []))
    for sequence, line in enumerate(persisted_lines, 1):
        cursor = db.execute(
            """INSERT INTO receipt_lines
               (line_uuid,job_id,acquisition_id,document_id,line_sequence,description,quantity,unit_price_cents,
                line_total_cents,currency,extracted_identifier,manufacturer_product_code,confidence,confidence_band,
                source_page,source_location,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (f"RCPT-LINE-{uuid.uuid4()}", job_id, acquisition_id, document_id, sequence, line["description"],
             line.get("quantity"), line.get("unit_price_cents"), line.get("line_total_cents"), line.get("currency", ""),
             line.get("extracted_identifier", ""), line.get("manufacturer_product_code", ""), line["confidence"],
             line["confidence_band"], line.get("source_page"), line.get("source_location", "")[:160], now, now),
        )
        source_index = line.get("source_line_index")
        if source_index is not None:
            receipt_line_ids_by_source_index[int(source_index)] = int(cursor.lastrowid)
    persist_initial_semantics(
        db,
        job_id=job_id,
        acquisition_id=acquisition_id,
        document_id=document_id,
        semantic_lines=list(extracted.get("semantic_lines", [])),
        receipt_line_ids_by_source_index=receipt_line_ids_by_source_index,
    )


def _catalog_match_for_receipt(db: sqlite3.Connection, receipt: Mapping) -> tuple[sqlite3.Row, str, float] | None:
    extracted_id = str(receipt.get("extracted_identifier") or "")
    if extracted_id:
        try:
            normalized = normalize_identifier(extracted_id)["normalized_identifier"]
        except ValueError:
            normalized = ""
        if normalized:
            row = db.execute(
                """SELECT p.* FROM product_identifiers i
                    JOIN catalog_products p ON p.id=i.catalog_product_id
                    WHERE i.normalized_identifier=? AND i.mapping_status='ACTIVE' AND p.active=1""",
                (normalized,),
            ).fetchone()
            if row:
                return row, "EXACT_IDENTIFIER", 1.0
    description = _normalize_name(receipt.get("description"))
    if not description:
        return None
    exact = [
        row for row in db.execute("SELECT * FROM catalog_products WHERE active=1 ORDER BY id").fetchall()
        if _normalize_name(row["display_name"]) == description
    ]
    if len(exact) == 1:
        return exact[0], "EXACT_NAME_SET", 0.96
    return None


def _prepare_catalog_lines(db: sqlite3.Connection, acquisition_id: int, job_id: int,
                           request_prefix: str) -> None:
    """Prepare draft product lines only from unique, deterministic catalog matches."""

    receipts = db.execute("SELECT * FROM receipt_lines WHERE job_id=? ORDER BY id", (job_id,)).fetchall()
    now = utcnow()
    changed = False
    for receipt_row in receipts:
        receipt = dict(receipt_row)
        if not semantic_allows_receipt_line(db, int(receipt["id"])):
            continue
        match = _catalog_match_for_receipt(db, receipt)
        if not match:
            continue
        product, method, confidence = match
        line = db.execute(
            """SELECT * FROM acquisition_lines
                WHERE acquisition_id=? AND catalog_product_id=? AND canceled_at IS NULL
                ORDER BY id LIMIT 1""",
            (acquisition_id, product["id"]),
        ).fetchone()
        if line is None:
            sequence = int(db.execute(
                "SELECT COALESCE(MAX(line_sequence),0)+1 FROM acquisition_lines WHERE acquisition_id=?",
                (acquisition_id,),
            ).fetchone()[0])
            cursor = db.execute(
                """INSERT INTO acquisition_lines
                   (line_uuid,acquisition_id,line_sequence,product_class,game,product_name,set_code,
                    pack_type,quantity,quantity_certainty,intended_action,allocation_status,
                    allocation_method,catalog_product_id,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,'KNOWN','DECIDE_LATER','UNALLOCATED','',?,?,?)""",
                (
                    str(uuid.uuid4()), acquisition_id, sequence, product["product_class"],
                    product["game"], product["display_name"], product["set_code"],
                    product["product_subtype"], receipt.get("quantity") or 1,
                    product["id"], now, now,
                ),
            )
            line = db.execute("SELECT * FROM acquisition_lines WHERE id=?", (cursor.lastrowid,)).fetchone()
            changed = True
            _event(
                db, acquisition_id, f"{request_prefix}:{receipt['id']}",
                "RECEIPT_CATALOG_LINE_PREPARED", job_id=job_id,
                receipt_line_id=int(receipt["id"]),
                payload={
                    "acquisition_line_id": int(line["id"]),
                    "catalog_product_id": int(product["id"]),
                    "match_method": method, "confidence": confidence,
                    "authoritative": False,
                },
            )
        existing_match = db.execute(
            "SELECT id FROM receipt_line_matches WHERE receipt_line_id=? AND acquisition_line_id=?",
            (receipt["id"], line["id"]),
        ).fetchone()
        if not existing_match:
            db.execute(
                """INSERT INTO receipt_line_matches
                   (match_uuid,receipt_line_id,acquisition_line_id,match_method,confidence,status,
                    authoritative_identity,rationale,created_at,updated_at)
                   VALUES (?,?,?,?,?,'ACCEPTED',1,?,?,?)""",
                (
                    f"RCPT-MATCH-{uuid.uuid4()}", receipt["id"], line["id"], method,
                    confidence, "Unique exact catalog identity; acquisition authority remains pending confirmation",
                    now, now,
                ),
            )
        # Pack-format catalog products are strong inventory evidence.  Broader
        # sealed products remain a genuine business-purpose question.
        if product["product_class"] == "PACK_PRODUCT":
            db.execute(
                """UPDATE receipt_lines SET classification='INVENTORY',
                    classification_source='DETERMINISTIC_CATALOG_RULE',updated_at=? WHERE id=?""",
                (now, receipt["id"]),
            )
    if changed:
        db.execute(
            "UPDATE acquisitions SET revision=revision+1,updated_at=? WHERE id=?",
            (now, acquisition_id),
        )


def _match_receipt_lines(db: sqlite3.Connection, acquisition_id: int, job_id: int, request_prefix: str) -> None:
    lines = db.execute("SELECT * FROM acquisition_lines WHERE acquisition_id=? AND canceled_at IS NULL ORDER BY id", (acquisition_id,)).fetchall()
    receipt_lines = db.execute("SELECT * FROM receipt_lines WHERE job_id=? ORDER BY id", (job_id,)).fetchall()
    now = utcnow()
    for receipt in receipt_lines:
        if not semantic_allows_receipt_line(db, int(receipt["id"])):
            continue
        if db.execute(
            "SELECT 1 FROM receipt_line_matches WHERE receipt_line_id=? AND status<>'REJECTED' LIMIT 1",
            (receipt["id"],),
        ).fetchone():
            continue
        candidates: list[tuple[sqlite3.Row, str, float, int, str]] = []
        extracted_id = str(receipt["extracted_identifier"] or "")
        for line in lines:
            product_name = str(line["product_name"] or "")
            if line["catalog_product_id"]:
                product = db.execute("SELECT * FROM catalog_products WHERE id=?", (line["catalog_product_id"],)).fetchone()
                if product:
                    product_name = str(product["display_name"] or product_name)
                    if extracted_id:
                        try:
                            normalized = normalize_identifier(extracted_id)["normalized_identifier"]
                        except ValueError:
                            normalized = ""
                        mapped = db.execute("SELECT 1 FROM product_identifiers WHERE catalog_product_id=? AND normalized_identifier=? AND mapping_status='ACTIVE'", (product["id"], normalized)).fetchone()
                        if mapped:
                            candidates.append((line, "EXACT_IDENTIFIER", 1.0, 1, "Exact catalog identifier"))
                    code = str(receipt["manufacturer_product_code"] or "").strip().lower()
                    if code and code == str(product["manufacturer_product_code"] or "").strip().lower():
                        candidates.append((line, "EXACT_MANUFACTURER_CODE", 0.99, 1, "Exact manufacturer product code"))
            left = _normalize_name(receipt["description"])
            right = _normalize_name(f"{product_name} {line['set_code'] or ''}")
            if left and right:
                if left == right or left == _normalize_name(product_name):
                    candidates.append((line, "EXACT_NAME_SET", 0.92, 0, "Exact normalized product name/set"))
                else:
                    score = SequenceMatcher(None, left, right).ratio()
                    if score >= 0.72:
                        candidates.append((line, "FUZZY_TEXT", round(score, 4), 0, "Text similarity suggestion only"))
        if not candidates:
            continue
        candidates.sort(key=lambda item: (-item[2], int(item[0]["id"])))
        best = candidates[0]
        if len(candidates) > 1 and candidates[1][2] == best[2] and int(candidates[1][0]["id"]) != int(best[0]["id"]):
            continue
        status = "ACCEPTED" if best[1] in ("EXACT_IDENTIFIER", "EXACT_MANUFACTURER_CODE") else "PROPOSED"
        cursor = db.execute(
            """INSERT INTO receipt_line_matches
               (match_uuid,receipt_line_id,acquisition_line_id,match_method,confidence,status,authoritative_identity,rationale,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (f"RCPT-MATCH-{uuid.uuid4()}", receipt["id"], best[0]["id"], best[1], best[2], status, best[3], best[4], now, now),
        )
        if best[1] != "FUZZY_TEXT":
            db.execute("UPDATE receipt_lines SET classification='INVENTORY',classification_source='DETERMINISTIC_MATCH',updated_at=? WHERE id=?", (now, receipt["id"]))
        _event(db, acquisition_id, f"{request_prefix}:{receipt['id']}", "RECEIPT_LINE_MATCH_PROPOSED",
               job_id=job_id, receipt_line_id=int(receipt["id"]),
               payload={"match_id": int(cursor.lastrowid), "acquisition_line_id": int(best[0]["id"]), "method": best[1], "confidence": best[2], "status": status})


def reconcile_semantic_merchandise_line(
    db: sqlite3.Connection, semantic_result: Mapping, request_prefix: str
) -> None:
    """Reconcile matching eligibility after an explicit semantic decision."""

    receipt_line_id = semantic_result.get("receipt_line_id")
    if not receipt_line_id:
        return
    acquisition_id = int(semantic_result["acquisition_id"])
    job_id = int(semantic_result["job_id"])
    if not semantic_allows_receipt_line(db, int(receipt_line_id)):
        active_proposal = db.execute(
            "SELECT 1 FROM receipt_allocation_proposals WHERE acquisition_id=? "
            "AND status IN ('PROPOSED','APPLIED') LIMIT 1",
            (acquisition_id,),
        ).fetchone()
        if active_proposal:
            _supersede_allocation_proposals(db, acquisition_id)
            db.execute(
                "UPDATE acquisitions SET revision=revision+1,updated_at=? WHERE id=?",
                (utcnow(), acquisition_id),
            )
        return
    _prepare_catalog_lines(db, acquisition_id, job_id, f"{request_prefix}:catalog-lines")
    _match_receipt_lines(db, acquisition_id, job_id, f"{request_prefix}:matching")


def _candidate_groups(db: sqlite3.Connection, acquisition_id: int) -> dict[str, list[dict]]:
    active_jobs = active_extraction_job_ids(db, acquisition_id=acquisition_id)
    if not active_jobs:
        return {}
    placeholders = ",".join("?" for _ in active_jobs)
    rows = db.execute(
        """SELECT c.* FROM receipt_candidate_facts c JOIN receipt_extraction_jobs j ON j.id=c.job_id
            JOIN acquisition_documents d ON d.id=j.document_id
            WHERE c.acquisition_id=? AND j.id IN (""" + placeholders + """)
              AND j.status='COMPLETED' AND c.disposition<>'REJECTED' AND j.disposition<>'REJECTED'
              AND d.storage_status='STORED'
            ORDER BY c.created_at,c.id""", (acquisition_id, *active_jobs)
    ).fetchall()
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["field_name"], []).append(candidate_payload(row))
    return groups


def _field_empty(field: str, value: object) -> bool:
    return value is None if field.endswith("_cents") or field == "original_foreign_amount_minor" else not str(value or "").strip()


def _coerce_candidate(candidate: Mapping) -> object:
    value = candidate["value"]
    return int(value) if candidate["value_type"] in ("CENTS", "INTEGER") else str(value)


def apply_proposed_facts(db: sqlite3.Connection, acquisition_id: int, payload: Mapping) -> dict:
    request_id = str(payload.get("request_id") or "").strip()
    if not request_id:
        raise ValueError("request_id is required")
    prior = db.execute("SELECT 1 FROM receipt_extraction_events WHERE request_id=?", (request_id,)).fetchone()
    if prior:
        return receipt_intelligence_payload(db, acquisition_id) | {"idempotent_replay": True}
    acquisition = _acquisition(db, acquisition_id)
    _require_revision(acquisition, payload)
    groups = _candidate_groups(db, acquisition_id)
    selected = {int(value) for value in payload.get("candidate_ids", [])}
    updates: dict[str, object] = {}
    applied: list[dict] = []
    conflicts: list[str] = []
    now = utcnow()
    for field, candidates in groups.items():
        eligible = [item for item in candidates if not selected or int(item["id"]) in selected]
        if payload.get("high_confidence_only", False):
            eligible = [item for item in eligible if item["confidence_band"] == "HIGH"]
        if not eligible:
            continue
        distinct = {str(item["normalized_value"]) for item in eligible}
        if len(distinct) > 1:
            conflicts.append(field)
            continue
        candidate = max(eligible, key=lambda item: (float(item["confidence"]), int(item["id"])))
        value = _coerce_candidate(candidate)
        # USD is DEX's accounting currency. A receipt's inferred USD marker is not
        # useful as an "original foreign currency" fact for a domestic purchase.
        if field == "original_currency" and str(value).upper() == "USD" and acquisition.get("source_scope") != "INTERNATIONAL":
            continue
        current = acquisition.get(field)
        if not _field_empty(field, current) and str(current) != str(value):
            replaceable = None
            if field == "merchant_name":
                replaceable = db.execute(
                    """SELECT p.id AS provenance_id,c.id AS candidate_id
                         FROM acquisition_field_provenance p
                         JOIN receipt_candidate_facts c ON c.id=p.candidate_id
                        WHERE p.acquisition_id=? AND p.field_name='merchant_name'
                          AND p.status IN ('PROPOSED','SUPERSEDED') AND p.proposed_value=?
                        ORDER BY p.id DESC LIMIT 1""",
                    (acquisition_id, str(current)),
                ).fetchone()
            if replaceable and candidate["confidence_band"] == "HIGH":
                updates[field] = value
                db.execute(
                    "UPDATE acquisition_field_provenance SET status='SUPERSEDED',updated_at=? WHERE id=?",
                    (now, int(replaceable["provenance_id"])),
                )
                db.execute(
                    "UPDATE receipt_candidate_facts SET disposition='SUPERSEDED',updated_at=? WHERE id=?",
                    (now, int(replaceable["candidate_id"])),
                )
            else:
                conflicts.append(field)
                continue
        if _field_empty(field, current):
            updates[field] = value
        db.execute(
            """INSERT OR IGNORE INTO acquisition_field_provenance
               (acquisition_id,field_name,candidate_id,proposed_value,status,created_at,updated_at)
               VALUES (?,?,?,?, 'PROPOSED',?,?)""",
            (acquisition_id, field, candidate["id"], str(value), now, now),
        )
        applied.append({"field_name": field, "candidate_id": int(candidate["id"]), "value": value})
    if updates:
        db.execute(
            f"UPDATE acquisitions SET {','.join(f'{field}=?' for field in updates)},revision=revision+1,updated_at=? WHERE id=?",
            (*updates.values(), now, acquisition_id),
        )
    _event(db, acquisition_id, request_id, "PROPOSED_FACTS_APPLIED",
           payload={"applied": applied, "conflicting_fields": conflicts, "authoritative": False})
    return receipt_intelligence_payload(db, acquisition_id) | {"applied": applied, "conflicting_fields": conflicts}


def record_manual_overrides(db: sqlite3.Connection, acquisition_id: int, updates: Mapping, request_id: str) -> None:
    rows = db.execute(
        """SELECT p.*,c.normalized_value FROM acquisition_field_provenance p
            JOIN receipt_candidate_facts c ON c.id=p.candidate_id
            WHERE p.acquisition_id=? AND p.status='PROPOSED'""", (acquisition_id,)
    ).fetchall()
    overridden = []
    for row in rows:
        field = row["field_name"]
        if field not in updates or str(updates[field]) == str(row["proposed_value"]):
            continue
        db.execute("UPDATE acquisition_field_provenance SET status='OPERATOR_REPLACED',operator_value=?,updated_at=? WHERE id=?",
                   ("" if updates[field] is None else str(updates[field]), utcnow(), row["id"]))
        overridden.append({"field_name": field, "candidate_id": int(row["candidate_id"])})
    if overridden:
        if any(item["field_name"] in RECEIPT_FINANCIAL_FIELDS for item in overridden):
            _supersede_allocation_proposals(db, acquisition_id)
        _event(db, acquisition_id, f"{request_id}:receipt-overrides", "PROPOSED_FACTS_OVERRIDDEN",
               payload={"fields": overridden})


RECEIPT_FINANCIAL_FIELDS = {
    "purchase_subtotal_cents", "acquisition_tax_cents", "inbound_shipping_cents",
    "acquisition_fees_cents", "import_duties_cents", "brokerage_cents",
    "acquisition_discount_cents", "final_usd_paid_cents",
}


def _supersede_allocation_proposals(db: sqlite3.Connection, acquisition_id: int) -> None:
    """Invalidate receipt allocation suggestions when their source facts change."""
    now = utcnow()
    db.execute(
        "UPDATE receipt_allocation_proposals SET status='SUPERSEDED',updated_at=? "
        "WHERE acquisition_id=? AND status IN ('PROPOSED','APPLIED')",
        (now, acquisition_id),
    )
    db.execute(
        "UPDATE acquisition_lines SET "
        "assigned_landed_cost_cents=CASE WHEN allocation_status='SUGGESTED' THEN NULL ELSE assigned_landed_cost_cents END,"
        "allocation_method=CASE WHEN allocation_status='SUGGESTED' THEN '' ELSE allocation_method END,"
        "allocation_status=CASE WHEN allocation_status='SUGGESTED' THEN 'UNALLOCATED' ELSE allocation_status END,"
        "updated_at=? WHERE acquisition_id=?",
        (now, acquisition_id),
    )


def accept_confirmed_provenance(db: sqlite3.Connection, acquisition_id: int, request_id: str) -> None:
    now = utcnow()
    candidate_ids = [row[0] for row in db.execute(
        "SELECT candidate_id FROM acquisition_field_provenance WHERE acquisition_id=? AND status='PROPOSED'", (acquisition_id,)
    ).fetchall()]
    db.execute("UPDATE acquisition_field_provenance SET status='ACCEPTED',updated_at=? WHERE acquisition_id=? AND status='PROPOSED'", (now, acquisition_id))
    if candidate_ids:
        placeholders = ",".join("?" for _ in candidate_ids)
        db.execute(f"UPDATE receipt_candidate_facts SET disposition='ACCEPTED',accepted_value=normalized_value,updated_at=? WHERE id IN ({placeholders})", (now, *candidate_ids))
        _event(db, acquisition_id, f"{request_id}:receipt-provenance", "PROPOSED_FACTS_ACCEPTED",
               payload={"candidate_ids": candidate_ids})


def classify_receipt_line(db: sqlite3.Connection, receipt_line_id: int, payload: Mapping) -> dict:
    request_id = str(payload.get("request_id") or "").strip()
    classification = str(payload.get("classification") or "").upper()
    if not request_id or classification not in RECEIPT_CLASSIFICATIONS:
        raise ValueError("request_id and a supported classification are required")
    line = db.execute("SELECT * FROM receipt_lines WHERE id=?", (receipt_line_id,)).fetchone()
    if line is None:
        raise ValueError("Receipt line not found")
    if int(line["job_id"]) not in active_extraction_job_ids(
        db, acquisition_id=int(line["acquisition_id"]), document_id=int(line["document_id"])
    ):
        raise ValueError("Receipt line is historical; review the current extraction")
    acquisition = _acquisition(db, int(line["acquisition_id"]))
    prior = db.execute("SELECT 1 FROM receipt_extraction_events WHERE request_id=?", (request_id,)).fetchone()
    if prior:
        return receipt_intelligence_payload(db, int(line["acquisition_id"])) | {"idempotent_replay": True}
    _require_revision(acquisition, payload)
    now = utcnow()
    _supersede_allocation_proposals(db, int(line["acquisition_id"]))
    db.execute("UPDATE receipt_lines SET classification=?,classification_source='OPERATOR',updated_at=? WHERE id=?", (classification, now, receipt_line_id))
    prepared_match = db.execute(
        """SELECT m.acquisition_line_id FROM receipt_line_matches m
            WHERE m.receipt_line_id=? AND EXISTS (
                SELECT 1 FROM receipt_extraction_events e
                WHERE e.receipt_line_id=? AND e.event_type='RECEIPT_CATALOG_LINE_PREPARED'
            ) ORDER BY m.confidence DESC,m.id LIMIT 1""",
        (receipt_line_id, receipt_line_id),
    ).fetchone()
    if prepared_match:
        db.execute(
            "UPDATE acquisition_lines SET canceled_at=?,updated_at=? WHERE id=?",
            (None if classification == "INVENTORY" else now, now, prepared_match["acquisition_line_id"]),
        )
    db.execute("UPDATE acquisitions SET revision=revision+1,updated_at=? WHERE id=?", (now, line["acquisition_id"]))
    _event(db, int(line["acquisition_id"]), request_id, "RECEIPT_LINE_CLASSIFIED", job_id=int(line["job_id"]),
           receipt_line_id=receipt_line_id, reason_code=classification, notes=str(payload.get("notes") or ""),
           payload={"from": line["classification"], "to": classification})
    try:
        current = _acquisition(db, int(line["acquisition_id"]))
        generate_allocation_proposal(
            db,
            int(line["acquisition_id"]),
            {
                "request_id": f"{request_id}:zero-entry-allocation",
                "expected_revision": current["revision"],
                "auto_apply": True,
            },
        )
    except ValueError:
        # Classification is still a valid audited decision when other receipt
        # facts remain unresolved.  The payload exposes the remaining question.
        pass
    return receipt_intelligence_payload(db, int(line["acquisition_id"]))


def candidate_disposition(db: sqlite3.Connection, candidate_id: int, payload: Mapping) -> dict:
    request_id = str(payload.get("request_id") or "").strip()
    disposition = str(payload.get("disposition") or "").upper()
    if not request_id or disposition not in ("ACCEPTED", "REJECTED"):
        raise ValueError("request_id and ACCEPTED or REJECTED disposition are required")
    candidate = db.execute("SELECT * FROM receipt_candidate_facts WHERE id=?", (candidate_id,)).fetchone()
    if candidate is None:
        raise ValueError("Candidate not found")
    job = db.execute(
        "SELECT document_id FROM receipt_extraction_jobs WHERE id=?", (int(candidate["job_id"]),)
    ).fetchone()
    if not job or int(candidate["job_id"]) not in active_extraction_job_ids(
        db, acquisition_id=int(candidate["acquisition_id"]), document_id=int(job["document_id"])
    ):
        raise ValueError("Receipt candidate is historical; review the current extraction")
    acquisition = _acquisition(db, int(candidate["acquisition_id"]))
    prior = db.execute("SELECT 1 FROM receipt_extraction_events WHERE request_id=?", (request_id,)).fetchone()
    if prior:
        return receipt_intelligence_payload(db, int(candidate["acquisition_id"])) | {"idempotent_replay": True}
    _require_revision(acquisition, payload)
    now = utcnow()
    if candidate["field_name"] in RECEIPT_FINANCIAL_FIELDS:
        _supersede_allocation_proposals(db, int(candidate["acquisition_id"]))
    provenance = db.execute(
        "SELECT * FROM acquisition_field_provenance WHERE candidate_id=? AND status='PROPOSED' ORDER BY id DESC LIMIT 1",
        (candidate_id,),
    ).fetchone()
    if disposition == "REJECTED" and provenance:
        field = str(candidate["field_name"])
        current = acquisition.get(field)
        if str(current) == str(provenance["proposed_value"]):
            cleared = None if field.endswith("_cents") or field == "original_foreign_amount_minor" else ""
            db.execute(f"UPDATE acquisitions SET {field}=?,updated_at=? WHERE id=?", (cleared, now, candidate["acquisition_id"]))
    db.execute("UPDATE receipt_candidate_facts SET disposition=?,disposition_reason=?,updated_at=? WHERE id=?",
               (disposition, str(payload.get("reason") or "")[:500], now, candidate_id))
    db.execute(
        "UPDATE acquisition_field_provenance SET status=?,updated_at=? WHERE candidate_id=? AND status='PROPOSED'",
        (disposition, now, candidate_id),
    )
    db.execute("UPDATE acquisitions SET revision=revision+1,updated_at=? WHERE id=?", (now, candidate["acquisition_id"]))
    _event(db, int(candidate["acquisition_id"]), request_id, f"CANDIDATE_{disposition}", job_id=int(candidate["job_id"]),
           candidate_id=candidate_id, notes=str(payload.get("reason") or ""), payload={"field_name": candidate["field_name"]})
    return receipt_intelligence_payload(db, int(candidate["acquisition_id"]))


def match_disposition(db: sqlite3.Connection, match_id: int, payload: Mapping) -> dict:
    request_id = str(payload.get("request_id") or "").strip()
    disposition = str(payload.get("disposition") or "").upper()
    if not request_id or disposition not in ("ACCEPTED", "REJECTED"):
        raise ValueError("request_id and ACCEPTED or REJECTED disposition are required")
    match = db.execute(
        """SELECT m.*,r.acquisition_id,r.job_id,r.document_id FROM receipt_line_matches m
             JOIN receipt_lines r ON r.id=m.receipt_line_id WHERE m.id=?""", (match_id,)
    ).fetchone()
    if match is None:
        raise ValueError("Receipt-line match not found")
    acquisition_id = int(match["acquisition_id"])
    if int(match["job_id"]) not in active_extraction_job_ids(
        db, acquisition_id=acquisition_id, document_id=int(match["document_id"])
    ):
        raise ValueError("Receipt-line match is historical; review the current extraction")
    prior = db.execute("SELECT 1 FROM receipt_extraction_events WHERE request_id=?", (request_id,)).fetchone()
    if prior:
        return receipt_intelligence_payload(db, acquisition_id) | {"idempotent_replay": True}
    acquisition = _acquisition(db, acquisition_id)
    _require_revision(acquisition, payload)
    now = utcnow()
    _supersede_allocation_proposals(db, acquisition_id)
    db.execute("UPDATE receipt_line_matches SET status=?,updated_at=? WHERE id=?", (disposition, now, match_id))
    if disposition == "ACCEPTED":
        db.execute("UPDATE receipt_lines SET classification='INVENTORY',classification_source='OPERATOR_MATCH',updated_at=? WHERE id=?",
                   (now, match["receipt_line_id"]))
    db.execute("UPDATE acquisitions SET revision=revision+1,updated_at=? WHERE id=?", (now, acquisition_id))
    _event(db, acquisition_id, request_id, f"RECEIPT_LINE_MATCH_{disposition}", job_id=int(match["job_id"]),
           receipt_line_id=int(match["receipt_line_id"]), notes=str(payload.get("notes") or ""),
           payload={"match_id": match_id, "acquisition_line_id": int(match["acquisition_line_id"]), "method": match["match_method"]})
    return receipt_intelligence_payload(db, acquisition_id)


def _allocate_weighted(amount: int, weights: list[tuple[int, int]]) -> dict[int, int]:
    if not weights or sum(weight for _, weight in weights) <= 0:
        raise ValueError("Positive merchandise values are required for proportional allocation")
    sign = -1 if amount < 0 else 1
    remaining_amount = abs(amount)
    total_weight = sum(weight for _, weight in weights)
    allocations = {line_id: remaining_amount * weight // total_weight for line_id, weight in weights}
    assigned = sum(allocations.values())
    remainders = sorted(weights, key=lambda item: (-(remaining_amount * item[1] % total_weight), item[0]))
    for index in range(remaining_amount - assigned):
        allocations[remainders[index][0]] += 1
    return {line_id: sign * cents for line_id, cents in allocations.items()}


def generate_allocation_proposal(db: sqlite3.Connection, acquisition_id: int, payload: Mapping) -> dict:
    request_id = str(payload.get("request_id") or "").strip()
    if not request_id:
        raise ValueError("request_id is required")
    existing = db.execute("SELECT * FROM receipt_allocation_proposals WHERE request_id=?", (request_id,)).fetchone()
    if existing:
        return _proposal_payload(existing) | {"idempotent_replay": True}
    acquisition = _acquisition(db, acquisition_id)
    _require_revision(acquisition, payload)
    active_lines = db.execute("SELECT * FROM acquisition_lines WHERE acquisition_id=? AND canceled_at IS NULL ORDER BY id", (acquisition_id,)).fetchall()
    if not active_lines:
        raise ValueError("At least one inventory product line is required for receipt allocation")
    final_paid = acquisition.get("final_usd_paid_cents")
    if final_paid is None:
        raise ValueError("Final USD remains Unknown; allocation cannot be proposed")
    active_jobs = active_extraction_job_ids(db, acquisition_id=acquisition_id)
    if not active_jobs:
        raise ValueError("No current receipt extraction is available for allocation")
    active_placeholders = ",".join("?" for _ in active_jobs)
    parsed_receipt_rows = db.execute(
        """SELECT r.* FROM receipt_lines r JOIN receipt_extraction_jobs j ON j.id=r.job_id
            JOIN acquisition_documents d ON d.id=j.document_id
            WHERE r.acquisition_id=? AND j.id IN (""" + active_placeholders + """)
              AND j.status='COMPLETED' AND j.disposition<>'REJECTED'
              AND d.storage_status='STORED'
              AND r.classification NOT IN ('DUPLICATE_EXTRACTION','SHIPPING_FEE') ORDER BY r.id""",
        (acquisition_id, *active_jobs),
    ).fetchall()
    receipt_rows = [
        row for row in parsed_receipt_rows
        if semantic_allows_receipt_line(db, int(row["id"]))
    ]
    if not receipt_rows:
        raise ValueError("No merchandise receipt lines are available for allocation")
    if any(row["classification"] == "UNRESOLVED" for row in receipt_rows):
        raise ValueError("Classify unresolved merchandise before deterministic allocation")
    if any(row["classification"] in ("PERSONAL_NONBUSINESS", "BUSINESS_NONINVENTORY") for row in receipt_rows):
        raise ValueError(
            "Mixed inventory/noninventory landed-cost allocation requires an approved accounting policy"
        )
    if any(row["line_total_cents"] is None or int(row["line_total_cents"]) < 0 for row in receipt_rows):
        raise ValueError("Every merchandise receipt line needs a nonnegative line total")
    direct = {int(line["id"]): 0 for line in active_lines}
    for receipt in [row for row in receipt_rows if row["classification"] == "INVENTORY"]:
        match = db.execute(
            """SELECT * FROM receipt_line_matches WHERE receipt_line_id=? AND status<>'REJECTED'
                AND (match_method<>'FUZZY_TEXT' OR status='ACCEPTED') ORDER BY confidence DESC,id LIMIT 1""", (receipt["id"],)
        ).fetchone()
        if match is None or receipt["line_total_cents"] is None:
            raise ValueError("Every inventory receipt line needs a deterministic match and line total")
        direct[int(match["acquisition_line_id"])] += int(receipt["line_total_cents"])
        target = next(line for line in active_lines if int(line["id"]) == int(match["acquisition_line_id"]))
        if receipt["quantity"] and target["quantity"] and int(receipt["quantity"]) != int(target["quantity"]):
            raise ValueError("Receipt quantity conflicts with the acquisition product quantity")
    if any(value <= 0 for value in direct.values()):
        raise ValueError("Every acquisition product line needs matched positive merchandise value")
    math_row = db.execute(
        """SELECT e.payload FROM receipt_extraction_events e
            JOIN receipt_extraction_jobs j ON j.id=e.job_id
            JOIN acquisition_documents d ON d.id=j.document_id
            WHERE e.acquisition_id=? AND e.event_type='RECEIPT_MATH_ANALYZED'
              AND j.id IN (""" + active_placeholders + """)
              AND j.status='COMPLETED' AND j.disposition<>'REJECTED' AND d.storage_status='STORED'
            ORDER BY e.recorded_at DESC,e.event_id DESC LIMIT 1""",
        (acquisition_id, *active_jobs),
    ).fetchone()
    receipt_math = json.loads(math_row["payload"] or "{}").get("receipt_math", {}) if math_row else {}
    weights = sorted(direct.items())
    merchandise_total = sum(int(row["line_total_cents"]) for row in receipt_rows)
    if receipt_math.get("status") != "RECONCILED_EXACT" or not receipt_math.get("allocation_ready"):
        raise ValueError("Receipt arithmetic must reconcile exactly before deterministic allocation")
    if int(receipt_math.get("merchandise_total_cents", -1)) != merchandise_total:
        raise ValueError("Receipt merchandise changed after arithmetic analysis; re-extract before allocation")
    shared_allocations = {line_id: 0 for line_id in direct}
    component_allocations: list[dict] = []
    supported_kinds = {"TAX", "SHIPPING", "FEE", "DISCOUNT", "DUTIES", "BROKERAGE"}
    applied_components = [
        dict(item) for item in receipt_math.get("components", [])
        if item.get("kind") in supported_kinds
        and item.get("math_role") in ("INCLUDED_IN_SUBTOTAL", "OUTSIDE_SUBTOTAL")
    ]
    for sequence, component in enumerate(applied_components):
        cents = int(component.get("signed_cents") or 0)
        allocated = _allocate_weighted(cents, weights) if cents else {
            line_id: 0 for line_id in direct
        }
        component_allocations.append(
            {
                "component_sequence": sequence,
                "kind": component.get("kind"),
                "label": component.get("label"),
                "scope": component.get("scope", "PURCHASE"),
                "math_role": component.get("math_role"),
                "signed_cents": cents,
                "allocations": allocated,
            }
        )
        for line_id, value in allocated.items():
            shared_allocations[line_id] += value
    if merchandise_total + sum(int(item["signed_cents"]) for item in applied_components) != int(final_paid):
        raise ValueError("Separate receipt components do not reconcile exactly to final USD")
    allocations = [
        {"acquisition_line_id": line_id, "direct_merchandise_cents": direct[line_id],
         "shared_component_cents": shared_allocations[line_id], "landed_cost_cents": direct[line_id] + shared_allocations[line_id]}
        for line_id in sorted(direct)
    ]
    total = sum(item["landed_cost_cents"] for item in allocations)
    difference = int(final_paid) - total
    now = utcnow()
    db.execute("UPDATE receipt_allocation_proposals SET status='SUPERSEDED',updated_at=? WHERE acquisition_id=? AND status IN ('PROPOSED','APPLIED')", (now, acquisition_id))
    cursor = db.execute(
        """INSERT INTO receipt_allocation_proposals
           (proposal_uuid,request_id,acquisition_id,method,calculation_version,status,input_facts,allocations,
            total_allocated_cents,difference_cents,explanation,created_at,updated_at)
           VALUES (?,?,?,?,?,'APPLIED',?,?,?,?,?,?,?)""",
        (f"RCPT-ALLOC-{uuid.uuid4()}", request_id, acquisition_id, "RECEIPT_VALUE_PROPORTIONAL", ALLOCATION_VERSION,
         json.dumps({
             "direct": direct,
             "shared_components": applied_components,
             "component_allocations": component_allocations,
             "receipt_math_version": receipt_math.get("version"),
         }, separators=(",", ":"), sort_keys=True),
         json.dumps(allocations, separators=(",", ":"), sort_keys=True), total, difference,
         "Existing receipt-landed-allocation-v1: direct receipt merchandise plus each separately preserved shared component allocated proportionally by merchandise value; remainder cents follow fractional remainder then immutable acquisition-line ID.", now, now),
    )
    for item in allocations:
        db.execute("UPDATE acquisition_lines SET assigned_landed_cost_cents=?,allocation_method='RECEIPT_VALUE_PROPORTIONAL',allocation_status='SUGGESTED',updated_at=? WHERE id=?",
                   (item["landed_cost_cents"], now, item["acquisition_line_id"]))
    db.execute("UPDATE acquisitions SET revision=revision+1,updated_at=? WHERE id=?", (now, acquisition_id))
    _event(db, acquisition_id, f"{request_id}:event", "ALLOCATION_PROPOSED",
           payload={"proposal_id": int(cursor.lastrowid), "method": "RECEIPT_VALUE_PROPORTIONAL", "version": ALLOCATION_VERSION,
                    "total_allocated_cents": total, "difference_cents": difference,
                    "policy_boundary": "EXISTING_ALL_INVENTORY_V1"})
    return _proposal_payload(db.execute("SELECT * FROM receipt_allocation_proposals WHERE id=?", (cursor.lastrowid,)).fetchone())


def _proposal_payload(row: Mapping | None) -> dict | None:
    if row is None:
        return None
    item = dict(row)
    item["input_facts"] = json.loads(item["input_facts"] or "{}")
    item["allocations"] = json.loads(item["allocations"] or "[]")
    item["authoritative"] = item["status"] == "ACCEPTED"
    return item


def allocation_for_confirmation(db: sqlite3.Connection, acquisition_id: int, final_paid: int) -> dict | None:
    active_jobs = active_extraction_job_ids(db, acquisition_id=acquisition_id)
    active_receipt = bool(active_jobs) and bool(db.execute(
        "SELECT 1 FROM receipt_extraction_jobs WHERE id IN ("
        + ",".join("?" for _ in active_jobs)
        + ") AND status='COMPLETED' LIMIT 1",
        active_jobs,
    ).fetchone())
    if not active_receipt:
        return None
    row = db.execute(
        """SELECT * FROM receipt_allocation_proposals WHERE acquisition_id=? AND status='APPLIED'
            ORDER BY created_at DESC,id DESC LIMIT 1""", (acquisition_id,)
    ).fetchone()
    proposal = _proposal_payload(row)
    if not proposal or proposal["difference_cents"] != 0 or proposal["total_allocated_cents"] != int(final_paid):
        return None
    current = {int(line["id"]): line for line in db.execute("SELECT * FROM acquisition_lines WHERE acquisition_id=? AND canceled_at IS NULL", (acquisition_id,)).fetchall()}
    for item in proposal["allocations"]:
        line = current.get(int(item["acquisition_line_id"]))
        if not line or line["allocation_status"] != "SUGGESTED" or line["allocation_method"] != "RECEIPT_VALUE_PROPORTIONAL" or int(line["assigned_landed_cost_cents"] or -1) != int(item["landed_cost_cents"]):
            return None
    return proposal


def accept_allocation_on_confirmation(db: sqlite3.Connection, acquisition_id: int, proposal: Mapping, request_id: str) -> None:
    now = utcnow()
    for item in proposal["allocations"]:
        db.execute("UPDATE acquisition_lines SET allocation_status='CONFIRMED',updated_at=? WHERE id=?", (now, item["acquisition_line_id"]))
    db.execute("UPDATE receipt_allocation_proposals SET status='ACCEPTED',accepted_at=?,updated_at=? WHERE id=?", (now, now, proposal["id"]))
    _event(db, acquisition_id, f"{request_id}:receipt-allocation", "ALLOCATION_ACCEPTED",
           payload={"proposal_id": proposal["id"], "method": proposal["method"], "version": proposal["calculation_version"],
                    "allocations": proposal["allocations"], "total_allocated_cents": proposal["total_allocated_cents"]})


def receipt_intelligence_payload(db: sqlite3.Connection, acquisition_id: int) -> dict:
    all_jobs = [_job_payload(db, int(row["id"])) for row in db.execute(
        "SELECT id FROM receipt_extraction_jobs WHERE acquisition_id=? ORDER BY created_at,id", (acquisition_id,)
    ).fetchall()]
    active_job_ids = set(active_extraction_job_ids(db, acquisition_id=acquisition_id))
    jobs = [job for job in all_jobs if int(job["id"]) in active_job_ids]
    historical_jobs = [job for job in all_jobs if int(job["id"]) not in active_job_ids]
    for job in jobs:
        job["active"] = True
    for job in historical_jobs:
        document = db.execute(
            "SELECT storage_status FROM acquisition_documents WHERE id=?", (int(job["document_id"]),)
        ).fetchone()
        job["active"] = False
        job["history_reason"] = (
            "REMOVED_DOCUMENT"
            if not document or document["storage_status"] != "STORED"
            else "SUPERSEDED_EXTRACTION"
        )
    groups = _candidate_groups(db, acquisition_id)
    acquisition = _acquisition(db, acquisition_id)
    conflicts = []
    proposed_fields = []
    low_confidence_critical = []
    for field, candidates in groups.items():
        distinct = {str(item["normalized_value"]) for item in candidates}
        if len(distinct) > 1:
            conflicts.append({"field_name": field, "candidate_ids": [int(item["id"]) for item in candidates], "values": sorted(distinct)})
        current = acquisition.get(field)
        for item in candidates:
            provenance = db.execute("SELECT * FROM acquisition_field_provenance WHERE acquisition_id=? AND field_name=? AND candidate_id=? ORDER BY id DESC LIMIT 1", (acquisition_id, field, item["id"])).fetchone()
            item["application_status"] = provenance["status"] if provenance else "NOT_APPLIED"
            item["operator_value"] = provenance["operator_value"] if provenance else None
            item["conflicts_with_manual"] = bool(
                (not provenance or provenance["status"] != "OPERATOR_REPLACED")
                and not _field_empty(field, current) and str(current) != str(item["value"])
            )
            if provenance and provenance["status"] in ("PROPOSED", "ACCEPTED"):
                proposed_fields.append({"field_name": field, "candidate_id": int(item["id"]), "value": item["value"], "confidence_band": item["confidence_band"], "status": provenance["status"]})
            if field in CRITICAL_FIELDS and item["confidence_band"] == "LOW":
                low_confidence_critical.append(field)
    parsed_receipt_lines = []
    if active_job_ids:
        placeholders = ",".join("?" for _ in active_job_ids)
        parsed_receipt_lines = [receipt_line_payload(db, row) for row in db.execute(
            "SELECT r.* FROM receipt_lines r WHERE r.acquisition_id=? "
            f"AND r.job_id IN ({placeholders}) ORDER BY r.id",
            (acquisition_id, *sorted(active_job_ids)),
        ).fetchall()]
    receipt_lines = [
        item for item in parsed_receipt_lines
        if semantic_allows_receipt_line(db, int(item["id"]))
    ]
    unresolved = [item for item in receipt_lines if item["classification"] == "UNRESOLVED"]
    fuzzy = [item for item in receipt_lines if item.get("best_match") and item["best_match"]["match_method"] == "FUZZY_TEXT"]
    quantity_conflicts = []
    for item in receipt_lines:
        match = item.get("best_match")
        if match and item.get("quantity"):
            line = db.execute("SELECT quantity FROM acquisition_lines WHERE id=?", (match["acquisition_line_id"],)).fetchone()
            if line and line["quantity"] and int(line["quantity"]) != int(item["quantity"]):
                quantity_conflicts.append(item["id"])
    proposal = None
    if active_job_ids:
        proposal = _proposal_payload(db.execute(
            "SELECT * FROM receipt_allocation_proposals WHERE acquisition_id=? AND status IN ('APPLIED','ACCEPTED') ORDER BY created_at DESC,id DESC LIMIT 1", (acquisition_id,)
        ).fetchone())
    latest_analysis_job = next(
        (job for job in reversed(jobs) if job.get("receipt_math")), None
    )
    receipt_math = latest_analysis_job.get("receipt_math") if latest_analysis_job else None
    performance = latest_analysis_job.get("performance", {}) if latest_analysis_job else {}
    receipt_classes = {str(item.get("classification") or "") for item in receipt_lines}
    mixed_inventory_noninventory = bool(
        "INVENTORY" in receipt_classes
        and receipt_classes.intersection({"BUSINESS_NONINVENTORY", "PERSONAL_NONBUSINESS"})
    )
    allocation_policy = {
        "status": "POLICY_REQUIRED",
        "scope": "MIXED_INVENTORY_NONINVENTORY",
        "message": (
            "Receipt extraction and arithmetic are complete, but DEX has no approved default "
            "for assigning shared purchase components between inventory and noninventory."
        ),
        "preserved_components": [
            {
                "kind": item.get("kind"), "label": item.get("label"),
                "signed_cents": item.get("signed_cents"),
                "scope": item.get("scope", "PURCHASE"),
                "math_role": item.get("math_role"),
            }
            for item in (receipt_math or {}).get("components", [])
        ],
        "required_policy_dimensions": [
            "SALES_TAX", "TRANSACTION_CARD_FEES", "SHIPPING_FREIGHT",
            "PURCHASE_DISCOUNTS_CREDITS", "CENT_ROUNDING_REMAINDERS",
        ],
        "authoritative": False,
    } if mixed_inventory_noninventory else {
        "status": "EXISTING_V1",
        "scope": "ALL_INVENTORY",
        "calculation_version": ALLOCATION_VERSION,
        "authoritative": False,
    }
    warnings = []
    if conflicts or any(item["conflicts_with_manual"] for candidates in groups.values() for item in candidates):
        warnings.append({"code": "RECEIPT_FIELD_CONFLICT", "message": "Receipt candidates conflict with another document or existing manual facts."})
    if low_confidence_critical:
        warnings.append({"code": "LOW_CONFIDENCE_CRITICAL_VALUE", "message": "A critical receipt value has low confidence and needs review."})
    if unresolved:
        warnings.append({"code": "UNRESOLVED_RECEIPT_LINES", "message": "Classify or match unresolved receipt lines before automatic allocation."})
    if fuzzy:
        warnings.append({"code": "AMBIGUOUS_PRODUCT_MATCH", "message": "Text-similarity matches remain suggestions and need operator review."})
    if quantity_conflicts:
        warnings.append({"code": "RECEIPT_QUANTITY_MISMATCH", "message": "Receipt quantities conflict with acquisition product quantities."})
    if receipt_math and receipt_math.get("status") == "AMBIGUOUS":
        warnings.append({"code": "RECEIPT_MATH_AMBIGUOUS", "message": "More than one receipt-math interpretation is possible; DEX will not guess."})
    elif receipt_math and receipt_math.get("status") == "UNRECONCILED":
        warnings.append({"code": "RECEIPT_MATH_UNRECONCILED", "message": "Printed receipt components do not reconcile exactly to final paid."})
    if mixed_inventory_noninventory:
        warnings.append({
            "code": "MIXED_PURCHASE_ALLOCATION_POLICY_REQUIRED",
            "message": "An approved mixed-purchase shared-component policy is required before landed cost can be finalized.",
        })
    elif len([row for row in db.execute("SELECT id FROM acquisition_lines WHERE acquisition_id=? AND canceled_at IS NULL", (acquisition_id,)).fetchall()]) > 1 and jobs and not proposal:
        warnings.append({"code": "RECEIPT_ALLOCATION_UNRESOLVED", "message": "Receipt evidence does not yet support an exact multi-line landed-cost allocation."})
    failed_jobs = [job for job in jobs if job["status"] == "FAILED"]
    unavailable_jobs = [job for job in failed_jobs if job.get("capability_unavailable")]
    manual_fallback_available = bool(
        jobs
        and not any(job["status"] == "COMPLETED" for job in jobs)
        and any(job["status"] in ("FAILED", "NO_FACTS") for job in jobs)
    )
    manual_fallback_selected = bool(db.execute(
        """SELECT 1 FROM receipt_extraction_events
            WHERE acquisition_id=? AND event_type='MANUAL_FALLBACK_SELECTED' LIMIT 1""",
        (acquisition_id,),
    ).fetchone())
    status = "NOT_REQUESTED"
    if any(job["status"] == "PROCESSING" for job in jobs): status = "PROCESSING"
    elif any(job["status"] == "COMPLETED" for job in jobs): status = "READY_TO_REVIEW"
    elif failed_jobs and unavailable_jobs and len(unavailable_jobs) == len(failed_jobs): status = "FAILED_MANUAL_AVAILABLE"
    elif failed_jobs: status = "FAILED_RETRYABLE"
    elif jobs: status = "NO_FACTS"
    return {
        "status": status, "jobs": jobs, "historical_jobs": historical_jobs,
        "candidate_groups": groups, "proposed_fields": proposed_fields,
        "conflicts": conflicts, "receipt_lines": receipt_lines, "allocation_proposal": proposal,
        "warnings": warnings, "failed_job_count": len(failed_jobs), "manual_entry_available": True,
        "manual_fallback_available": manual_fallback_available,
        "manual_fallback_selected": manual_fallback_selected,
        "retry_plausible": any(job.get("retry_plausible") for job in jobs),
        "raw_ocr_available": False, "external_transmission": False,
        "receipt_math": receipt_math,
        "semantic_review": semantic_review_payload(db, acquisition_id),
        "performance": performance,
        "allocation_policy": allocation_policy,
        "operator_questions": [
            {
                "receipt_line_id": int(item["id"]),
                "description": item["description"],
                "question": "How should this purchase item be treated?",
                "choices": ["INVENTORY", "BUSINESS_NONINVENTORY", "PERSONAL_NONBUSINESS"],
            }
            for item in unresolved
        ],
        "calculation_version": ALLOCATION_VERSION,
    }


def select_manual_fallback(db: sqlite3.Connection, acquisition_id: int, payload: Mapping) -> dict:
    """Record that the operator will use independently confirmed manual facts.

    This event does not accept extraction, allocate basis, or confirm any financial
    fact. It only makes an unavailable receipt allocation informational while the
    established acquisition confirmation rules continue to enforce all accounting.
    """

    request_id = str(payload.get("request_id") or "").strip()
    if not request_id:
        raise ValueError("request_id is required")
    prior = db.execute(
        "SELECT 1 FROM receipt_extraction_events WHERE request_id=?", (request_id,)
    ).fetchone()
    if prior:
        return receipt_intelligence_payload(db, acquisition_id) | {"idempotent_replay": True}
    acquisition = _acquisition(db, acquisition_id)
    _require_revision(acquisition, payload)
    if payload.get("confirm_manual_fallback") is not True:
        raise ValueError("Explicit confirmation is required to continue with manual purchase facts")
    intelligence = receipt_intelligence_payload(db, acquisition_id)
    if not intelligence["manual_fallback_available"]:
        raise ValueError("Manual receipt fallback is available only after active extraction is unavailable or returns no facts")
    affected_jobs = [
        {"job_uuid": job["job_uuid"], "status": job["status"], "error_code": job.get("error_code")}
        for job in intelligence["jobs"]
        if job["status"] in ("FAILED", "NO_FACTS")
    ]
    db.execute(
        "UPDATE acquisitions SET revision=revision+1,updated_at=? WHERE id=?",
        (utcnow(), acquisition_id),
    )
    _event(
        db,
        acquisition_id,
        request_id,
        "MANUAL_FALLBACK_SELECTED",
        reason_code="OPERATOR_MANUAL_FACTS",
        notes="Operator chose authoritative manual purchase facts after receipt extraction was unavailable",
        payload={
            "affected_jobs": affected_jobs,
            "receipt_remains_supporting_evidence": True,
            "financial_facts_confirmed": False,
            "allocation_authority_created": False,
        },
    )
    return receipt_intelligence_payload(db, acquisition_id)


def retry_extraction(db: sqlite3.Connection, job_uuid: str, payload: Mapping,
                     store: DocumentStore, extractor: ReceiptExtractor) -> dict:
    prior = db.execute("SELECT * FROM receipt_extraction_jobs WHERE job_uuid=?", (job_uuid,)).fetchone()
    if prior is None:
        raise ValueError("Extraction job not found")
    if prior["status"] not in ("FAILED", "NO_FACTS"):
        raise ValueError("Only failed or no-facts extraction jobs can be retried")
    if prior["error_code"] == "FORMAT_PROVIDER_UNAVAILABLE":
        raise ValueError("Retry is unavailable because the installed local provider cannot extract this image format; continue with manual purchase facts")
    retry_payload = dict(payload)
    retry_payload["retry_of_job_id"] = int(prior["id"])
    return queue_extraction(db, int(prior["document_id"]), retry_payload, store, extractor)
