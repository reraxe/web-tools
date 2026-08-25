import base64
import io
import json
import os
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import app
from dex_documents import (
    LocalFilesystemDocumentStore,
    document_summary,
    provider_contract,
    tombstone_document,
    upload_document,
    validate_document,
    verify_document,
)
from dex_inbound import create_acquisition
from dex_migrations import DEFAULT_MIGRATIONS, MigrationError, apply_migrations
from tests.test_phase5_sealed import base_schema


def image_bytes(fmt="PNG"):
    output = io.BytesIO()
    Image.new("RGB", (12, 8), (220, 40, 40)).save(output, format=fmt)
    return output.getvalue()


def pdf_bytes():
    return b"%PDF-1.4\n1 0 obj<</Type /Catalog /Pages 2 0 R>>endobj\n2 0 obj<</Type /Pages /Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type /Page /Parent 2 0 R>>endobj\n%%EOF\n"


class Phase4MigrationTest(unittest.TestCase):
    def test_additive_metadata_only_migration_preserves_existing_facts(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        base_schema(db)
        apply_migrations(db, DEFAULT_MIGRATIONS[:9])
        db.execute("INSERT INTO batches (id,batch_code,total_cost) VALUES (1,'P3-PRESERVED',25.00)")
        db.execute("""INSERT INTO acquisitions
            (acquisition_uuid,acquisition_code,creation_request_id,created_at,updated_at)
            VALUES ('ACQ-PRESERVED','ACQ-PRESERVED','PRESERVE','2026-08-15','2026-08-15')""")
        before = tuple(db.execute("SELECT id,batch_code,total_cost FROM batches").fetchone())
        self.assertEqual(apply_migrations(db), ("0010_v22_phase4_source_documents", "0011_v22_phase5_receipt_intelligence", "0012_v22_prephase_ux_safety_hotfix", "0013_v22_phase6_downstream_intake_bridge", "0014_v22_phase7_sam_recognition", "0015_v22_rc3_hf1_mixed_purchase_reconciliation", "0016_v23_inventory_intelligence_phase1_receipt_semantics", "0017_v24_sam_phase1_family_printing", "0018_v24_jarvis_economics_sam_phase2", "0019_v24_sam_multi_evidence_operator_trial_v1a"))
        self.assertEqual(tuple(db.execute("SELECT id,batch_code,total_cost FROM batches").fetchone()), before)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM acquisition_documents").fetchone()[0], 0)
        self.assertNotIn("BLOB", " ".join(row[0] or "" for row in db.execute("SELECT sql FROM sqlite_master WHERE name IN ('acquisition_documents','acquisition_document_events')")))
        self.assertEqual(apply_migrations(db), ())
        db.close()

    def test_failed_migration_rolls_back_tables_and_ledger(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        base_schema(db)
        apply_migrations(db, DEFAULT_MIGRATIONS[:9])
        db.execute("CREATE TABLE acquisition_documents (id INTEGER)")
        db.commit()
        with self.assertRaises(MigrationError):
            apply_migrations(db)
        self.assertNotIn("acquisition_document_events", {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")})
        self.assertIsNone(db.execute("SELECT 1 FROM schema_migrations WHERE migration_id='0010_v22_phase4_source_documents'").fetchone())
        db.close()


class Phase4DocumentServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db_path = self.root / "dex.db"
        with patch.object(app, "DB_PATH", self.db_path), patch.object(app, "DATA_DIR", self.root), patch.object(app, "IMAGE_DIR", self.root / "images"), patch.object(app, "INBOUND_DIR", self.root / "inbound"), patch.object(app, "SOURCE_DB_DIR", self.root / "source"):
            app.init_db()
        self.db = sqlite3.connect(self.db_path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.store = LocalFilesystemDocumentStore(self.root / "private-documents")
        created = create_acquisition(self.db, {"request_id": "DOC-ACQ"})
        self.acquisition_id = created["acquisition"]["id"]
        self.revision = created["acquisition"]["revision"]

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def payload(self, request_id, data, name, mime, **extra):
        return {"request_id": request_id, "expected_revision": self.revision, "original_filename": name,
                "declared_mime_type": mime, "data_base64": base64.b64encode(data).decode(), **extra}

    def upload(self, request_id, data, name, mime, **extra):
        result = upload_document(self.db, self.acquisition_id, self.payload(request_id, data, name, mime, **extra), self.store)
        self.revision = self.db.execute("SELECT revision FROM acquisitions WHERE id=?", (self.acquisition_id,)).fetchone()[0]
        return result

    def test_jpg_png_pdf_multiple_hashes_private_storage_and_no_downstream_facts(self):
        inputs = [(image_bytes("JPEG"), "camera.jpg", "image/jpeg", "CAMERA"),
                  (image_bytes("PNG"), "screenshot.png", "image/png", "SCREENSHOT"),
                  (pdf_bytes(), "invoice.pdf", "application/pdf", "PDF_UPLOAD")]
        for index, (data, name, mime, capture) in enumerate(inputs):
            result = self.upload(f"DOC-{index}", data, name, mime, capture_method=capture)
            self.assertEqual(result["document"]["storage_status"], "STORED")
            self.assertEqual(result["document"]["integrity_status"], "VERIFIED")
            self.assertEqual(len(result["document"]["sha256"]), 64)
        summary = document_summary(self.db, self.acquisition_id)
        self.assertEqual(summary["active_count"], 3)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM batches").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM cards").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sealed_units").fetchone()[0], 0)
        self.assertFalse(any("data_base64" in (event[0] or "") for event in self.db.execute("SELECT payload FROM acquisition_document_events")))

    def test_mime_mismatch_malformed_and_oversize_are_retryable_failures(self):
        mismatch = self.upload("BAD-MIME", image_bytes("PNG"), "receipt.jpg", "image/jpeg")
        self.assertTrue(mismatch["upload_failed"])
        malformed = self.upload("BAD-PDF", b"%PDF-1.4 broken", "receipt.pdf", "application/pdf")
        self.assertTrue(malformed["upload_failed"])
        with patch.dict(os.environ, {"DEX_DOCUMENT_MAX_BYTES": "8"}):
            oversize = self.upload("TOO-LARGE", image_bytes("PNG"), "large.png", "image/png")
        self.assertTrue(oversize["upload_failed"])
        self.assertEqual(document_summary(self.db, self.acquisition_id)["failed_count"], 3)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM acquisition_document_events WHERE event_type='DOCUMENT_STORAGE_FAILED'").fetchone()[0], 3)

    def test_safe_names_path_traversal_duplicate_and_request_replay(self):
        data = image_bytes("PNG")
        first = self.upload("SAFE-1", data, "../../secret receipt.png", "image/png")
        self.assertNotIn("/", first["document"]["safe_filename"])
        replay = upload_document(self.db, self.acquisition_id, self.payload("SAFE-1", data, "other.png", "image/png"), self.store)
        self.assertTrue(replay["idempotent_replay"])
        duplicate = upload_document(self.db, self.acquisition_id, self.payload("SAFE-2", data, "copy.png", "image/png"), self.store)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM acquisition_documents").fetchone()[0], 1)

    def test_integrity_failure_is_audited(self):
        result = self.upload("INTEGRITY", image_bytes("PNG"), "receipt.png", "image/png")
        resource = result["document"]["provider_resource_id"]
        path = self.store.root / resource
        path.write_bytes(b"tampered")
        verified = verify_document(self.db, result["document"]["id"], {"request_id": "VERIFY-TAMPER"}, self.store)
        self.assertEqual(verified["document"]["integrity_status"], "FAILED")
        self.assertEqual(self.db.execute("SELECT event_type FROM acquisition_document_events WHERE request_id='VERIFY-TAMPER'").fetchone()[0], "DOCUMENT_INTEGRITY_FAILED")

    def test_draft_remove_deletes_artifact_but_confirmed_remove_preserves_it(self):
        draft = self.upload("DRAFT-REMOVE", image_bytes("PNG"), "draft.png", "image/png")["document"]
        draft_path = self.store.root / draft["provider_resource_id"]
        result = tombstone_document(self.db, draft["id"], {"request_id": "REMOVE-DRAFT", "expected_revision": self.revision}, self.store)
        self.revision = self.db.execute("SELECT revision FROM acquisitions WHERE id=?", (self.acquisition_id,)).fetchone()[0]
        self.assertFalse(draft_path.exists())
        self.assertFalse(result["content_preserved"])
        confirmed = self.upload("CONFIRMED-REMOVE", image_bytes("JPEG"), "confirmed.jpg", "image/jpeg")["document"]
        self.db.execute("UPDATE acquisitions SET state='READY_FOR_INTAKE' WHERE id=?", (self.acquisition_id,))
        result = tombstone_document(self.db, confirmed["id"], {"request_id": "REMOVE-CONFIRMED", "expected_revision": self.revision}, self.store)
        self.assertTrue(result["content_preserved"])
        self.assertTrue(any((self.store.tombstone_root / confirmed["document_uuid"]).iterdir()))

    def test_provider_contract_is_private_and_drive_boundary_unconfigured(self):
        contract = provider_contract(self.store)
        self.assertTrue(contract["active"]["private"])
        self.assertFalse(contract["public_links"])
        self.assertFalse(contract["extraction_enabled"])
        drive = next(item for item in contract["available_providers"] if item["provider"] == "GOOGLE_DRIVE_COMPATIBLE")
        self.assertFalse(drive["configured"])


class Phase4DocumentApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.store = LocalFilesystemDocumentStore(root / "private-documents")
        self.patches = (patch.object(app, "DB_PATH", root / "dex.db"), patch.object(app, "DATA_DIR", root),
                        patch.object(app, "IMAGE_DIR", root / "images"), patch.object(app, "INBOUND_DIR", root / "inbound"),
                        patch.object(app, "SOURCE_DB_DIR", root / "source"), patch.object(app, "DOCUMENT_STORE", self.store))
        for item in self.patches: item.start()
        app.init_db()
        self.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.DexHandler)
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.thread.join(timeout=3); self.server.server_close()
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()

    def request(self, path, method="GET", body=None, raw=False):
        request = urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None,
                                         method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.read() if raw else json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_upload_list_metadata_view_tombstone_and_refresh_contract(self):
        _, created = self.request("/api/acquisitions", "POST", {"request_id": "API-DOC-ACQ"})
        acquisition = created["acquisition"]
        png = image_bytes("PNG")
        status, uploaded = self.request(f"/api/acquisitions/{acquisition['id']}/documents", "POST", {
            "request_id": "API-DOC-UPLOAD", "expected_revision": acquisition["revision"], "original_filename": "receipt.png",
            "declared_mime_type": "image/png", "data_base64": base64.b64encode(png).decode(), "capture_method": "CAMERA"})
        self.assertEqual(status, 201)
        document = uploaded["document"]
        self.assertEqual(uploaded["acquisition_payload"]["source_documents"]["active_count"], 1)
        self.assertEqual(self.request(f"/api/acquisitions/{acquisition['id']}/documents")[1]["documents"][0]["id"], document["id"])
        self.assertEqual(self.request(f"/api/acquisition-documents/{document['id']}")[1]["document"]["sha256"], document["sha256"])
        content_status, body = self.request(f"/api/acquisition-documents/{document['id']}/content", raw=True)
        self.assertEqual((content_status, body), (200, png))
        revision = uploaded["acquisition_payload"]["acquisition"]["revision"]
        status, removed = self.request(f"/api/acquisition-documents/{document['id']}/tombstone", "POST", {
            "request_id": "API-DOC-REMOVE", "expected_revision": revision, "reason_code": "OPERATOR_REMOVED"})
        self.assertEqual(status, 200)
        self.assertEqual(removed["document"]["storage_status"], "TOMBSTONED")
        self.assertEqual(self.request(f"/api/acquisitions/{acquisition['id']}")[1]["source_documents"]["tombstone_count"], 1)
        self.assertEqual(self.request("/api/document-providers/status")[1]["phase"], "INBOUND_2_PHASE_4_SOURCE_DOCUMENTS")


if __name__ == "__main__":
    unittest.main()
