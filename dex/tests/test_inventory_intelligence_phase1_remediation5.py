import io
import sqlite3
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import dex_receipts
from dex_inbound import acquisition_payload, confirm_acquisition, create_acquisition
from dex_receipt_ocr import ReceiptOcrFailed
from dex_receipts import queue_extraction, retry_extraction
from tests.test_v22_phase5_receipts import ReceiptFixture


FANTASY_BAY = """| } 7A/V\\TASY BAV ~~
Fantasy Bay
726 Broadway
BAYONNE, NJ 07092
08/20/2026 03:42 PM
Receipt # FB-SYNTHETIC-002
OP deck $16.00
Purchase Subtotal $16.00
UEZ (3.3125%5)} $0.53
Total $16.53
@ MasterCard 0000 (Contactless)
Auth code: 000000
AID: A0000000000000
No CVM
ITEMS SOLD: 1
Thank you for shopping at Fantasy Bay
for store credit within two weeks of the purchase date.
Exchanges require receipt.
Store credit only for opened returns.
Customer copy
www.example.invalid
Tel: 555-0100
********
End of receipt
"""


def image_bytes(image_format="PNG"):
    output = io.BytesIO()
    Image.new("RGB", (640, 900), "white").save(output, format=image_format)
    return output.getvalue()


def simple_receipt(payment_label):
    return f"""Brand Test Shop
Date 08/21/2026
{payment_label}
Inventory item $10.00
Subtotal $10.00
Total $10.00
"""


class Remediation5ReceiptExtractionTests(ReceiptFixture):
    def blank_acquisition(self, request):
        return create_acquisition(self.db, {"request_id": request})

    def attach_image(self, result, *, image_format="PNG", request="R5-DOC"):
        extension = "jpg" if image_format == "JPEG" else "png"
        mime = "image/jpeg" if image_format == "JPEG" else "image/png"
        return self.attach(
            result, image_bytes(image_format), f"receipt.{extension}", mime, request
        )

    def extract_image_text(self, result, document, text, request):
        with (
            patch("dex_receipt_ocr.find_tesseract_command", return_value="fixture-tesseract"),
            patch("dex_receipt_ocr._run_tesseract", return_value=(text, 12.0)),
        ):
            return self.extract(result, document, request)

    def test_fantasy_bay_png_completes_full_pipeline_and_remains_allocation_blocked(self):
        result = self.add_line(self.blank_acquisition("R5-FANTASY"), "OP deck", quantity=1)
        result, document = self.attach_image(result, request="R5-FANTASY-DOC")
        result, job = self.extract_image_text(
            result, document, FANTASY_BAY, "R5-FANTASY-EXTRACT"
        )

        self.assertEqual(job["status"], "COMPLETED")
        self.assertEqual(result["acquisition"]["merchant_name"], "Fantasy Bay")
        self.assertEqual(result["acquisition"]["payment_method"], "CREDIT_DEBIT_CARD")
        self.assertEqual(result["acquisition"]["final_usd_paid_cents"], 1653)
        payment = next(
            item for item in job["candidates"] if item["field_name"] == "payment_method"
        )
        self.assertEqual(payment["normalized_value"], "CREDIT_DEBIT_CARD")
        tender = next(
            item for item in result["receipt_intelligence"]["semantic_review"]["lines"]
            if "MasterCard" in item["normalized_text"]
        )
        self.assertFalse(tender["authoritative"])
        corrupt = next(
            item for item in result["receipt_intelligence"]["semantic_review"]["lines"]
            if item["normalized_text"] == "UEZ (3.3125%5)} $0.53"
        )
        self.assertEqual(corrupt["semantic_class"], "UNKNOWN")
        self.assertTrue(corrupt["operator_confirmation_required"])
        self.assertEqual(result["receipt_intelligence"]["receipt_math"]["status"], "UNRECONCILED")
        self.assertIsNone(result["receipt_intelligence"]["allocation_proposal"])
        self.assertIsNone(result["automatic_single_line_allocation_preview"])
        with self.assertRaisesRegex(ValueError, "Automatic allocation is not ready"):
            confirm_acquisition(self.db, result["acquisition"]["id"], {
                "request_id": "R5-FANTASY-CONFIRM",
                "expected_revision": result["acquisition"]["revision"],
                "confirm_authoritative_financial_facts": True,
                "confirm_reconciliation": True,
            })
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM acquisition_events WHERE acquisition_id=? AND event_type='ALLOCATION_CONFIRMED'",
            (result["acquisition"]["id"],),
        ).fetchone()[0], 0)

    def test_card_brands_normalize_to_existing_broad_payment_method(self):
        for index, label in enumerate(("Visa", "Mastercard", "Amex", "Discover"), 1):
            with self.subTest(label=label):
                result = self.blank_acquisition(f"R5-BRAND-{index}")
                result, document = self.attach_image(result, request=f"R5-BRAND-DOC-{index}")
                result, job = self.extract_image_text(
                    result, document, simple_receipt(label), f"R5-BRAND-EXTRACT-{index}"
                )
                self.assertEqual(job["status"], "COMPLETED")
                self.assertEqual(result["acquisition"]["payment_method"], "CREDIT_DEBIT_CARD")
                candidate = next(
                    item for item in job["candidates"] if item["field_name"] == "payment_method"
                )
                self.assertEqual(candidate["normalized_value"], "CREDIT_DEBIT_CARD")

    def test_unsupported_payment_evidence_is_rejected_non_authoritatively_without_crash(self):
        result = self.blank_acquisition("R5-UNSUPPORTED")
        result, document = self.attach_image(result, request="R5-UNSUPPORTED-DOC")
        result, job = self.extract_image_text(
            result, document, simple_receipt("Apple Pay"), "R5-UNSUPPORTED-EXTRACT"
        )

        self.assertEqual(job["status"], "COMPLETED")
        self.assertEqual(result["acquisition"]["payment_method"], "")
        candidate = next(
            item for item in job["candidates"] if item["field_name"] == "payment_method"
        )
        self.assertEqual(candidate["normalized_value"], "APPLE_PAY")
        self.assertEqual(candidate["disposition"], "REJECTED")
        event = self.db.execute(
            "SELECT reason_code,payload FROM receipt_extraction_events "
            "WHERE candidate_id=? AND event_type='RECEIPT_CANDIDATE_REJECTED'",
            (candidate["id"],),
        ).fetchone()
        self.assertIsNotNone(event)
        self.assertEqual(event["reason_code"], "UNSUPPORTED_PAYMENT_METHOD")
        self.assertNotIn("APPLE_PAY", event["payload"])

    def test_jpeg_uses_same_complete_orchestration_path(self):
        result = self.blank_acquisition("R5-JPEG")
        result, document = self.attach_image(
            result, image_format="JPEG", request="R5-JPEG-DOC"
        )
        result, job = self.extract_image_text(
            result, document, simple_receipt("Visa"), "R5-JPEG-EXTRACT"
        )
        self.assertEqual(document["detected_mime_type"], "image/jpeg")
        self.assertEqual(job["status"], "COMPLETED")
        self.assertEqual(result["acquisition"]["payment_method"], "CREDIT_DEBIT_CARD")
        self.assertGreater(result["receipt_intelligence"]["semantic_review"]["active_assertion_count"], 0)

    def test_retry_success_is_sole_active_interpretation_and_preserves_prior_history(self):
        result = self.blank_acquisition("R5-RETRY")
        result, document = self.attach_image(result, request="R5-RETRY-DOC")
        result, first = self.extract_image_text(
            result, document, simple_receipt("Mastercard"), "R5-RETRY-FIRST"
        )
        self.assertEqual(first["status"], "COMPLETED")

        with patch(
            "dex_receipts.extract_image_text",
            side_effect=ReceiptOcrFailed("Private local OCR could not complete"),
        ):
            failed = queue_extraction(
                self.db, document["id"], {
                    "request_id": "R5-RETRY-FAILED",
                    "expected_revision": result["acquisition"]["revision"],
                    "auto_apply": True,
                }, self.store, self.extractor,
            )
        self.assertEqual(failed["status"], "FAILED")
        result = acquisition_payload(self.db, result["acquisition"]["id"])
        self.assertEqual(result["receipt_intelligence"]["semantic_review"]["active_assertion_count"], 0)

        with (
            patch("dex_receipt_ocr.find_tesseract_command", return_value="fixture-tesseract"),
            patch("dex_receipt_ocr._run_tesseract", return_value=(simple_receipt("Visa"), 10.0)),
        ):
            retry = retry_extraction(
                self.db, failed["job_uuid"], {
                    "request_id": "R5-RETRY-SUCCESS",
                    "expected_revision": result["acquisition"]["revision"],
                    "auto_apply": True,
                }, self.store, self.extractor,
            )
        self.assertEqual(retry["status"], "COMPLETED")
        result = acquisition_payload(self.db, result["acquisition"]["id"])
        intelligence = result["receipt_intelligence"]
        self.assertEqual([job["id"] for job in intelligence["jobs"]], [retry["id"]])
        self.assertEqual(
            {job["status"] for job in intelligence["historical_jobs"]},
            {"COMPLETED", "FAILED"},
        )
        active_job_ids = {
            item["job_id"] for item in intelligence["semantic_review"]["lines"]
        }
        self.assertEqual(active_job_ids, {retry["id"]})
        historical_job_ids = {
            item["job_id"] for item in intelligence["semantic_review"]["history"]
        }
        self.assertIn(first["id"], historical_job_ids)
        self.assertEqual(result["acquisition"]["payment_method"], "CREDIT_DEBIT_CARD")

    def test_candidate_database_failure_uses_specific_privacy_safe_status(self):
        result = self.blank_acquisition("R5-APPLICATION-FAIL")
        result, document = self.attach_image(result, request="R5-APPLICATION-FAIL-DOC")
        with (
            patch("dex_receipt_ocr.find_tesseract_command", return_value="fixture-tesseract"),
            patch("dex_receipt_ocr._run_tesseract", return_value=(simple_receipt("Visa"), 8.0)),
            patch.object(
                dex_receipts, "apply_proposed_facts",
                side_effect=sqlite3.IntegrityError("private source detail must not escape"),
            ),
        ):
            _, job = self.extract(result, document, "R5-APPLICATION-FAIL-EXTRACT")
        self.assertEqual(job["status"], "FAILED")
        self.assertEqual(job["error_code"], "CANDIDATE_APPLICATION_FAILED")
        self.assertEqual(job["error_message"], "Receipt candidates could not be applied safely")
        self.assertNotIn("private source detail", job["error_message"])


class Remediation5DockerSmokeContractTests(__import__("unittest").TestCase):
    def test_docker_build_runs_tesseract_through_complete_receipt_orchestration(self):
        root = Path(__file__).resolve().parents[1]
        dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
        smoke = (root / "scripts" / "docker_receipt_orchestration_smoke.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "COPY scripts/docker_receipt_orchestration_smoke.py ./scripts/docker_receipt_orchestration_smoke.py",
            dockerfile,
        )
        self.assertIn("RUN python scripts/docker_receipt_orchestration_smoke.py", dockerfile)
        self.assertIn("queue_extraction", smoke)
        self.assertIn("get_receipt_extractor", smoke)
        self.assertIn('job["status"] == "COMPLETED"', smoke)
        self.assertIn('payment_method"] == "CREDIT_DEBIT_CARD"', smoke)


if __name__ == "__main__":
    import unittest

    unittest.main()
