import base64
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from PIL import Image
from dex_documents import LocalFilesystemDocumentStore, tombstone_document, upload_document
from dex_inbound import (
    acquisition_payload,
    add_acquisition_line,
    autosave_acquisition,
    confirm_acquisition,
    confirm_line_allocation,
    create_acquisition,
)
from dex_receipts import (
    LocalPdfTextReceiptExtractor,
    queue_extraction,
    receipt_intelligence_payload,
    retry_extraction,
    select_manual_fallback,
)


def jpeg_bytes():
    output = io.BytesIO()
    Image.new("RGB", (100, 60), "white").save(output, format="JPEG")
    return output.getvalue()


class ManualReceiptFallbackFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db_path = self.root / "hf2.db"
        with (
            patch.object(app, "DB_PATH", self.db_path),
            patch.object(app, "DATA_DIR", self.root),
            patch.object(app, "IMAGE_DIR", self.root / "images"),
            patch.object(app, "INBOUND_DIR", self.root / "inbound"),
            patch.object(app, "SOURCE_DB_DIR", self.root / "source"),
        ):
            app.init_db()
        self.db = sqlite3.connect(self.db_path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.store = LocalFilesystemDocumentStore(self.root / "documents")
        self.extractor = LocalPdfTextReceiptExtractor()

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def mixed_purchase_with_failed_image(self):
        result = create_acquisition(self.db, {
            "request_id": "HF2-CREATE",
            "source_scope": "DOMESTIC",
            "merchant_name": "Mom and Pop Shop",
            "purchased_on": "2026-08-16",
            "payment_method": "CREDIT_DEBIT_CARD",
            "purchase_subtotal_cents": 13616,
            "final_usd_paid_cents": 13417,
            "discrepancy_reason_code": "MERCHANT_TOTAL_CONTROLS",
            "discrepancy_notes": "Merchant credit reduced the component total by $1.99.",
        })
        products = (("OP13", 3000), ("Hobbit", 5000), ("Riftbound", 3000))
        for sequence, (name, cents) in enumerate(products, 1):
            result = add_acquisition_line(self.db, result["acquisition"]["id"], {
                "request_id": f"HF2-LINE-{sequence}",
                "expected_revision": result["acquisition"]["revision"],
                "product_class": "SEALED_PRODUCT",
                "game": "One Piece" if name == "OP13" else name,
                "set_code": name.upper(),
                "product_name": name,
                "quantity": 1,
                "quantity_certainty": "KNOWN",
            })
            result = confirm_line_allocation(self.db, result["lines"][-1]["id"], {
                "request_id": f"HF2-ALLOC-{sequence}",
                "expected_revision": result["acquisition"]["revision"],
                "assigned_landed_cost_cents": cents,
                "allocation_method": "ACTUAL_LINE_COST",
                "confirm_allocation": True,
            })
        uploaded = upload_document(self.db, result["acquisition"]["id"], {
            "request_id": "HF2-JPG",
            "expected_revision": result["acquisition"]["revision"],
            "original_filename": "mom-and-pop-receipt.jpg",
            "declared_mime_type": "image/jpeg",
            "data_base64": base64.b64encode(jpeg_bytes()).decode(),
            "document_role": "RECEIPT",
        }, self.store)
        result = acquisition_payload(self.db, result["acquisition"]["id"])
        with patch("dex_receipt_ocr.find_tesseract_command", return_value=""):
            job = queue_extraction(self.db, uploaded["document"]["id"], {
                "request_id": "HF2-EXTRACT-JPG",
                "expected_revision": result["acquisition"]["revision"],
                "auto_apply": True,
            }, self.store, self.extractor)
        return acquisition_payload(self.db, result["acquisition"]["id"]), uploaded["document"], job


class ManualReceiptFallbackTest(ManualReceiptFallbackFixture):
    def test_failed_jpg_manual_fallback_confirms_exact_mixed_purchase(self):
        result, document, job = self.mixed_purchase_with_failed_image()
        acquisition_id = result["acquisition"]["id"]
        self.assertEqual(job["status"], "FAILED")
        self.assertEqual(job["error_code"], "FORMAT_PROVIDER_UNAVAILABLE")
        self.assertTrue(result["receipt_intelligence"]["manual_fallback_available"])
        self.assertFalse(result["receipt_intelligence"]["manual_fallback_selected"])
        self.assertFalse(result["receipt_intelligence"]["retry_plausible"])
        self.assertIn("RECEIPT_ALLOCATION_UNRESOLVED", {
            item["code"] for item in result["readiness"]["warnings"]
        })
        self.assertEqual(result["reconciliation"]["inventory_landed_cost_cents"], 11000)
        self.assertEqual(result["reconciliation"]["component_adjustment_cents"], -199)

        with self.assertRaisesRegex(ValueError, "Explicit confirmation"):
            select_manual_fallback(self.db, acquisition_id, {
                "request_id": "HF2-FALLBACK-NOT-CONFIRMED",
                "expected_revision": result["acquisition"]["revision"],
            })
        with self.assertRaisesRegex(ValueError, "Retry is unavailable"):
            retry_extraction(self.db, job["job_uuid"], {
                "request_id": "HF2-RETRY-IMPOSSIBLE",
                "expected_revision": result["acquisition"]["revision"],
            }, self.store, self.extractor)

        before_fallback = {
            field: result["acquisition"][field]
            for field in ("purchase_subtotal_cents", "final_usd_paid_cents", "excluded_noninventory_cents")
        }
        select_manual_fallback(self.db, acquisition_id, {
            "request_id": "HF2-FALLBACK",
            "expected_revision": result["acquisition"]["revision"],
            "confirm_manual_fallback": True,
        })
        result = acquisition_payload(self.db, acquisition_id)
        self.assertEqual({field: result["acquisition"][field] for field in before_fallback}, before_fallback)
        self.assertTrue(result["receipt_intelligence"]["manual_fallback_selected"])
        self.assertIn("RECEIPT_ALLOCATION_UNRESOLVED", {
            item["code"] for item in result["receipt_intelligence"]["warnings"]
        })
        self.assertNotIn("RECEIPT_ALLOCATION_UNRESOLVED", {
            item["code"] for item in result["readiness"]["warnings"]
        })
        fallback_event = self.db.execute(
            "SELECT payload FROM receipt_extraction_events WHERE acquisition_id=? AND event_type='MANUAL_FALLBACK_SELECTED'",
            (acquisition_id,),
        ).fetchone()
        self.assertIsNotNone(fallback_event)

        result = autosave_acquisition(self.db, acquisition_id, {
            "request_id": "HF2-WRONG-EXCLUSION",
            "expected_revision": result["acquisition"]["revision"],
            "excluded_noninventory_cents": 2400,
            "noninventory_treatment_code": "MIXED_NONINVENTORY",
            "noninventory_notes": "Explicit noninventory portion.",
        })
        with self.assertRaisesRegex(ValueError, "must equal final USD paid exactly"):
            confirm_acquisition(self.db, acquisition_id, {
                "request_id": "HF2-WRONG-CONFIRM",
                "expected_revision": result["acquisition"]["revision"],
                "confirm_authoritative_financial_facts": True,
                "confirm_reconciliation": True,
                "confirm_noninventory_exclusion": True,
            })

        result = autosave_acquisition(self.db, acquisition_id, {
            "request_id": "HF2-AMOUNT-ONLY",
            "expected_revision": result["acquisition"]["revision"],
            "excluded_noninventory_cents": 2417,
            "noninventory_treatment_code": None,
        })
        with self.assertRaisesRegex(ValueError, "treatment code"):
            confirm_acquisition(self.db, acquisition_id, {
                "request_id": "HF2-MISSING-TREATMENT",
                "expected_revision": result["acquisition"]["revision"],
                "confirm_authoritative_financial_facts": True,
                "confirm_reconciliation": True,
                "confirm_noninventory_exclusion": True,
            })

        result = autosave_acquisition(self.db, acquisition_id, {
            "request_id": "HF2-CORRECT-PARTITION",
            "expected_revision": result["acquisition"]["revision"],
            "excluded_noninventory_cents": 2417,
            "noninventory_treatment_code": "MIXED_NONINVENTORY",
            "noninventory_notes": "Net noninventory portion of the final payment.",
        })
        self.assertTrue(result["reconciliation"]["partition_reconciled"])
        with self.assertRaisesRegex(ValueError, "Explicit excluded-noninventory confirmation"):
            confirm_acquisition(self.db, acquisition_id, {
                "request_id": "HF2-MISSING-EXCLUSION-CHECK",
                "expected_revision": result["acquisition"]["revision"],
                "confirm_authoritative_financial_facts": True,
                "confirm_reconciliation": True,
            })

        ready = confirm_acquisition(self.db, acquisition_id, {
            "request_id": "HF2-CONFIRM",
            "expected_revision": result["acquisition"]["revision"],
            "confirm_authoritative_financial_facts": True,
            "confirm_reconciliation": True,
            "confirm_noninventory_exclusion": True,
        })
        self.assertEqual(ready["acquisition"]["state"], "READY_FOR_INTAKE")
        self.assertEqual(sum(line["assigned_landed_cost_cents"] for line in ready["lines"]), 11000)
        self.assertEqual(ready["acquisition"]["excluded_noninventory_cents"], 2417)
        stored = self.db.execute(
            "SELECT storage_status FROM acquisition_documents WHERE id=?", (document["id"],)
        ).fetchone()[0]
        self.assertEqual(stored, "STORED")

    def test_removed_failed_receipt_keeps_history_without_active_retry_or_warning(self):
        result, document, _ = self.mixed_purchase_with_failed_image()
        tombstone_document(self.db, document["id"], {
            "request_id": "HF2-REMOVE-RECEIPT",
            "expected_revision": result["acquisition"]["revision"],
            "reason_code": "OPERATOR_REMOVED",
            "notes": "Wrong receipt image attached during draft setup.",
        }, self.store)
        intelligence = receipt_intelligence_payload(self.db, result["acquisition"]["id"])
        self.assertEqual(intelligence["jobs"], [])
        self.assertEqual(len(intelligence["historical_jobs"]), 1)
        self.assertEqual(intelligence["failed_job_count"], 0)
        self.assertFalse(intelligence["manual_fallback_available"])
        self.assertNotIn("RECEIPT_ALLOCATION_UNRESOLVED", {
            item["code"] for item in intelligence["warnings"]
        })


if __name__ == "__main__":
    unittest.main()
