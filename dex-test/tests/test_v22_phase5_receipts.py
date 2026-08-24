import base64
import io
import json
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from reportlab.pdfgen import canvas

import app
from dex_catalog import add_identifier_mapping, create_catalog_product
from dex_documents import LocalFilesystemDocumentStore, upload_document
from dex_inbound import add_acquisition_line, acquisition_payload, autosave_acquisition, autosave_acquisition_line, confirm_acquisition
from dex_migrations import DEFAULT_MIGRATIONS, MigrationError, apply_migrations
from dex_receipts import (
    LocalPdfTextReceiptExtractor,
    apply_proposed_facts,
    candidate_disposition,
    classify_receipt_line,
    extraction_provider_contract,
    generate_allocation_proposal,
    queue_extraction,
    receipt_intelligence_payload,
    retry_extraction,
)
from tests.test_phase5_sealed import base_schema


def receipt_pdf(lines):
    output = io.BytesIO()
    page = canvas.Canvas(output, pagesize=(612, 792), pageCompression=0)
    y = 760
    for line in lines:
        page.drawString(40, y, line)
        y -= 18
    page.save()
    return output.getvalue()


def png_bytes():
    output = io.BytesIO()
    Image.new("RGB", (100, 60), "white").save(output, format="PNG")
    return output.getvalue()


def clean_receipt(merchant="Phase Five Shop", total="113.00", item="OP16 Booster Box", quantity=2, unit="50.00"):
    return receipt_pdf([
        f"Merchant: {merchant}", "Date: 2026-08-15", "Order #: RCPT-5001", "Currency: USD",
        f"ITEM | {item} | QTY {quantity} | UNIT {unit} | TOTAL 100.00",
        "Subtotal: 100.00", "Tax: 8.00", "Shipping: 5.00", f"Total: {total}",
    ])


class Phase5ReceiptMigrationTest(unittest.TestCase):
    def test_migration_is_additive_metadata_only_and_runs_once(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        base_schema(db)
        apply_migrations(db, DEFAULT_MIGRATIONS[:10])
        db.execute("INSERT INTO batches (id,batch_code,total_cost) VALUES (1,'P4-PRESERVED',50.00)")
        before = tuple(db.execute("SELECT id,batch_code,total_cost FROM batches").fetchone())
        self.assertEqual(apply_migrations(db), ("0011_v22_phase5_receipt_intelligence", "0012_v22_prephase_ux_safety_hotfix", "0013_v22_phase6_downstream_intake_bridge", "0014_v22_phase7_sam_recognition", "0015_v22_rc3_hf1_mixed_purchase_reconciliation", "0016_v23_inventory_intelligence_phase1_receipt_semantics", "0017_v24_sam_phase1_family_printing", "0018_v24_jarvis_economics_sam_phase2"))
        self.assertEqual(tuple(db.execute("SELECT id,batch_code,total_cost FROM batches").fetchone()), before)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM receipt_extraction_jobs").fetchone()[0], 0)
        self.assertEqual(apply_migrations(db), ())
        db.close()

    def test_forced_failure_rolls_back_schema_and_marker(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        base_schema(db)
        apply_migrations(db, DEFAULT_MIGRATIONS[:10])
        db.execute("CREATE TABLE receipt_extraction_jobs (id INTEGER)")
        db.commit()
        with self.assertRaises(MigrationError):
            apply_migrations(db)
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn("receipt_candidate_facts", tables)
        self.assertIsNone(db.execute("SELECT 1 FROM schema_migrations WHERE migration_id='0011_v22_phase5_receipt_intelligence'").fetchone())
        db.close()


class ReceiptFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db_path = self.root / "dex.db"
        with patch.object(app, "DB_PATH", self.db_path), patch.object(app, "DATA_DIR", self.root), patch.object(app, "IMAGE_DIR", self.root / "images"), patch.object(app, "INBOUND_DIR", self.root / "inbound"), patch.object(app, "SOURCE_DB_DIR", self.root / "source"):
            app.init_db()
        self.db = sqlite3.connect(self.db_path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.store = LocalFilesystemDocumentStore(self.root / "documents")
        self.extractor = LocalPdfTextReceiptExtractor()

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def acquisition(self, request="ACQ-RCPT", final=None, merchant="", source="DOMESTIC"):
        payload = {"request_id": request, "source_scope": source, "payment_method": "CREDIT_DEBIT_CARD"}
        if merchant: payload["merchant_name"] = merchant
        if final is not None: payload["final_usd_paid_cents"] = final
        return __import__("dex_inbound").create_acquisition(self.db, payload)

    def add_line(self, result, name, quantity=2, catalog_product_id=None):
        result = add_acquisition_line(self.db, result["acquisition"]["id"], {
            "request_id": f"LINE-{result['acquisition']['id']}-{name}-{result['acquisition']['revision']}", "expected_revision": result["acquisition"]["revision"], "product_class": "SEALED_PRODUCT",
        })
        line = next(item for item in result["lines"] if not item["canceled_at"] and not item["product_name"])
        return autosave_acquisition_line(self.db, line["id"], {
            "request_id": f"LINE-FACTS-{line['id']}", "expected_revision": result["acquisition"]["revision"],
            "game": "One Piece", "set_code": name.split()[0], "product_name": name, "quantity": quantity,
            "quantity_certainty": "KNOWN", "catalog_product_id": catalog_product_id,
        })

    def attach(self, result, data, name="receipt.pdf", mime="application/pdf", request="DOC-RCPT"):
        uploaded = upload_document(self.db, result["acquisition"]["id"], {
            "request_id": request, "expected_revision": result["acquisition"]["revision"], "original_filename": name,
            "declared_mime_type": mime, "data_base64": base64.b64encode(data).decode(), "document_role": "RECEIPT",
        }, self.store)
        current = acquisition_payload(self.db, result["acquisition"]["id"])
        return current, uploaded["document"]

    def extract(self, result, document, request="EXTRACT-RCPT"):
        job = queue_extraction(self.db, document["id"], {
            "request_id": request, "expected_revision": result["acquisition"]["revision"], "auto_apply": True,
        }, self.store, self.extractor)
        return acquisition_payload(self.db, result["acquisition"]["id"]), job


class ReceiptExtractionServiceTest(ReceiptFixture):
    def test_happy_path_candidates_auto_populate_as_proposed_and_keep_missing_unknown(self):
        result = self.add_line(self.acquisition(), "OP16 Booster Box")
        result, document = self.attach(result, clean_receipt())
        result, job = self.extract(result, document)
        acquisition = result["acquisition"]
        self.assertEqual(job["status"], "COMPLETED")
        self.assertEqual(acquisition["merchant_name"], "Phase Five Shop")
        self.assertEqual(acquisition["purchased_on"], "2026-08-15")
        self.assertEqual(acquisition["order_reference"], "RCPT-5001")
        self.assertEqual(acquisition["purchase_subtotal_cents"], 10000)
        self.assertEqual(acquisition["acquisition_tax_cents"], 800)
        self.assertEqual(acquisition["inbound_shipping_cents"], 500)
        self.assertEqual(acquisition["final_usd_paid_cents"], 11300)
        self.assertIsNone(acquisition["acquisition_fees_cents"])
        self.assertFalse(acquisition["financial_facts_confirmed"])
        proposed = {item["field_name"] for item in result["receipt_intelligence"]["proposed_fields"]}
        self.assertIn("merchant_name", proposed)
        self.assertIn("final_usd_paid_cents", proposed)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM batches").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM cards").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sealed_units").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM rip_sessions").fetchone()[0], 0)
        confirmed = confirm_acquisition(self.db, acquisition["id"], {
            "request_id": "CONFIRM-RECEIPT-SINGLE", "expected_revision": acquisition["revision"],
            "confirm_authoritative_financial_facts": True, "confirm_reconciliation": True,
        })
        self.assertEqual(confirmed["lines"][0]["assigned_landed_cost_cents"], 11300)
        self.assertEqual(confirmed["lines"][0]["allocation_method"], "SINGLE_LINE_100_PERCENT")

    def test_all_supported_purchase_components_are_normalized_without_invention(self):
        result = self.add_line(self.acquisition(), "OP16 Booster Box")
        pdf = receipt_pdf([
            "Merchant: Complete Components", "Date: 2026-08-15", "Order #: ALL-FACTS", "Currency: USD",
            "ITEM | OP16 Booster Box | QTY 2 | UNIT 50.00 | TOTAL 100.00", "Subtotal: 100.00",
            "Tax: 8.00", "Shipping: 5.00", "Fees: 2.00", "Duties: 3.00", "Brokerage: 1.00",
            "Discounts: 4.00", "Total: 115.00",
        ])
        result, document = self.attach(result, pdf)
        result, _ = self.extract(result, document)
        expected = {
            "purchase_subtotal_cents": 10000, "acquisition_tax_cents": 800, "inbound_shipping_cents": 500,
            "acquisition_fees_cents": 200, "import_duties_cents": 300, "brokerage_cents": 100,
            "acquisition_discount_cents": 400, "final_usd_paid_cents": 11500,
        }
        self.assertEqual({field: result["acquisition"][field] for field in expected}, expected)
        self.assertIsNone(result["acquisition"].get("unconfigured_receipt_value"))

    def test_manual_conflict_is_not_overwritten_and_operator_edit_preserves_candidate(self):
        result = self.add_line(self.acquisition(final=9999, merchant="Manual Merchant"), "OP16 Booster Box")
        result, document = self.attach(result, clean_receipt())
        result, _ = self.extract(result, document)
        self.assertEqual(result["acquisition"]["merchant_name"], "Manual Merchant")
        self.assertEqual(result["acquisition"]["final_usd_paid_cents"], 9999)
        self.assertIn("RECEIPT_FIELD_CONFLICT", {item["code"] for item in result["receipt_intelligence"]["warnings"]})

        fresh = self.add_line(self.acquisition("ACQ-EDIT"), "OP16 Booster Box")
        fresh, doc = self.attach(fresh, clean_receipt(), request="DOC-EDIT")
        fresh, _ = self.extract(fresh, doc, "EXTRACT-EDIT")
        fresh = autosave_acquisition(self.db, fresh["acquisition"]["id"], {
            "request_id": "OPERATOR-EDIT", "expected_revision": fresh["acquisition"]["revision"], "merchant_name": "Corrected Merchant",
        })
        provenance = self.db.execute("SELECT status,operator_value FROM acquisition_field_provenance WHERE acquisition_id=? AND field_name='merchant_name'", (fresh["acquisition"]["id"],)).fetchone()
        self.assertEqual(tuple(provenance), ("OPERATOR_REPLACED", "Corrected Merchant"))
        candidate = self.db.execute("SELECT normalized_value FROM receipt_candidate_facts WHERE acquisition_id=? AND field_name='merchant_name'", (fresh["acquisition"]["id"],)).fetchone()[0]
        self.assertEqual(candidate, "Phase Five Shop")

    def test_image_failure_retry_and_provider_privacy_leave_manual_path_available(self):
        result = self.add_line(self.acquisition(), "OP16 Booster Box")
        result, document = self.attach(result, png_bytes(), "camera.png", "image/png", "DOC-IMAGE")
        with patch("dex_receipt_ocr.find_tesseract_command", return_value=""):
            result, job = self.extract(result, document, "EXTRACT-IMAGE")
        self.assertEqual(job["status"], "FAILED")
        self.assertTrue(result["receipt_intelligence"]["manual_entry_available"])
        self.assertFalse(job["retry_plausible"])
        with self.assertRaisesRegex(ValueError, "Retry is unavailable"):
            retry_extraction(self.db, job["job_uuid"], {
                "request_id": "EXTRACT-IMAGE-RETRY", "expected_revision": result["acquisition"]["revision"],
            }, self.store, self.extractor)
        with patch("dex_receipt_ocr.find_tesseract_command", return_value=""):
            contract = extraction_provider_contract(self.extractor)
        self.assertFalse(contract["external_transmission_enabled"])
        self.assertEqual(contract["active"]["operational_formats"], ["application/pdf"])

    def test_low_confidence_critical_candidate_needs_attention_and_stays_non_authoritative(self):
        class LowConfidenceExtractor:
            provider_name = "TEST_LOW_CONFIDENCE"
            provider_version = "fixture-v1"
            def extract(self, document, data):
                return {"candidates": [{
                    "field_name": "final_usd_paid_cents", "normalized_value": "11300", "value_type": "CENTS",
                    "confidence": 0.55, "confidence_band": "LOW", "source_page": 1, "source_location": "unclear total",
                }], "lines": []}

        result = self.add_line(self.acquisition(), "OP16 Booster Box")
        result, document = self.attach(result, clean_receipt())
        queue_extraction(self.db, document["id"], {
            "request_id": "EXTRACT-LOW", "expected_revision": result["acquisition"]["revision"], "auto_apply": True,
        }, self.store, LowConfidenceExtractor())
        result = acquisition_payload(self.db, result["acquisition"]["id"])
        self.assertIsNone(result["acquisition"]["final_usd_paid_cents"])
        self.assertIn("LOW_CONFIDENCE_CRITICAL_VALUE", {item["code"] for item in result["receipt_intelligence"]["warnings"]})
        self.assertEqual(result["attention"]["decision_level"], "NEEDS_ATTENTION")

    def test_multiple_documents_conflict_and_candidate_rejection_is_audited(self):
        result = self.add_line(self.acquisition(), "OP16 Booster Box")
        result, first = self.attach(result, clean_receipt(total="113.00"), request="DOC-FIRST")
        result, _ = self.extract(result, first, "EXTRACT-FIRST")
        result, second = self.attach(result, clean_receipt(total="120.00"), name="second.pdf", request="DOC-SECOND")
        result, _ = self.extract(result, second, "EXTRACT-SECOND")
        self.assertTrue(any(item["field_name"] == "final_usd_paid_cents" for item in result["receipt_intelligence"]["conflicts"]))
        second_candidate = self.db.execute("SELECT c.id FROM receipt_candidate_facts c JOIN receipt_extraction_jobs j ON j.id=c.job_id WHERE j.document_id=? AND c.field_name='final_usd_paid_cents'", (second["id"],)).fetchone()[0]
        result = candidate_disposition(self.db, second_candidate, {
            "request_id": "REJECT-CONFLICT", "expected_revision": result["acquisition"]["revision"], "disposition": "REJECTED", "reason": "Wrong duplicate receipt",
        })
        self.assertFalse(any(item["field_name"] == "final_usd_paid_cents" for item in result["conflicts"]))

    def test_rejecting_an_auto_populated_candidate_clears_only_its_draft_value(self):
        result = self.add_line(self.acquisition(), "OP16 Booster Box")
        result, document = self.attach(result, clean_receipt())
        result, _ = self.extract(result, document)
        candidate = self.db.execute(
            "SELECT id FROM receipt_candidate_facts WHERE acquisition_id=? AND field_name='inbound_shipping_cents'",
            (result["acquisition"]["id"],),
        ).fetchone()[0]
        result = candidate_disposition(self.db, candidate, {
            "request_id": "REJECT-AUTO-SHIPPING", "expected_revision": result["acquisition"]["revision"],
            "disposition": "REJECTED", "reason": "Receipt shipping line was not part of this acquisition",
        })
        refreshed = acquisition_payload(self.db, result["jobs"][0]["acquisition_id"])
        self.assertIsNone(refreshed["acquisition"]["inbound_shipping_cents"])
        self.assertEqual(refreshed["acquisition"]["purchase_subtotal_cents"], 10000)
        provenance = self.db.execute("SELECT status FROM acquisition_field_provenance WHERE candidate_id=?", (candidate,)).fetchone()[0]
        self.assertEqual(provenance, "REJECTED")

    def test_exact_identifier_exact_name_and_fuzzy_matching_contract(self):
        product = create_catalog_product(self.db, {"request_id": "PROD-UPC", "game": "One Piece", "display_name": "OP16 Booster Box", "set_code": "OP16", "product_class": "SEALED_PRODUCT", "product_subtype": "Booster Box"})
        add_identifier_mapping(self.db, product["id"], {"request_id": "MAP-UPC", "raw_identifier": "012345678905", "provenance": "OPERATOR_CONFIRMED"})
        result = self.add_line(self.acquisition(), "OP16 Booster Box")
        line = next(item for item in result["lines"] if not item["canceled_at"])
        self.db.execute("UPDATE acquisition_lines SET catalog_product_id=? WHERE id=?", (product["id"], line["id"]))
        pdf = receipt_pdf(["Merchant: Match Shop", "Date: 2026-08-15", "Order #: MATCH-1", "Currency: USD",
                           "ITEM | OP16 Booster Box | QTY 2 | UNIT 50.00 | TOTAL 100.00 | UPC 012345678905",
                           "Subtotal: 100.00", "Total: 100.00"])
        result, document = self.attach(result, pdf)
        result, _ = self.extract(result, document)
        match = result["receipt_intelligence"]["receipt_lines"][0]["best_match"]
        self.assertEqual((match["match_method"], match["status"], match["authoritative_identity"]), ("EXACT_IDENTIFIER", "ACCEPTED", 1))

        fuzzy = self.add_line(self.acquisition("ACQ-FUZZY"), "OP16 Premium Booster Collection")
        fuzzy, doc = self.attach(fuzzy, receipt_pdf(["Merchant: Fuzzy", "Date: 2026-08-15", "ITEM | OP16 Premium Booster Collectn | QTY 2 | UNIT 50.00 | TOTAL 100.00", "Subtotal: 100.00", "Total: 100.00"]), request="DOC-FUZZY")
        fuzzy, _ = self.extract(fuzzy, doc, "EXTRACT-FUZZY")
        fuzzy_match = fuzzy["receipt_intelligence"]["receipt_lines"][0]["best_match"]
        self.assertEqual(fuzzy_match["match_method"], "FUZZY_TEXT")
        self.assertEqual(fuzzy_match["status"], "PROPOSED")
        self.assertFalse(fuzzy_match["authoritative_identity"])

    def test_unmatched_line_classification_and_personal_exclusion_block_allocation(self):
        result = self.add_line(self.acquisition(), "OP16 Booster Box")
        result = self.add_line(result, "ST27 Starter Deck", quantity=1)
        pdf = receipt_pdf(["Merchant: Mixed Shop", "Date: 2026-08-15", "Currency: USD",
                           "ITEM | OP16 Booster Box | QTY 2 | UNIT 50.00 | TOTAL 100.00",
                           "ITEM | Birthday Gift | QTY 1 | UNIT 20.00 | TOTAL 20.00",
                           "Subtotal: 120.00", "Tax: 8.00", "Total: 128.00"])
        result, document = self.attach(result, pdf)
        result, _ = self.extract(result, document)
        unmatched = next(item for item in result["receipt_intelligence"]["receipt_lines"] if item["description"] == "Birthday Gift")
        acquisition_id = result["acquisition"]["id"]
        result = classify_receipt_line(self.db, unmatched["id"], {
            "request_id": "CLASSIFY-PERSONAL", "expected_revision": result["acquisition"]["revision"], "classification": "PERSONAL_NONBUSINESS", "notes": "Not business inventory",
        })
        self.assertEqual(result["allocation_policy"]["status"], "POLICY_REQUIRED")
        with self.assertRaisesRegex(ValueError, "approved accounting policy"):
            generate_allocation_proposal(self.db, acquisition_id, {
                "request_id": "ALLOC-PERSONAL", "expected_revision": self.db.execute("SELECT revision FROM acquisitions WHERE id=?", (acquisition_id,)).fetchone()[0],
            })

    def test_multi_line_proportional_allocation_exact_cents_and_confirmation(self):
        result = self.add_line(self.acquisition(), "OP16 Booster Box", quantity=1)
        result = self.add_line(result, "ST27 Starter Deck", quantity=1)
        pdf = receipt_pdf(["Merchant: Multi Shop", "Date: 2026-08-15", "Order #: MULTI-1", "Currency: USD",
                           "ITEM | OP16 Booster Box | QTY 1 | UNIT 100.00 | TOTAL 100.00",
                           "ITEM | ST27 Starter Deck | QTY 1 | UNIT 50.00 | TOTAL 50.00",
                           "Subtotal: 150.00", "Tax: 10.00", "Shipping: 1.00", "Total: 161.00"])
        result, document = self.attach(result, pdf)
        result, _ = self.extract(result, document)
        proposal = result["receipt_intelligence"]["allocation_proposal"]
        self.assertEqual(proposal["method"], "RECEIPT_VALUE_PROPORTIONAL")
        self.assertEqual(proposal["difference_cents"], 0)
        allocations = [item["landed_cost_cents"] for item in proposal["allocations"]]
        self.assertEqual(sum(allocations), 16100)
        self.assertEqual(allocations, [10734, 5366])
        self.assertTrue(result["reconciliation"]["allocation_reconciled"])
        self.assertTrue(result["readiness"]["ready_to_confirm"])
        confirmed = confirm_acquisition(self.db, result["acquisition"]["id"], {
            "request_id": "CONFIRM-MULTI", "expected_revision": result["acquisition"]["revision"],
            "confirm_authoritative_financial_facts": True, "confirm_reconciliation": True,
        })
        self.assertEqual(confirmed["acquisition"]["state"], "READY_FOR_INTAKE")
        self.assertTrue(all(line["allocation_status"] == "CONFIRMED" for line in confirmed["lines"] if not line["canceled_at"]))

    def test_material_severe_zero_and_international_controls_remain(self):
        result = self.add_line(self.acquisition(), "OP16 Booster Box")
        result, document = self.attach(result, clean_receipt(total="10.00"))
        result, _ = self.extract(result, document)
        self.assertTrue(result["reconciliation"]["extreme"])
        self.assertEqual(result["attention"]["decision_level"], "NEEDS_ATTENTION")

        international = self.add_line(self.acquisition("ACQ-INTL", source="INTERNATIONAL"), "OP16 Booster Box")
        pdf = receipt_pdf(["Merchant: Tokyo Shop", "Date: 2026-08-15", "Currency: JPY", "Original Amount: 15000", "ITEM | OP16 Booster Box | QTY 2 | UNIT 7500 | TOTAL 15000", "Total: 15000"])
        international, doc = self.attach(international, pdf, request="DOC-INTL")
        international, _ = self.extract(international, doc, "EXTRACT-INTL")
        self.assertEqual(international["acquisition"]["original_currency"], "JPY")
        self.assertEqual(international["acquisition"]["original_foreign_amount_minor"], 1500000)
        self.assertIsNone(international["acquisition"]["final_usd_paid_cents"])
        self.assertNotIn("exchange_rate", international["receipt_intelligence"])

    def test_realistic_twenty_five_line_receipt_remains_prompt(self):
        result = self.acquisition("ACQ-PERFORMANCE")
        receipt_items = []
        for index in range(1, 26):
            name = f"SET{index:02d} Product {index:02d}"
            result = self.add_line(result, name, quantity=1)
            receipt_items.append(f"ITEM | {name} | QTY 1 | UNIT 1.00 | TOTAL 1.00")
        pdf = receipt_pdf(["Merchant: Performance Shop", "Date: 2026-08-15", "Currency: USD", *receipt_items, "Subtotal: 25.00", "Total: 25.00"])
        result, document = self.attach(result, pdf, request="DOC-PERFORMANCE")
        started = time.perf_counter()
        result, job = self.extract(result, document, "EXTRACT-PERFORMANCE")
        elapsed_ms = (time.perf_counter() - started) * 1000
        self.assertEqual(job["status"], "COMPLETED")
        self.assertEqual(len(result["receipt_intelligence"]["receipt_lines"]), 25)
        self.assertEqual(result["receipt_intelligence"]["allocation_proposal"]["difference_cents"], 0)
        self.assertLess(elapsed_ms, 2500)
        print(f"Phase 5 receipt performance: 25 matched lines in {elapsed_ms:.2f} ms")


class ReceiptExtractionApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.store = LocalFilesystemDocumentStore(root / "private-documents")
        self.extractor = LocalPdfTextReceiptExtractor()
        self.patches = (
            patch.object(app, "DB_PATH", root / "dex.db"), patch.object(app, "DATA_DIR", root),
            patch.object(app, "IMAGE_DIR", root / "images"), patch.object(app, "INBOUND_DIR", root / "inbound"),
            patch.object(app, "SOURCE_DB_DIR", root / "source"), patch.object(app, "DOCUMENT_STORE", self.store),
            patch.object(app, "RECEIPT_EXTRACTOR", self.extractor),
        )
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

    def request(self, path, method="GET", body=None):
        request = urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None,
                                         method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_provider_queue_status_candidates_and_retry_api_contract(self):
        status, created = self.request("/api/acquisitions", "POST", {"request_id": "API-RCPT-ACQ"})
        self.assertEqual(status, 201)
        acquisition = created["acquisition"]
        status, with_line = self.request(f"/api/acquisitions/{acquisition['id']}/lines", "POST", {
            "request_id": "API-RCPT-LINE", "expected_revision": acquisition["revision"], "product_class": "SEALED_PRODUCT",
            "game": "One Piece", "set_code": "OP16", "product_name": "OP16 Booster Box", "quantity": 2,
        })
        self.assertEqual(status, 201)
        pdf = clean_receipt()
        status, uploaded = self.request(f"/api/acquisitions/{acquisition['id']}/documents", "POST", {
            "request_id": "API-RCPT-DOC", "expected_revision": with_line["acquisition"]["revision"],
            "original_filename": "receipt.pdf", "declared_mime_type": "application/pdf",
            "data_base64": base64.b64encode(pdf).decode(), "capture_method": "FILE_UPLOAD",
        })
        self.assertEqual(status, 201)
        document = uploaded["document"]
        revision = uploaded["acquisition_payload"]["acquisition"]["revision"]
        status, extracted = self.request(f"/api/acquisition-documents/{document['id']}/extractions", "POST", {
            "request_id": "API-RCPT-EXTRACT", "expected_revision": revision,
        })
        self.assertEqual(status, 201)
        self.assertEqual(extracted["status"], "COMPLETED")
        self.assertEqual(extracted["acquisition_payload"]["acquisition"]["merchant_name"], "Phase Five Shop")
        self.assertFalse(extracted["acquisition_payload"]["acquisition"]["financial_facts_confirmed"])
        self.assertEqual(self.request(f"/api/receipt-extractions/{extracted['job_uuid']}")[1]["status"], "COMPLETED")
        intelligence = self.request(f"/api/acquisitions/{acquisition['id']}/receipt-intelligence")[1]
        self.assertEqual(intelligence["status"], "READY_TO_REVIEW")
        self.assertGreater(len(intelligence["candidate_groups"]["final_usd_paid_cents"]), 0)
        provider = self.request("/api/receipt-extraction/providers/status")[1]
        self.assertEqual(provider["phase"], "INBOUND_2_PHASE_5_RECEIPT_INTELLIGENCE")
        self.assertFalse(provider["external_transmission_enabled"])


if __name__ == "__main__":
    unittest.main()
