import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from dex_inbound import (
    add_acquisition_line,
    autosave_acquisition,
    autosave_acquisition_line,
    confirm_acquisition,
    confirm_line_allocation,
    create_acquisition,
)
from dex_migrations import DEFAULT_MIGRATIONS, apply_migrations
from tests.test_phase5_sealed import base_schema


class MixedPurchaseFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.db_path = root / "rc3-hf1.db"
        with (
            patch.object(app, "DB_PATH", self.db_path),
            patch.object(app, "DATA_DIR", root),
            patch.object(app, "IMAGE_DIR", root / "images"),
            patch.object(app, "INBOUND_DIR", root / "inbound"),
            patch.object(app, "SOURCE_DB_DIR", root / "source"),
        ):
            app.init_db()
        self.db = sqlite3.connect(self.db_path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def mixed_purchase(self):
        result = create_acquisition(
            self.db,
            {
                "request_id": "HF1-CREATE",
                "source_scope": "DOMESTIC",
                "merchant_name": "Mom and Pop Shop",
                "purchased_on": "2026-08-16",
                "payment_method": "CREDIT_DEBIT_CARD",
                "purchase_subtotal_cents": 13616,
                "final_usd_paid_cents": 13417,
                "discrepancy_reason_code": "MERCHANT_TOTAL_CONTROLS",
                "discrepancy_notes": "Merchant credit reduced the component total by $1.99.",
            },
        )
        for sequence, amount in enumerate((3000, 5000, 3000), start=1):
            result = add_acquisition_line(
                self.db,
                result["acquisition"]["id"],
                {
                    "request_id": f"HF1-LINE-{sequence}",
                    "expected_revision": result["acquisition"]["revision"],
                    "product_class": "SEALED_PRODUCT",
                    "game": "One Piece",
                    "set_code": f"OP{12 + sequence:02d}",
                    "product_name": f"Inventory product {sequence}",
                    "quantity": 1,
                    "quantity_certainty": "KNOWN",
                },
            )
            result = confirm_line_allocation(
                self.db,
                result["lines"][-1]["id"],
                {
                    "request_id": f"HF1-ALLOC-{sequence}",
                    "expected_revision": result["acquisition"]["revision"],
                    "assigned_landed_cost_cents": amount,
                    "allocation_method": "ACTUAL_LINE_COST",
                    "confirm_allocation": True,
                },
            )
        return result


class MixedPurchaseReconciliationTest(MixedPurchaseFixture):
    def test_exact_live_mixed_purchase_requires_and_accepts_explicit_partition(self):
        result = self.mixed_purchase()
        reconciliation = result["reconciliation"]
        self.assertEqual(reconciliation["component_total_cents"], 13616)
        self.assertEqual(reconciliation["component_adjustment_cents"], -199)
        self.assertTrue(reconciliation["component_reconciled"])
        self.assertEqual(reconciliation["inventory_landed_cost_cents"], 11000)
        self.assertIsNone(reconciliation["excluded_noninventory_cents"])
        self.assertEqual(reconciliation["partition_difference_cents"], 2417)
        self.assertFalse(reconciliation["partition_reconciled"])
        warning_codes = {item["code"] for item in result["readiness"]["warnings"]}
        self.assertIn("EXCLUDED_NONINVENTORY_REQUIRED", warning_codes)

        with self.assertRaisesRegex(ValueError, "explicit excluded-noninventory amount"):
            confirm_acquisition(
                self.db,
                result["acquisition"]["id"],
                {
                    "request_id": "HF1-REASON-ONLY",
                    "expected_revision": result["acquisition"]["revision"],
                    "confirm_authoritative_financial_facts": True,
                    "confirm_reconciliation": True,
                },
            )

        result = autosave_acquisition(
            self.db,
            result["acquisition"]["id"],
            {
                "request_id": "HF1-WRONG-EXCLUSION",
                "expected_revision": result["acquisition"]["revision"],
                "excluded_noninventory_cents": 2400,
                "noninventory_treatment_code": "MIXED_NONINVENTORY",
                "noninventory_notes": "Net noninventory portion of the final payment.",
            },
        )
        self.assertEqual(result["reconciliation"]["partition_difference_cents"], 17)
        with self.assertRaisesRegex(ValueError, "must equal final USD paid exactly"):
            confirm_acquisition(
                self.db,
                result["acquisition"]["id"],
                {
                    "request_id": "HF1-WRONG-CONFIRM",
                    "expected_revision": result["acquisition"]["revision"],
                    "confirm_authoritative_financial_facts": True,
                    "confirm_reconciliation": True,
                    "confirm_noninventory_exclusion": True,
                },
            )

        result = autosave_acquisition(
            self.db,
            result["acquisition"]["id"],
            {
                "request_id": "HF1-CORRECT-EXCLUSION",
                "expected_revision": result["acquisition"]["revision"],
                "excluded_noninventory_cents": 2417,
                "noninventory_treatment_code": "MIXED_NONINVENTORY",
                "noninventory_notes": "Net noninventory portion of the final payment.",
            },
        )
        self.assertTrue(result["reconciliation"]["partition_reconciled"])
        self.assertEqual(result["reconciliation"]["partition_difference_cents"], 0)
        self.assertTrue(result["readiness"]["ready_to_confirm"])

        with self.assertRaisesRegex(ValueError, "Explicit excluded-noninventory confirmation"):
            confirm_acquisition(
                self.db,
                result["acquisition"]["id"],
                {
                    "request_id": "HF1-MISSING-CHECKBOX",
                    "expected_revision": result["acquisition"]["revision"],
                    "confirm_authoritative_financial_facts": True,
                    "confirm_reconciliation": True,
                },
            )

        ready = confirm_acquisition(
            self.db,
            result["acquisition"]["id"],
            {
                "request_id": "HF1-CONFIRM",
                "expected_revision": result["acquisition"]["revision"],
                "confirm_authoritative_financial_facts": True,
                "confirm_reconciliation": True,
                "confirm_noninventory_exclusion": True,
            },
        )
        self.assertEqual(ready["acquisition"]["state"], "READY_FOR_INTAKE")
        self.assertEqual(sum(line["assigned_landed_cost_cents"] for line in ready["lines"]), 11000)
        self.assertEqual(ready["acquisition"]["excluded_noninventory_cents"], 2417)
        event = next(item for item in ready["events"] if item["event_type"] == "AUTHORITATIVE_CONFIRMATION")
        self.assertEqual(event["payload"]["calculation_version"], "inbound-acquisition-v2")
        self.assertEqual(event["payload"]["noninventory_partition"]["excluded_noninventory_cents"], 2417)
        self.assertTrue(event["payload"]["noninventory_partition"]["operator_confirmed"])

    def test_editing_confirmed_allocation_invalidates_backend_confirmation(self):
        result = self.mixed_purchase()
        line = result["lines"][0]
        self.assertEqual(line["allocation_status"], "CONFIRMED")
        result = autosave_acquisition_line(
            self.db,
            line["id"],
            {
                "request_id": "HF1-EDIT-CONFIRMED",
                "expected_revision": result["acquisition"]["revision"],
                "assigned_landed_cost_cents": 2999,
                "allocation_method": "MANUAL",
            },
        )
        edited = next(item for item in result["lines"] if item["id"] == line["id"])
        self.assertEqual(edited["allocation_status"], "UNALLOCATED")
        self.assertIn("LINE_COST_UNCONFIRMED", {item["code"] for item in result["readiness"]["warnings"]})


class MixedPurchaseMigrationTest(unittest.TestCase):
    def test_0015_preserves_confirmed_and_incomplete_rc3_rows_without_backfill(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        base_schema(db)
        self.assertEqual(apply_migrations(db, DEFAULT_MIGRATIONS[:-5])[-1], "0014_v22_phase7_sam_recognition")
        db.execute(
            """INSERT INTO acquisitions
               (acquisition_uuid,acquisition_code,creation_request_id,state,merchant_name,
                final_usd_paid_cents,financial_facts_confirmed,reconciliation_confirmed,
                created_at,updated_at)
               VALUES ('ACQ-CONFIRMED','ACQ-RC3-0001','RC3-CONFIRMED','READY_FOR_INTAKE',
                       'Preserved Shop',4200,1,1,'2026-08-15','2026-08-15')"""
        )
        db.execute(
            """INSERT INTO acquisitions
               (acquisition_uuid,acquisition_code,creation_request_id,state,merchant_name,
                final_usd_paid_cents,financial_facts_confirmed,reconciliation_confirmed,
                created_at,updated_at)
               VALUES ('ACQ-INCOMPLETE','ACQ-RC3-0002','RC3-INCOMPLETE','ACQUISITION_INCOMPLETE',
                       'Mom and Pop Shop',13417,0,0,'2026-08-16','2026-08-16')"""
        )
        before = [tuple(row) for row in db.execute(
            "SELECT acquisition_code,state,merchant_name,final_usd_paid_cents,financial_facts_confirmed,reconciliation_confirmed FROM acquisitions ORDER BY id"
        )]
        self.assertEqual(apply_migrations(db), ("0015_v22_rc3_hf1_mixed_purchase_reconciliation", "0016_v23_inventory_intelligence_phase1_receipt_semantics", "0017_v24_sam_phase1_family_printing", "0018_v24_jarvis_economics_sam_phase2", "0019_v24_sam_multi_evidence_operator_trial_v1a"))
        after = [tuple(row) for row in db.execute(
            "SELECT acquisition_code,state,merchant_name,final_usd_paid_cents,financial_facts_confirmed,reconciliation_confirmed FROM acquisitions ORDER BY id"
        )]
        self.assertEqual(after, before)
        for row in db.execute(
            "SELECT excluded_noninventory_cents,noninventory_treatment_code,noninventory_notes FROM acquisitions"
        ):
            self.assertEqual(tuple(row), (None, None, None))
        self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(apply_migrations(db), ())
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("UPDATE acquisitions SET noninventory_treatment_code='TAX_DEDUCTION' WHERE id=1")
        db.close()


if __name__ == "__main__":
    unittest.main()
