import base64
import io
import json
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import app
from dex_catalog import create_catalog_product
from dex_documents import LocalFilesystemDocumentStore, upload_document
from dex_inbound import acquisition_payload, create_acquisition
from dex_receipt_parser import parse_receipt_pages
from dex_receipt_semantics import (
    SEMANTIC_CLASSES,
    classify_receipt_pages,
    classify_source_line,
    current_semantic_lines,
    decide_semantic_line,
    semantic_allows_receipt_line,
)
from dex_receipts import (
    LocalPdfTextReceiptExtractor,
    queue_extraction,
    reconcile_semantic_merchandise_line,
)
from dex_migrations import DEFAULT_MIGRATIONS, apply_migrations


GOLDEN_TEXT = """Mom and Pop Shop
Receipt # MPS-SYNTHETIC
One Piece booster packs x4 30.00
Riftbound booster packs x6 30.00
Luffy Gear Five #1607 x1 18.00
MTG collector pack x1 50.00
10% Off -1.80
Credit/Debit Fee 3.79
Subtotal 129.99
State Tax 3.3125% 4.18
Total 134.17
DEBIT CARD SALE
Total by cash: 130.38
Thank you for shopping
"""


def tiny_png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (12, 12), "white").save(output, format="PNG")
    return output.getvalue()


class ReceiptSemanticUnitTests(unittest.TestCase):
    def classify(self, text):
        return classify_source_line(
            text,
            source_line_index=1,
            source_page=1,
            source_location="line 1",
            parser_version="test-parser",
        )

    def test_all_required_semantic_classes_and_confidence_states(self):
        examples = {
            "MERCHANDISE": "OP13 booster packs x4 30.00",
            "DISCOUNT_CREDIT": "10% Off -1.80",
            "FEE_SURCHARGE": "Credit/Debit Fee 3.79",
            "TAX": "State Tax 3.3125% 4.18",
            "SHIPPING": "Shipping 5.00",
            "SUBTOTAL": "Subtotal 129.99",
            "TOTAL": "Total 134.17",
            "TENDER_PAYMENT_METHOD": "DEBIT CARD SALE",
            "PAYMENT_SUMMARY": "Total by cash: 130.38",
            "INFORMATIONAL_FOOTER": "Thank you for shopping",
            "STRUCTURAL": "ITEM DESCRIPTION QTY PRICE",
            "UNKNOWN": "Mystery adjustment -2.00",
        }
        self.assertEqual(set(examples), set(SEMANTIC_CLASSES))
        for expected, text in examples.items():
            with self.subTest(expected=expected):
                result = self.classify(text)
                self.assertEqual(result["semantic_class"], expected)
                self.assertFalse(result["evidence"]["arithmetic_used_as_authority"])
                self.assertIn(
                    result["confidence_state"],
                    {"HIGH_CONFIDENCE_SUGGESTION", "UNRESOLVED", "CONFLICTING"},
                )
        self.assertEqual(self.classify("10% Off -1.80")["signed_amount_cents"], -180)
        self.assertEqual(self.classify("Coupon −$2.50")["signed_amount_cents"], -250)
        self.assertEqual(self.classify("State Tax 3.3125% 4.18")["signed_amount_cents"], 418)
        self.assertEqual(self.classify("Mystery adjustment -2.00")["confidence_state"], "UNRESOLVED")
        conflict = self.classify("Tax / Discount adjustment 1.00")
        self.assertEqual(conflict["semantic_class"], "UNKNOWN")
        self.assertEqual(conflict["confidence_state"], "CONFLICTING")
        self.assertTrue(conflict["operator_confirmation_required"])

    def test_golden_semantics_and_arithmetic_ignore_payment_summary(self):
        parsed = parse_receipt_pages([(1, GOLDEN_TEXT)])
        by_text = {item["normalized_text"]: item for item in parsed["semantic_lines"]}
        expected = {
            "One Piece booster packs x4 30.00": "MERCHANDISE",
            "Riftbound booster packs x6 30.00": "MERCHANDISE",
            "Luffy Gear Five #1607 x1 18.00": "MERCHANDISE",
            "MTG collector pack x1 50.00": "MERCHANDISE",
            "10% Off -1.80": "DISCOUNT_CREDIT",
            "Credit/Debit Fee 3.79": "FEE_SURCHARGE",
            "Subtotal 129.99": "SUBTOTAL",
            "State Tax 3.3125% 4.18": "TAX",
            "Total 134.17": "TOTAL",
            "DEBIT CARD SALE": "TENDER_PAYMENT_METHOD",
            "Total by cash: 130.38": "PAYMENT_SUMMARY",
            "Thank you for shopping": "INFORMATIONAL_FOOTER",
        }
        for text, semantic_class in expected.items():
            self.assertEqual(by_text[text]["semantic_class"], semantic_class)
        self.assertEqual(parsed["receipt_math"]["status"], "RECONCILED_EXACT")
        self.assertEqual(parsed["receipt_math"]["merchandise_total_cents"], 12800)
        self.assertEqual(parsed["receipt_math"]["printed_subtotal_cents"], 12999)
        self.assertEqual(parsed["receipt_math"]["final_paid_cents"], 13417)
        self.assertNotIn("Total by cash", {item["description"] for item in parsed["lines"]})

    def test_large_receipt_semantic_pass_is_local_and_prompt(self):
        source = "\n".join(f"Product line {index} x1 {index % 97 + 1}.00" for index in range(1000))
        started = time.perf_counter()
        results = classify_receipt_pages([(1, source)], parser_version="performance-fixture")
        elapsed = time.perf_counter() - started
        self.assertEqual(len(results), 1000)
        self.assertTrue(all(item["semantic_class"] == "MERCHANDISE" for item in results))
        self.assertLess(elapsed, 1.0)


class ReceiptSemanticPersistenceTests(unittest.TestCase):
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

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def extract(self):
        acquisition = create_acquisition(self.db, {"request_id": "SEM-ACQ"})
        for request, name, game in (
            ("CAT-OP", "One Piece booster packs", "One Piece"),
            ("CAT-RIFT", "Riftbound booster packs", "Riftbound"),
            ("CAT-LUFFY", "Luffy Gear Five #1607", "One Piece"),
            ("CAT-MTG", "MTG collector pack", "Magic"),
            ("CAT-CASH", "Total by cash", "Other"),
        ):
            create_catalog_product(self.db, {
                "request_id": request,
                "game": game,
                "display_name": name,
                "set_code": "TEST",
                "product_class": "PACK_PRODUCT",
                "product_subtype": "Test",
            })
        upload = upload_document(
            self.db,
            acquisition["acquisition"]["id"],
            {
                "request_id": "SEM-DOC",
                "expected_revision": acquisition["acquisition"]["revision"],
                "original_filename": "synthetic.png",
                "declared_mime_type": "image/png",
                "data_base64": base64.b64encode(tiny_png()).decode(),
                "document_role": "RECEIPT",
                "capture_method": "FILE_UPLOAD",
            },
            self.store,
        )
        current = acquisition_payload(self.db, acquisition["acquisition"]["id"])
        with patch("dex_receipts.extract_image_text", return_value={
            "pages": [(1, GOLDEN_TEXT)],
            "metrics": {"preprocessing_ms": 1.0, "ocr_ms": 2.0},
        }):
            queue_extraction(
                self.db,
                upload["document"]["id"],
                {
                    "request_id": "SEM-EXTRACT",
                    "expected_revision": current["acquisition"]["revision"],
                    "auto_apply": False,
                },
                self.store,
                self.extractor,
            )
        return acquisition["acquisition"]["id"]

    def test_every_source_line_is_persisted_with_provenance_and_matching_gate(self):
        acquisition_id = self.extract()
        lines = current_semantic_lines(self.db, acquisition_id=acquisition_id)
        self.assertEqual(len(lines), len([line for line in GOLDEN_TEXT.splitlines() if line.strip()]))
        self.assertTrue(all(item["job_id"] and item["document_id"] for item in lines))
        self.assertTrue(all(item["source_line_sha256"] and item["recorded_at"] for item in lines))
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM receipt_semantic_events WHERE event_type='CLASSIFIED'").fetchone()[0],
            len(lines),
        )
        receipt_rows = self.db.execute("SELECT * FROM receipt_lines ORDER BY id").fetchall()
        self.assertEqual(len(receipt_rows), 5)
        eligible = [row for row in receipt_rows if semantic_allows_receipt_line(self.db, row["id"])]
        self.assertEqual(len(eligible), 4)
        payment_summary = next(row for row in receipt_rows if row["description"] == "Total by cash")
        self.assertFalse(semantic_allows_receipt_line(self.db, payment_summary["id"]))
        self.assertFalse(any(
            row["product_name"] == "Total by cash"
            for row in self.db.execute(
                "SELECT product_name FROM acquisition_lines WHERE acquisition_id=?", (acquisition_id,)
            ).fetchall()
        ))

        payment_semantic = next(
            item for item in lines if item["semantic_class"] == "PAYMENT_SUMMARY"
        )
        resolved = decide_semantic_line(self.db, payment_semantic["semantic_uuid"], {
            "request_id": "SEM-EXPLICIT-MERCH-RESOLUTION",
            "action": "CHANGE",
            "semantic_class": "MERCHANDISE",
            "reason_code": "PARSER_MISCLASSIFIED",
            "notes": "Synthetic gate test only",
        })
        reconcile_semantic_merchandise_line(self.db, resolved, "SEM-EXPLICIT-MERCH-RESOLUTION")
        self.assertTrue(semantic_allows_receipt_line(self.db, payment_summary["id"]))
        self.assertEqual(
            self.db.execute(
                "SELECT COUNT(*) FROM receipt_line_matches WHERE receipt_line_id=?",
                (payment_summary["id"],),
            ).fetchone()[0],
            1,
        )

    def test_operator_confirmation_and_correction_append_history(self):
        acquisition_id = self.extract()
        tax = next(
            item for item in current_semantic_lines(self.db, acquisition_id=acquisition_id)
            if item["semantic_class"] == "TAX"
        )
        confirmed = decide_semantic_line(self.db, tax["semantic_uuid"], {
            "request_id": "SEM-CONFIRM-TAX", "action": "CONFIRM",
        })
        self.assertEqual(confirmed["confidence_state"], "OPERATOR_CONFIRMED")
        corrected = decide_semantic_line(self.db, confirmed["semantic_uuid"], {
            "request_id": "SEM-CORRECT-TAX",
            "action": "CHANGE",
            "semantic_class": "FEE_SURCHARGE",
            "reason_code": "PARSER_MISCLASSIFIED",
            "notes": "Synthetic correction test",
        })
        self.assertEqual(corrected["semantic_class"], "FEE_SURCHARGE")
        self.assertEqual(
            self.db.execute(
                "SELECT COUNT(*) FROM receipt_semantic_lines WHERE source_line_sha256=?",
                (tax["source_line_sha256"],),
            ).fetchone()[0],
            3,
        )
        history = self.db.execute(
            "SELECT event_type FROM receipt_semantic_events WHERE semantic_line_id IN (SELECT id FROM receipt_semantic_lines WHERE source_line_sha256=?) ORDER BY recorded_at,event_id",
            (tax["source_line_sha256"],),
        ).fetchall()
        self.assertEqual(
            {row["event_type"] for row in history},
            {"CLASSIFIED", "OPERATOR_CONFIRMED", "OPERATOR_CORRECTED"},
        )
        replay = decide_semantic_line(self.db, confirmed["semantic_uuid"], {
            "request_id": "SEM-CORRECT-TAX",
            "action": "CHANGE",
            "semantic_class": "FEE_SURCHARGE",
            "reason_code": "PARSER_MISCLASSIFIED",
        })
        self.assertTrue(replay["idempotent_replay"])

    def test_semantic_review_and_decision_api_contract(self):
        acquisition_id = self.extract()
        tax = next(
            item for item in current_semantic_lines(self.db, acquisition_id=acquisition_id)
            if item["semantic_class"] == "TAX"
        )
        self.db.commit()
        with patch.object(app, "DB_PATH", self.db_path):
            server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.DexHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with urllib.request.urlopen(
                    f"{base}/api/acquisitions/{acquisition_id}/receipt-semantics", timeout=5
                ) as response:
                    review = json.loads(response.read())
                self.assertEqual(response.status, 200)
                self.assertEqual(len(review["lines"]), len(GOLDEN_TEXT.splitlines()))
                self.assertFalse(review["lines"][0]["authoritative"])

                request = urllib.request.Request(
                    f"{base}/api/receipt-semantic-lines/{tax['semantic_uuid']}/decision",
                    data=json.dumps({
                        "request_id": "SEM-API-CONFIRM-TAX", "action": "CONFIRM",
                    }).encode(),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    decision = json.loads(response.read())
                self.assertEqual(response.status, 200)
                self.assertEqual(decision["confidence_state"], "OPERATOR_CONFIRMED")
                self.assertFalse(decision["authoritative"])
                current = decision["acquisition_payload"]["receipt_intelligence"]["semantic_review"]["lines"]
                confirmed = next(item for item in current if item["source_line_sha256"] == tax["source_line_sha256"])
                self.assertEqual(confirmed["confidence_state"], "OPERATOR_CONFIRMED")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    def test_migration_is_additive_and_does_not_backfill_existing_receipt_rows(self):
        migration_ids = [
            row[0] for row in self.db.execute(
                "SELECT migration_id FROM schema_migrations ORDER BY migration_id"
            ).fetchall()
        ]
        self.assertEqual(migration_ids[-1], "0019_v24_sam_multi_evidence_operator_trial_v1a")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM receipt_semantic_lines").fetchone()[0], 0)
        self.assertEqual(self.db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_disposable_hf3_history_migrates_without_rewriting_source_facts(self):
        acquisition_id = self.extract()
        acquisition_before = dict(self.db.execute(
            "SELECT * FROM acquisitions WHERE id=?", (acquisition_id,)
        ).fetchone())
        receipt_before = [dict(row) for row in self.db.execute(
            "SELECT * FROM receipt_lines WHERE acquisition_id=? ORDER BY id", (acquisition_id,)
        ).fetchall()]
        job_before = [dict(row) for row in self.db.execute(
            "SELECT * FROM receipt_extraction_jobs WHERE acquisition_id=? ORDER BY id", (acquisition_id,)
        ).fetchall()]

        # Turn this disposable database into an RC3/HF3-shaped fixture: retain
        # extraction history, remove only Phase 1 semantic structures/ledger.
        self.db.execute("DELETE FROM receipt_semantic_events")
        self.db.execute("DELETE FROM receipt_semantic_lines")
        self.db.execute("DROP TABLE receipt_semantic_events")
        self.db.execute("DROP TABLE receipt_semantic_lines")
        self.db.execute(
            "DELETE FROM schema_migrations WHERE migration_id=?",
            ("0016_v23_inventory_intelligence_phase1_receipt_semantics",),
        )
        self.db.commit()

        applied = apply_migrations(self.db, DEFAULT_MIGRATIONS)
        self.assertEqual(applied, ("0016_v23_inventory_intelligence_phase1_receipt_semantics",))
        self.assertEqual(dict(self.db.execute(
            "SELECT * FROM acquisitions WHERE id=?", (acquisition_id,)
        ).fetchone()), acquisition_before)
        self.assertEqual([dict(row) for row in self.db.execute(
            "SELECT * FROM receipt_lines WHERE acquisition_id=? ORDER BY id", (acquisition_id,)
        ).fetchall()], receipt_before)
        self.assertEqual([dict(row) for row in self.db.execute(
            "SELECT * FROM receipt_extraction_jobs WHERE acquisition_id=? ORDER BY id", (acquisition_id,)
        ).fetchall()], job_before)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM receipt_semantic_lines").fetchone()[0], 0)
        self.assertEqual(self.db.execute("PRAGMA integrity_check").fetchone()[0], "ok")


if __name__ == "__main__":
    unittest.main()
