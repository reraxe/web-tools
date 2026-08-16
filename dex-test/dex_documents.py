"""DEX v2.2-test Phase 4 private source-document infrastructure.

Binary artifacts intentionally live outside SQLite.  This module exposes a
provider-neutral contract, a private local-filesystem implementation, and an
unconfigured Google Drive-compatible boundary for a later approved phase.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import os
import re
import sqlite3
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from PIL import Image, UnidentifiedImageError


DEFAULT_MAX_BYTES = 15 * 1024 * 1024
DEFAULT_MAX_IMAGE_PIXELS = 80_000_000
DEFAULT_MAX_PDF_PAGES = 50
DOCUMENT_ROLES = ("RECEIPT", "INVOICE", "ORDER_CONFIRMATION", "SOURCE_EVIDENCE", "OTHER")
CAPTURE_METHODS = ("CAMERA", "FILE_UPLOAD", "SCREENSHOT", "PDF_UPLOAD")
SUPPORTED_MIME_TYPES = ("image/jpeg", "image/png", "application/pdf")
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class DocumentError(ValueError):
    code = "DOCUMENT_ERROR"


class DocumentValidationError(DocumentError):
    code = "VALIDATION_FAILED"


class DocumentIntegrityError(DocumentError):
    code = "INTEGRITY_FAILED"


class DocumentProviderError(DocumentError):
    code = "PROVIDER_UNAVAILABLE"


class DocumentStore(ABC):
    """Provider-neutral private artifact contract."""

    provider_name: str

    @abstractmethod
    def store(self, document_uuid: str, safe_filename: str, data: bytes) -> str: ...

    @abstractmethod
    def metadata(self, resource_id: str) -> dict: ...

    @abstractmethod
    def retrieve(self, resource_id: str) -> bytes: ...

    @abstractmethod
    def verify(self, resource_id: str, expected_sha256: str) -> dict: ...

    @abstractmethod
    def tombstone(self, resource_id: str, preserve_content: bool) -> None: ...

    @abstractmethod
    def health(self) -> dict: ...


class LocalFilesystemDocumentStore(DocumentStore):
    provider_name = "LOCAL_PRIVATE_FILESYSTEM"

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.active_root = self.root / "active"
        self.tombstone_root = self.root / "tombstones"

    def _path(self, resource_id: str) -> Path:
        if not re.fullmatch(r"(?:active|tombstones)/[0-9a-f-]{36}/[A-Za-z0-9._-]+", resource_id):
            raise DocumentProviderError("Invalid provider resource identifier")
        path = (self.root / resource_id).resolve()
        if self.root not in path.parents:
            raise DocumentProviderError("Document path escaped the private storage root")
        return path

    def store(self, document_uuid: str, safe_filename: str, data: bytes) -> str:
        directory = (self.active_root / document_uuid).resolve()
        if self.root not in directory.parents:
            raise DocumentProviderError("Document path escaped the private storage root")
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / safe_filename
        temporary = directory / f".{safe_filename}.{uuid.uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(target)
        finally:
            if temporary.exists():
                temporary.unlink()
        return target.relative_to(self.root).as_posix()

    def metadata(self, resource_id: str) -> dict:
        path = self._path(resource_id)
        stat = path.stat()
        return {"resource_id": resource_id, "byte_size": stat.st_size, "modified_at": stat.st_mtime}

    def retrieve(self, resource_id: str) -> bytes:
        path = self._path(resource_id)
        if not path.is_file():
            raise DocumentProviderError("Stored document is unavailable")
        return path.read_bytes()

    def verify(self, resource_id: str, expected_sha256: str) -> dict:
        data = self.retrieve(resource_id)
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected_sha256:
            raise DocumentIntegrityError("Stored document hash no longer matches its recorded SHA-256")
        return {"verified": True, "sha256": actual, "byte_size": len(data)}

    def tombstone(self, resource_id: str, preserve_content: bool) -> None:
        source = self._path(resource_id)
        if not source.exists():
            return
        if preserve_content:
            parts = Path(resource_id).parts
            target = self.tombstone_root / parts[1] / parts[2]
            target.parent.mkdir(parents=True, exist_ok=True)
            source.replace(target)
            try:
                source.parent.rmdir()
            except OSError:
                pass
        else:
            source.unlink()
            try:
                source.parent.rmdir()
            except OSError:
                pass

    def health(self) -> dict:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            writable = os.access(self.root, os.W_OK)
        except OSError:
            writable = False
        return {
            "provider": self.provider_name,
            "configured": True,
            "available": writable,
            "private": True,
            "public_links": False,
        }


class GoogleDriveCompatibleDocumentStore(DocumentStore):
    """Deliberately inert Phase 4 adapter boundary; no credentials are accepted here."""

    provider_name = "GOOGLE_DRIVE_COMPATIBLE"

    def _unavailable(self, *_args, **_kwargs):
        raise DocumentProviderError("Google Drive-compatible storage is provider-ready but not configured in Phase 4")

    store = metadata = retrieve = verify = tombstone = _unavailable

    def health(self) -> dict:
        return {
            "provider": self.provider_name,
            "configured": False,
            "available": False,
            "private": True,
            "public_links": False,
            "status": "PROVIDER_READY_NOT_CONFIGURED",
        }


def get_document_store(data_dir: Path | None = None) -> DocumentStore:
    provider = os.environ.get("DEX_DOCUMENT_PROVIDER", "LOCAL").strip().upper()
    if provider in ("GOOGLE_DRIVE", "GOOGLE_DRIVE_COMPATIBLE"):
        return GoogleDriveCompatibleDocumentStore()
    root = Path(os.environ.get("DEX_DOCUMENT_DIR", str((data_dir or Path("data")) / "source-documents")))
    return LocalFilesystemDocumentStore(root)


def provider_contract(store: DocumentStore) -> dict:
    maximum = int(os.environ.get("DEX_DOCUMENT_MAX_BYTES", DEFAULT_MAX_BYTES))
    return {
        "phase": "INBOUND_2_PHASE_4_SOURCE_DOCUMENTS",
        "active": store.health(),
        "available_providers": [store.health(), GoogleDriveCompatibleDocumentStore().health()],
        "supported_mime_types": list(SUPPORTED_MIME_TYPES),
        "accepted_extensions": [".jpg", ".jpeg", ".png", ".pdf"],
        "heic_status": "UNAVAILABLE_WITHOUT_VERIFIED_DECODER",
        "max_bytes": maximum,
        "max_pdf_pages": DEFAULT_MAX_PDF_PAGES,
        "raw_artifacts_in_sqlite": False,
        "extraction_enabled": False,
        "public_links": False,
    }


def safe_filename(original: object, document_uuid: str) -> str:
    raw = Path(str(original or "document").replace("\\", "/")).name
    cleaned = SAFE_NAME_RE.sub("-", raw).strip(".-")[:100]
    suffix = Path(cleaned).suffix.lower()
    stem = Path(cleaned).stem[:70] or "document"
    return f"{stem}-{document_uuid[:8]}{suffix}"


def _detect_mime(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if len(data) >= 12 and data[4:12] in (b"ftypheic", b"ftypheix", b"ftyphevc", b"ftypmif1"):
        raise DocumentValidationError("HEIC/HEIF needs a verified server decoder and is unavailable in this runtime")
    raise DocumentValidationError("Unsupported or unrecognized document signature")


def _validate_image(data: bytes, detected_mime: str) -> None:
    previous = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = int(os.environ.get("DEX_DOCUMENT_MAX_IMAGE_PIXELS", DEFAULT_MAX_IMAGE_PIXELS))
    try:
        with Image.open(io.BytesIO(data)) as image:
            expected = "JPEG" if detected_mime == "image/jpeg" else "PNG"
            if image.format != expected:
                raise DocumentValidationError("Image signature and decoded format do not agree")
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise DocumentValidationError("Image is malformed or exceeds safe decoding limits") from exc
    finally:
        Image.MAX_IMAGE_PIXELS = previous


def _validate_pdf(data: bytes) -> int:
    if b"%%EOF" not in data[-2048:]:
        raise DocumentValidationError("PDF is incomplete or malformed")
    if re.search(br"/Encrypt\b", data):
        raise DocumentValidationError("Encrypted PDFs are not supported")
    page_count = len(re.findall(br"/Type\s*/Page\b", data))
    if page_count <= 0:
        raise DocumentValidationError("PDF has no readable page structure")
    maximum = int(os.environ.get("DEX_DOCUMENT_MAX_PDF_PAGES", DEFAULT_MAX_PDF_PAGES))
    if page_count > maximum:
        raise DocumentValidationError(f"PDF exceeds the {maximum}-page safety limit")
    return page_count


def validate_document(data: bytes, original_filename: object, declared_mime_type: object) -> dict:
    maximum = int(os.environ.get("DEX_DOCUMENT_MAX_BYTES", DEFAULT_MAX_BYTES))
    if not data:
        raise DocumentValidationError("Document is empty")
    if len(data) > maximum:
        raise DocumentValidationError(f"Document exceeds the {maximum // (1024 * 1024)} MB limit")
    detected = _detect_mime(data)
    declared = str(declared_mime_type or "").split(";", 1)[0].strip().lower()
    if declared and declared not in (detected, "application/octet-stream"):
        raise DocumentValidationError("Declared MIME type does not match the file signature")
    extension = Path(str(original_filename or "")).suffix.lower()
    allowed = {
        "image/jpeg": {".jpg", ".jpeg"},
        "image/png": {".png"},
        "application/pdf": {".pdf"},
    }
    if extension and extension not in allowed[detected]:
        raise DocumentValidationError("Filename extension does not match the file signature")
    pages = None
    if detected.startswith("image/"):
        _validate_image(data, detected)
    else:
        pages = _validate_pdf(data)
    return {
        "detected_mime_type": detected,
        "byte_size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "pdf_page_count": pages,
    }


def decode_upload(value: object) -> bytes:
    text = str(value or "")
    if "," in text and text.startswith("data:"):
        text = text.split(",", 1)[1]
    try:
        return base64.b64decode(text, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise DocumentValidationError("Document payload is not valid base64") from exc


def document_payload(row: Mapping) -> dict:
    item = dict(row)
    item["view_available"] = item.get("storage_status") == "STORED" and item.get("integrity_status") != "FAILED"
    item["content_url"] = f"/api/acquisition-documents/{item['id']}/content" if item["view_available"] else None
    item["metadata_url"] = f"/api/acquisition-documents/{item['id']}"
    item["raw_provider_link"] = None
    item["extraction_enabled"] = False
    return item


def list_documents(db: sqlite3.Connection, acquisition_id: int, include_tombstones: bool = True) -> list[dict]:
    suffix = "" if include_tombstones else " AND storage_status<>'TOMBSTONED'"
    rows = db.execute(
        f"SELECT * FROM acquisition_documents WHERE acquisition_id=?{suffix} ORDER BY created_at,id",
        (acquisition_id,),
    ).fetchall()
    return [document_payload(row) for row in rows]


def document_summary(db: sqlite3.Connection, acquisition_id: int) -> dict:
    documents = list_documents(db, acquisition_id)
    active = [item for item in documents if item["storage_status"] == "STORED"]
    return {
        "documents": documents,
        "active_count": len(active),
        "failed_count": sum(item["storage_status"] == "FAILED" for item in documents),
        "tombstone_count": sum(item["storage_status"] == "TOMBSTONED" for item in documents),
        "has_source_evidence": bool(active),
        "extraction_status": "NOT_REQUESTED",
    }


def _acquisition(db: sqlite3.Connection, acquisition_id: int) -> dict:
    row = db.execute("SELECT * FROM acquisitions WHERE id=?", (acquisition_id,)).fetchone()
    if row is None:
        raise DocumentError("Acquisition not found")
    return dict(row)


def _check_revision(acquisition: Mapping, expected: object) -> None:
    if expected is None or int(expected) != int(acquisition["revision"]):
        raise DocumentError("Acquisition changed in another session; refresh before attaching documents")


def _event(db: sqlite3.Connection, acquisition_id: int, document_id: int | None, request_id: str,
           event_type: str, reason_code: str = "", notes: str = "", payload: dict | None = None) -> None:
    now = utcnow()
    db.execute(
        """INSERT INTO acquisition_document_events
           (event_id,request_id,acquisition_id,document_id,event_type,effective_at,recorded_at,reason_code,notes,payload)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (f"DOC-EVT-{uuid.uuid4()}", request_id, acquisition_id, document_id, event_type,
         now, now, reason_code, notes[:1000], json.dumps(payload or {}, separators=(",", ":"))),
    )


def _increment_revision(db: sqlite3.Connection, acquisition_id: int) -> None:
    db.execute("UPDATE acquisitions SET revision=revision+1,updated_at=? WHERE id=?", (utcnow(), acquisition_id))


def upload_document(db: sqlite3.Connection, acquisition_id: int, payload: Mapping, store: DocumentStore) -> dict:
    request_id = str(payload.get("request_id") or "").strip()
    if not request_id:
        raise DocumentError("request_id is required")
    existing = db.execute("SELECT * FROM acquisition_documents WHERE upload_request_id=?", (request_id,)).fetchone()
    if existing:
        if int(existing["acquisition_id"]) != acquisition_id:
            raise DocumentError("request_id already belongs to another acquisition")
        return {"document": document_payload(existing), "idempotent_replay": True, "duplicate": False}
    suppressed = db.execute(
        "SELECT document_id FROM acquisition_document_events WHERE request_id=? AND event_type='DOCUMENT_DUPLICATE_SUPPRESSED'",
        (request_id,),
    ).fetchone()
    if suppressed:
        document = get_document(db, int(suppressed["document_id"]))
        if int(document["acquisition_id"]) != acquisition_id:
            raise DocumentError("request_id already belongs to another acquisition")
        return {"document": document, "idempotent_replay": True, "duplicate": True}
    acquisition = _acquisition(db, acquisition_id)
    _check_revision(acquisition, payload.get("expected_revision"))
    role = str(payload.get("document_role") or "RECEIPT").upper()
    capture = str(payload.get("capture_method") or "FILE_UPLOAD").upper()
    if role not in DOCUMENT_ROLES or capture not in CAPTURE_METHODS:
        raise DocumentError("Unsupported document role or capture method")
    original = str(payload.get("original_filename") or "document")[:240]
    declared = str(payload.get("declared_mime_type") or "")[:120]
    document_uuid = str(uuid.uuid4())
    safe = safe_filename(original, document_uuid)
    now = utcnow()
    try:
        data = decode_upload(payload.get("data_base64"))
        facts = validate_document(data, original, declared)
    except DocumentValidationError as exc:
        cursor = db.execute(
            """INSERT INTO acquisition_documents
               (document_uuid,acquisition_id,upload_request_id,provider_name,original_filename,safe_filename,
                declared_mime_type,document_role,capture_method,storage_status,integrity_status,error_code,error_message,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,'FAILED','NOT_AVAILABLE',?,?,?,?)""",
            (document_uuid, acquisition_id, request_id, store.provider_name, original, safe, declared,
             role, capture, exc.code, str(exc)[:500], now, now),
        )
        _event(db, acquisition_id, int(cursor.lastrowid), f"{request_id}:failure", "DOCUMENT_STORAGE_FAILED",
               exc.code, str(exc), {"stage": "VALIDATION"})
        _increment_revision(db, acquisition_id)
        row = db.execute("SELECT * FROM acquisition_documents WHERE id=?", (cursor.lastrowid,)).fetchone()
        return {"document": document_payload(row), "upload_failed": True, "idempotent_replay": False, "duplicate": False}
    duplicate = db.execute(
        """SELECT * FROM acquisition_documents
           WHERE acquisition_id=? AND sha256=? AND storage_status='STORED' ORDER BY id LIMIT 1""",
        (acquisition_id, facts["sha256"]),
    ).fetchone()
    if duplicate:
        _event(db, acquisition_id, int(duplicate["id"]), request_id, "DOCUMENT_DUPLICATE_SUPPRESSED",
               "IDENTICAL_SHA256", "Identical source artifact already attached to this acquisition",
               {"document_id": int(duplicate["id"]), "sha256": facts["sha256"]})
        return {"document": document_payload(duplicate), "idempotent_replay": False, "duplicate": True}
    cursor = db.execute(
        """INSERT INTO acquisition_documents
           (document_uuid,acquisition_id,upload_request_id,provider_name,original_filename,safe_filename,
            declared_mime_type,detected_mime_type,byte_size,sha256,document_role,capture_method,storage_status,
            integrity_status,captured_at,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'PENDING','UNVERIFIED',?,?,?)""",
        (document_uuid, acquisition_id, request_id, store.provider_name, original, safe, declared,
         facts["detected_mime_type"], facts["byte_size"], facts["sha256"], role, capture,
         str(payload.get("captured_at") or "")[:40] or None, now, now),
    )
    document_id = int(cursor.lastrowid)
    try:
        resource_id = store.store(document_uuid, safe, data)
        store.verify(resource_id, facts["sha256"])
        db.execute(
            """UPDATE acquisition_documents SET provider_resource_id=?,storage_status='STORED',
                      integrity_status='VERIFIED',last_verified_at=?,updated_at=? WHERE id=?""",
            (resource_id, now, now, document_id),
        )
        _event(db, acquisition_id, document_id, f"{request_id}:attached", "DOCUMENT_ATTACHED",
               payload={"sha256": facts["sha256"], "byte_size": facts["byte_size"], "pdf_page_count": facts["pdf_page_count"]})
    except (OSError, DocumentError) as exc:
        db.execute(
            "UPDATE acquisition_documents SET storage_status='FAILED',integrity_status='NOT_AVAILABLE',error_code=?,error_message=?,updated_at=? WHERE id=?",
            (getattr(exc, "code", "STORAGE_FAILED"), str(exc)[:500], now, document_id),
        )
        _event(db, acquisition_id, document_id, f"{request_id}:failure", "DOCUMENT_STORAGE_FAILED",
               getattr(exc, "code", "STORAGE_FAILED"), str(exc), {"stage": "STORE"})
    _increment_revision(db, acquisition_id)
    row = db.execute("SELECT * FROM acquisition_documents WHERE id=?", (document_id,)).fetchone()
    return {"document": document_payload(row), "upload_failed": row["storage_status"] == "FAILED", "idempotent_replay": False, "duplicate": False}


def get_document(db: sqlite3.Connection, document_id: int) -> dict:
    row = db.execute("SELECT * FROM acquisition_documents WHERE id=?", (document_id,)).fetchone()
    if row is None:
        raise DocumentError("Document not found")
    return document_payload(row)


def read_document(db: sqlite3.Connection, document_id: int, store: DocumentStore) -> tuple[dict, bytes]:
    document = get_document(db, document_id)
    if document["storage_status"] != "STORED":
        raise DocumentError("Document is not available for normal viewing")
    if document["provider_name"] != store.provider_name:
        raise DocumentProviderError("The document's storage provider is not active")
    data = store.retrieve(document["provider_resource_id"])
    if hashlib.sha256(data).hexdigest() != document["sha256"]:
        raise DocumentIntegrityError("Stored document failed SHA-256 verification")
    return document, data


def verify_document(db: sqlite3.Connection, document_id: int, payload: Mapping, store: DocumentStore) -> dict:
    request_id = str(payload.get("request_id") or "").strip()
    if not request_id:
        raise DocumentError("request_id is required")
    prior = db.execute("SELECT 1 FROM acquisition_document_events WHERE request_id=?", (request_id,)).fetchone()
    document = get_document(db, document_id)
    if prior:
        return {"document": document, "idempotent_replay": True}
    if document["storage_status"] != "STORED":
        raise DocumentError("Only stored documents can be verified")
    now = utcnow()
    try:
        result = store.verify(document["provider_resource_id"], document["sha256"])
        status, event_type, reason = "VERIFIED", "DOCUMENT_INTEGRITY_VERIFIED", ""
    except DocumentIntegrityError as exc:
        result = {"verified": False}
        status, event_type, reason = "FAILED", "DOCUMENT_INTEGRITY_FAILED", str(exc)
    db.execute("UPDATE acquisition_documents SET integrity_status=?,last_verified_at=?,updated_at=? WHERE id=?",
               (status, now, now, document_id))
    _event(db, int(document["acquisition_id"]), document_id, request_id, event_type,
           "SHA256_MISMATCH" if status == "FAILED" else "", reason, result)
    return {"document": get_document(db, document_id), "verification": result, "idempotent_replay": False}


def tombstone_document(db: sqlite3.Connection, document_id: int, payload: Mapping, store: DocumentStore) -> dict:
    request_id = str(payload.get("request_id") or "").strip()
    reason = str(payload.get("reason_code") or "OPERATOR_REMOVED").strip().upper()[:80]
    notes = str(payload.get("notes") or "").strip()[:1000]
    if not request_id:
        raise DocumentError("request_id is required")
    prior = db.execute("SELECT 1 FROM acquisition_document_events WHERE request_id=?", (request_id,)).fetchone()
    document = get_document(db, document_id)
    if prior or document["storage_status"] == "TOMBSTONED":
        return {"document": document, "idempotent_replay": True}
    acquisition = _acquisition(db, int(document["acquisition_id"]))
    _check_revision(acquisition, payload.get("expected_revision"))
    preserve = acquisition["state"] not in ("ACQUISITION_INCOMPLETE", "RECONCILIATION_REQUIRED")
    if document["storage_status"] == "STORED" and document["provider_resource_id"]:
        store.tombstone(document["provider_resource_id"], preserve)
    now = utcnow()
    db.execute(
        """UPDATE acquisition_documents SET storage_status='TOMBSTONED',integrity_status='NOT_AVAILABLE',
                  tombstoned_at=?,tombstone_reason=?,updated_at=? WHERE id=?""",
        (now, reason, now, document_id),
    )
    _event(db, int(document["acquisition_id"]), document_id, request_id, "DOCUMENT_TOMBSTONED",
           reason, notes, {"content_preserved": preserve, "acquisition_state": acquisition["state"]})
    _increment_revision(db, int(document["acquisition_id"]))
    return {"document": get_document(db, document_id), "idempotent_replay": False, "content_preserved": preserve}


def retry_document(db: sqlite3.Connection, document_id: int, payload: Mapping, store: DocumentStore) -> dict:
    failed = get_document(db, document_id)
    if failed["storage_status"] != "FAILED":
        raise DocumentError("Only failed document uploads can be retried")
    retry_payload = dict(payload)
    retry_payload.setdefault("original_filename", failed["original_filename"])
    retry_payload.setdefault("declared_mime_type", failed["declared_mime_type"])
    retry_payload.setdefault("document_role", failed["document_role"])
    retry_payload.setdefault("capture_method", failed["capture_method"])
    result = upload_document(db, int(failed["acquisition_id"]), retry_payload, store)
    if not result.get("upload_failed") and not result.get("duplicate") and not result.get("idempotent_replay"):
        new_id = int(result["document"]["id"])
        db.execute("UPDATE acquisition_documents SET replaced_by_document_id=?,updated_at=? WHERE id=?",
                   (new_id, utcnow(), document_id))
        _event(db, int(failed["acquisition_id"]), new_id, f"{payload['request_id']}:retry-link",
               "DOCUMENT_RETRIED", payload={"replaces_document_id": document_id})
    return result
