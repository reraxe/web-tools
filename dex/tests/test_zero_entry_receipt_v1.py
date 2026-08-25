import base64
import hashlib
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFont

import app
from dex_catalog import create_catalog_product
from dex_documents import LocalFilesystemDocumentStore, upload_document
from dex_inbound import acquisition_payload, confirm_acquisition, create_acquisition
from dex_receipt_ocr import ReceiptOcrFailed, extract_image_text, find_tesseract_command
from dex_receipt_parser import parse_receipt_pages
from dex_receipts import (
    LocalPdfTextReceiptExtractor,
    classify_receipt_line,
    queue_extraction,
    select_manual_fallback,
)


MOM_AND_POP_TEXT = """Mom and Pop Shop
Receipt # MPS-0816
Date: 08/16/2026
Credit / Debit Card
OP13 booster packs x4 30.00
Riftbound Vendetta booster packs x6 30.00
Gear Five Luffy x1 18.00
Discount -1.80
Hobbit Collector Booster x1 50.00
Credit/Debit fee 3.79
Subtotal 129.99
Tax 4.18
Final Paid 134.17
"""


def image_bytes(*, low_contrast=False, angle=0.0, realistic_font=False):
    image = Image.new("RGB", (1500, 1800), (228, 228, 228) if low_contrast else "white")
    draw = ImageDraw.Draw(image)
    color = (125, 125, 125) if low_contrast else "black"
    font = None
    if realistic_font:
        for candidate in (
            Path("C:/Windows/Fonts/consola.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
        ):
            if candidate.is_file():
                font = ImageFont.truetype(str(candidate), 40)
                break
    for index, line in enumerate(MOM_AND_POP_TEXT.splitlines()):
        draw.text((60, 50 + index * 90), line, fill=color, font=font)
    if angle:
        image = image.rotate(angle, expand=True, fillcolor="white")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class ZeroEntryReceiptFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db_path = self.root / "dex.db"
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
        self.products = {}
        for key, name, game, product_class, subtype in (
            ("op13", "OP13 booster packs", "One Piece", "PACK_PRODUCT", "Booster Pack"),
            ("riftbound", "Riftbound Vendetta booster packs", "Riftbound", "PACK_PRODUCT", "Booster Pack"),
            ("gear", "Gear Five Luffy", "One Piece", "SEALED_PRODUCT", "Collectible"),
            ("hobbit", "Hobbit Collector Booster", "Magic", "PACK_PRODUCT", "Collector Booster"),
        ):
            self.products[key] = create_catalog_product(
                self.db,
                {
                    "request_id": f"CATALOG-{key}", "game": game, "display_name": name,
                    "set_code": name.split()[0], "product_class": product_class,
                    "product_subtype": subtype,
                },
            )

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def acquisition(self, request="ZERO-ENTRY-ACQ"):
        return create_acquisition(self.db, {"request_id": request})

    def attach_image(self, result, data, request="ZERO-ENTRY-DOC"):
        uploaded = upload_document(
            self.db,
            result["acquisition"]["id"],
            {
                "request_id": request, "expected_revision": result["acquisition"]["revision"],
                "original_filename": "mom-and-pop.png", "declared_mime_type": "image/png",
                "data_base64": base64.b64encode(data).decode(), "document_role": "RECEIPT",
                "capture_method": "CAMERA",
            },
            self.store,
        )
        return acquisition_payload(self.db, result["acquisition"]["id"]), uploaded

    def extract_with_text(self, result, document, text=MOM_AND_POP_TEXT, request="ZERO-ENTRY-EXTRACT"):
        with patch("dex_receipts.extract_image_text", return_value={
            "pages": [(1, text)],
            "metrics": {"preprocessing_ms": 12.5, "ocr_ms": 80.0, "ocr_attempt_count": 1, "selected_rotation_degrees": 0},
        }):
            job = queue_extraction(
                self.db,
                document["id"],
                {"request_id": request, "expected_revision": result["acquisition"]["revision"], "auto_apply": True},
                self.store,
                self.extractor,
            )
        return acquisition_payload(self.db, result["acquisition"]["id"]), job


class ZeroEntryReceiptTest(ZeroEntryReceiptFixture):
    def test_canonical_mom_and_pop_requires_one_business_answer_and_zero_dollar_typing(self):
        result = self.acquisition()
        original = image_bytes()
        digest = hashlib.sha256(original).hexdigest()
        result, upload = self.attach_image(result, original)
        result, job = self.extract_with_text(result, upload["document"])

        self.assertEqual(job["status"], "COMPLETED")
        self.assertEqual(hashlib.sha256(original).hexdigest(), digest)
        acquisition = result["acquisition"]
        self.assertEqual(acquisition["merchant_name"], "Mom and Pop Shop")
        self.assertEqual(acquisition["purchased_on"], "2026-08-16")
        self.assertEqual(acquisition["payment_method"], "CREDIT_DEBIT_CARD")
        self.assertEqual(acquisition["purchase_subtotal_cents"], 12999)
        self.assertEqual(acquisition["acquisition_tax_cents"], 418)
        self.assertIsNone(acquisition["acquisition_fees_cents"])
        self.assertIsNone(acquisition["acquisition_discount_cents"])
        self.assertEqual(acquisition["final_usd_paid_cents"], 13417)
        self.assertEqual(result["reconciliation"]["difference_cents"], 0)
        self.assertEqual(result["reconciliation"]["component_total_cents"], 13417)
        self.assertNotEqual(result["reconciliation"]["component_total_cents"], 13616)

        intelligence = result["receipt_intelligence"]
        self.assertEqual(intelligence["receipt_math"]["status"], "RECONCILED_EXACT")
        roles = {(item["kind"], item["math_role"]) for item in intelligence["receipt_math"]["components"]}
        self.assertIn(("DISCOUNT", "INCLUDED_IN_SUBTOTAL"), roles)
        self.assertIn(("FEE", "INCLUDED_IN_SUBTOTAL"), roles)
        self.assertIn(("TAX", "OUTSIDE_SUBTOTAL"), roles)
        self.assertEqual([item["description"] for item in intelligence["operator_questions"]], ["Gear Five Luffy"])
        self.assertEqual(len([line for line in result["lines"] if not line["canceled_at"]]), 4)
        self.assertIsNone(intelligence["allocation_proposal"])

        gear = next(item for item in intelligence["receipt_lines"] if item["description"] == "Gear Five Luffy")
        intelligence = classify_receipt_line(
            self.db,
            gear["id"],
            {
                "request_id": "CLASSIFY-GEAR-PERSONAL",
                "expected_revision": result["acquisition"]["revision"],
                "classification": "PERSONAL_NONBUSINESS",
                "notes": "Operator says this item is personal",
            },
        )
        result = acquisition_payload(self.db, acquisition["id"])
        self.assertEqual(intelligence["operator_questions"], [])
        self.assertEqual(result["receipt_intelligence"]["allocation_policy"]["status"], "POLICY_REQUIRED")
        self.assertEqual(result["receipt_intelligence"]["allocation_policy"]["scope"], "MIXED_INVENTORY_NONINVENTORY")
        self.assertIsNone(result["receipt_intelligence"]["allocation_proposal"])
        self.assertIsNone(result["acquisition"]["excluded_noninventory_cents"])
        self.assertIsNone(result["acquisition"]["noninventory_treatment_code"])
        self.assertEqual(
            {item["kind"] for item in result["receipt_intelligence"]["allocation_policy"]["preserved_components"]},
            {"DISCOUNT", "FEE", "TAX"},
        )
        self.assertIn(
            "MIXED_PURCHASE_ALLOCATION_POLICY_REQUIRED",
            {item["code"] for item in result["receipt_intelligence"]["warnings"]},
        )
        with self.assertRaises(ValueError):
            confirm_acquisition(
                self.db,
                acquisition["id"],
                {
                    "request_id": "CONFIRM-ZERO-ENTRY", "expected_revision": result["acquisition"]["revision"],
                    "confirm_authoritative_financial_facts": True, "confirm_reconciliation": True,
                    "confirm_noninventory_exclusion": True,
                },
            )
        self.assertEqual(acquisition_payload(self.db, acquisition["id"])["acquisition"]["state"], "ACQUISITION_INCOMPLETE")

    def test_all_inventory_and_purchase_level_discount_reconcile_without_double_count(self):
        text = """All Inventory Shop
Date 08/16/2026
Debit Card
OP13 booster packs x4 30.00
Riftbound Vendetta booster packs x6 30.00
Purchase Discount -5.00
Subtotal 55.00
Tax 3.30
Total 58.30
"""
        result = self.acquisition("ALL-INVENTORY")
        result, upload = self.attach_image(result, image_bytes(), "ALL-INVENTORY-DOC")
        result, _ = self.extract_with_text(result, upload["document"], text, "ALL-INVENTORY-EXTRACT")
        self.assertEqual(result["receipt_intelligence"]["receipt_math"]["status"], "RECONCILED_EXACT")
        self.assertIsNone(result["acquisition"]["acquisition_discount_cents"])
        self.assertEqual(result["acquisition"]["purchase_subtotal_cents"], 5500)
        self.assertEqual(result["acquisition"]["final_usd_paid_cents"], 5830)
        self.assertEqual(result["receipt_intelligence"]["operator_questions"], [])
        self.assertEqual(result["receipt_intelligence"]["allocation_proposal"]["total_allocated_cents"], 5830)
        self.assertEqual(
            result["receipt_intelligence"]["allocation_proposal"]["calculation_version"],
            "receipt-landed-allocation-v1",
        )
        self.assertTrue(result["readiness"]["ready_to_confirm"])
        confirmed = confirm_acquisition(
            self.db,
            result["acquisition"]["id"],
            {
                "request_id": "CONFIRM-ALL-INVENTORY-ZERO-ENTRY",
                "expected_revision": result["acquisition"]["revision"],
                "confirm_authoritative_financial_facts": True,
                "confirm_reconciliation": True,
            },
        )
        self.assertEqual(confirmed["acquisition"]["state"], "READY_FOR_INTAKE")

    def test_unreconciled_receipt_never_generates_allocation(self):
        text = """Broken Math Shop
Date 08/16/2026
Debit Card
OP13 booster packs x4 30.00
Subtotal 35.00
Tax 4.00
Total 41.00
"""
        result = self.acquisition("BROKEN-MATH")
        result, upload = self.attach_image(result, image_bytes(), "BROKEN-MATH-DOC")
        result, _ = self.extract_with_text(result, upload["document"], text, "BROKEN-MATH-EXTRACT")
        intelligence = result["receipt_intelligence"]
        self.assertEqual(intelligence["receipt_math"]["status"], "UNRECONCILED")
        self.assertIsNone(intelligence["allocation_proposal"])
        self.assertIn("RECEIPT_MATH_UNRECONCILED", {item["code"] for item in intelligence["warnings"]})

    def test_ocr_failure_preserves_hf2_manual_fallback(self):
        result = self.acquisition("OCR-FAILURE")
        result, upload = self.attach_image(result, image_bytes(), "OCR-FAILURE-DOC")
        with patch("dex_receipts.extract_image_text", side_effect=ReceiptOcrFailed("Unreadable receipt")):
            job = queue_extraction(
                self.db,
                upload["document"]["id"],
                {"request_id": "OCR-FAILURE-EXTRACT", "expected_revision": result["acquisition"]["revision"]},
                self.store,
                self.extractor,
            )
        result = acquisition_payload(self.db, result["acquisition"]["id"])
        self.assertEqual(job["status"], "FAILED")
        self.assertTrue(result["receipt_intelligence"]["manual_fallback_available"])
        fallback = select_manual_fallback(
            self.db,
            result["acquisition"]["id"],
            {
                "request_id": "OCR-FAILURE-MANUAL", "expected_revision": result["acquisition"]["revision"],
                "confirm_manual_fallback": True,
            },
        )
        self.assertTrue(fallback["manual_fallback_selected"])

    def test_duplicate_upload_is_suppressed_before_second_extraction(self):
        result = self.acquisition("DUPLICATE-RECEIPT")
        data = image_bytes()
        result, first = self.attach_image(result, data, "DUPLICATE-FIRST")
        result, _ = self.extract_with_text(result, first["document"], request="DUPLICATE-EXTRACT")
        second = upload_document(
            self.db,
            result["acquisition"]["id"],
            {
                "request_id": "DUPLICATE-SECOND", "expected_revision": result["acquisition"]["revision"],
                "original_filename": "same.png", "declared_mime_type": "image/png",
                "data_base64": base64.b64encode(data).decode(), "document_role": "RECEIPT",
            },
            self.store,
        )
        self.assertTrue(second["duplicate"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM receipt_extraction_jobs").fetchone()[0], 1)


class LocalReceiptOcrTest(unittest.TestCase):
    def test_low_contrast_and_mild_rotation_use_disposable_derived_image(self):
        original = image_bytes(low_contrast=True, angle=2.5)
        original_hash = hashlib.sha256(original).hexdigest()
        with (
            patch("dex_receipt_ocr.find_tesseract_command", return_value="fixture-tesseract"),
            patch("dex_receipt_ocr._run_tesseract", return_value=(MOM_AND_POP_TEXT, 42.0)) as run,
        ):
            result = extract_image_text(original)
        self.assertEqual(result["pages"][0][1], MOM_AND_POP_TEXT)
        self.assertEqual(result["metrics"]["ocr_attempt_count"], 1)
        self.assertTrue(run.call_args.args[1].name.endswith(".png"))
        self.assertEqual(hashlib.sha256(original).hexdigest(), original_hash)

    def test_installed_local_tesseract_reads_realistic_low_contrast_rotated_receipt(self):
        if not find_tesseract_command():
            self.skipTest("Local Tesseract is not installed in this test environment")
        if not any(Path(item).is_file() for item in (
            "C:/Windows/Fonts/consola.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        )):
            self.skipTest("A deterministic test font is unavailable")
        original = image_bytes(low_contrast=True, angle=1.5, realistic_font=True)
        result = extract_image_text(original)
        parsed = parse_receipt_pages(result["pages"])
        self.assertEqual(parsed["receipt_math"]["status"], "RECONCILED_EXACT")
        self.assertEqual(len(parsed["lines"]), 4)
        self.assertGreater(result["metrics"]["ocr_ms"], 0)


class ReceiptParserCoverageTest(unittest.TestCase):
    def test_quantity_prefix_line_item_discount_fee_tax_and_component_boundary(self):
        parsed = parse_receipt_pages([(1, MOM_AND_POP_TEXT)])
        self.assertEqual([item["quantity"] for item in parsed["lines"]], [4, 6, 1, 1])
        self.assertEqual(parsed["receipt_math"]["status"], "RECONCILED_EXACT")
        fields = {item["field_name"]: item["normalized_value"] for item in parsed["candidates"]}
        self.assertEqual(fields["purchase_subtotal_cents"], "12999")
        self.assertEqual(fields["acquisition_tax_cents"], "418")
        self.assertEqual(fields["final_usd_paid_cents"], "13417")
        self.assertNotIn("acquisition_fees_cents", fields)
        self.assertNotIn("acquisition_discount_cents", fields)

    def test_line_item_discount_is_linked_as_evidence_without_double_counting(self):
        text = """Line Discount Shop
OP13 booster packs x4 32.00
Item discount -2.00
Subtotal 30.00
Tax 1.80
Final Paid 31.80
"""
        parsed = parse_receipt_pages([(1, text)])
        self.assertEqual(parsed["receipt_math"]["status"], "RECONCILED_EXACT")
        discount = next(
            item for item in parsed["receipt_math"]["components"]
            if item["kind"] == "DISCOUNT"
        )
        self.assertEqual(discount["scope"], "LINE_ITEM")
        self.assertEqual(discount["applies_to_description"], "OP13 booster packs")
        self.assertEqual(discount["math_role"], "INCLUDED_IN_SUBTOTAL")
        fields = {item["field_name"] for item in parsed["candidates"]}
        self.assertNotIn("acquisition_discount_cents", fields)


if __name__ == "__main__":
    unittest.main()
