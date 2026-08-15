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
    cancel_acquisition_line,
    confirm_acquisition,
    confirm_line_allocation,
    create_acquisition,
    foundation_contract,
    mark_reconciliation_required,
)
from dex_migrations import DEFAULT_MIGRATIONS, apply_migrations
from tests.test_phase5_sealed import base_schema


class Phase2Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.db_path = root / "phase2-wizard.db"
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

    def create(self, **fields):
        defaults = {
            "source_scope": "DOMESTIC",
            "merchant_name": "Phase 2 Fixture Shop",
            "purchased_on": "2026-08-15",
            "payment_method": "CASH",
        }
        defaults.update(fields)
        return create_acquisition(self.db, {"request_id": "P2-CREATE", **defaults})

    def add_line(self, result, request_id="P2-LINE", **fields):
        return add_acquisition_line(
            self.db,
            result["acquisition"]["id"],
            {
                "request_id": request_id,
                "expected_revision": result["acquisition"]["revision"],
                **fields,
            },
        )


class Phase2MigrationTest(unittest.TestCase):
    def test_phase2_progress_migration_is_additive_and_resumable(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        base_schema(db)
        apply_migrations(db, DEFAULT_MIGRATIONS[:7])
        db.execute(
            """INSERT INTO acquisitions
               (acquisition_uuid,acquisition_code,creation_request_id,created_at,updated_at)
               VALUES ('ACQ-LEGACY-DRAFT','ACQ-LEGACY-0001','LEGACY-DRAFT','2026-08-15','2026-08-15')"""
        )
        db.execute("INSERT INTO batches (id,batch_code,total_cost) VALUES (1,'P7C-UNCHANGED',42.50)")
        before = tuple(db.execute("SELECT id,batch_code,total_cost FROM batches").fetchone())
        self.assertEqual(apply_migrations(db), ("0008_v22_phase2_ux_revision", "0009_v22_phase3_product_catalog_upc"))
        self.assertEqual(db.execute("SELECT wizard_step FROM acquisitions").fetchone()[0], "ACQUIRE")
        self.assertEqual(db.execute("SELECT payment_method FROM acquisitions").fetchone()[0], "")
        self.assertEqual(tuple(db.execute("SELECT id,batch_code,total_cost FROM batches").fetchone()), before)
        self.assertEqual(apply_migrations(db), ())
        db.close()


class Phase2ServiceTest(Phase2Fixture):
    def test_wizard_progress_autosaves_without_confirming_or_resetting_reconciliation(self):
        result = self.create()
        result = self.add_line(result, product_class="PACK_PRODUCT")
        result = mark_reconciliation_required(
            self.db,
            result["acquisition"]["id"],
            {
                "request_id": "P2-RECON-STATE",
                "expected_revision": result["acquisition"]["revision"],
            },
        )
        result = autosave_acquisition(
            self.db,
            result["acquisition"]["id"],
            {
                "request_id": "P2-PROGRESS",
                "expected_revision": result["acquisition"]["revision"],
                "wizard_step": "REVIEW",
            },
        )
        self.assertEqual(result["acquisition"]["wizard_step"], "REVIEW")
        self.assertEqual(result["acquisition"]["state"], "RECONCILIATION_REQUIRED")
        self.assertFalse(result["acquisition"]["financial_facts_confirmed"])
        self.assertFalse(result["acquisition"]["reconciliation_confirmed"])

    def test_multiple_lines_remain_independent_and_draft_removal_is_durable(self):
        result = self.create(final_usd_paid_cents=2500)
        result = self.add_line(result, product_class="PACK_PRODUCT", product_name="Pack A")
        result = self.add_line(
            result,
            request_id="P2-LINE-2",
            product_class="SEALED_PRODUCT",
            product_name="Box B",
        )
        removed_id = result["lines"][0]["id"]
        result = cancel_acquisition_line(
            self.db,
            removed_id,
            {
                "request_id": "P2-REMOVE",
                "expected_revision": result["acquisition"]["revision"],
            },
        )
        self.assertIsNotNone(result["lines"][0]["canceled_at"])
        self.assertIsNone(result["lines"][1]["canceled_at"])
        event = next(event for event in result["events"] if event["request_id"] == "P2-REMOVE")
        self.assertEqual(event["reason_code"], "DRAFT_LINE_REMOVED")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM batches").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sealed_units").fetchone()[0], 0)

    def test_editing_line_cost_invalidates_prior_allocation_confirmation(self):
        result = self.create(purchase_subtotal_cents=1000, final_usd_paid_cents=1000)
        result = self.add_line(
            result,
            product_class="PACK_PRODUCT",
            game="One Piece",
            product_name="OP16 Pack",
            quantity=2,
            quantity_certainty="KNOWN",
        )
        result = confirm_line_allocation(
            self.db,
            result["lines"][0]["id"],
            {
                "request_id": "P2-ALLOC",
                "expected_revision": result["acquisition"]["revision"],
                "assigned_landed_cost_cents": 1000,
                "allocation_method": "EQUAL",
                "confirm_allocation": True,
            },
        )
        result = autosave_acquisition_line(
            self.db,
            result["lines"][0]["id"],
            {
                "request_id": "P2-EDIT-COST",
                "expected_revision": result["acquisition"]["revision"],
                "assigned_landed_cost_cents": 999,
            },
        )
        self.assertEqual(result["lines"][0]["allocation_status"], "UNALLOCATED")
        self.assertFalse(result["reconciliation"]["allocation_reconciled"])

    def test_explicit_zero_requires_reason_and_can_be_authoritatively_confirmed(self):
        result = self.create(final_usd_paid_cents=0)
        result = self.add_line(
            result,
            product_class="SINGLE_CARDS",
            game="One Piece",
            set_code="Promo",
            quantity=3,
            quantity_certainty="KNOWN",
            singles_cost_mode="LUMP_SUM",
            intended_action="INVENTORY_SINGLES",
        )
        result = confirm_line_allocation(
            self.db,
            result["lines"][0]["id"],
            {
                "request_id": "P2-ZERO-ALLOC",
                "expected_revision": result["acquisition"]["revision"],
                "assigned_landed_cost_cents": 0,
                "allocation_method": "EQUAL",
                "confirm_allocation": True,
            },
        )
        self.assertIn("ZERO_COST_REASON_REQUIRED", {item["code"] for item in result["readiness"]["warnings"]})
        self.assertEqual(result["attention"]["decision_level"], "NEEDS_ATTENTION")
        self.assertEqual(result["attention"]["resolve_mode"], "ZERO_COST")
        result = autosave_acquisition(
            self.db,
            result["acquisition"]["id"],
            {
                "request_id": "P2-ZERO-REASON",
                "expected_revision": result["acquisition"]["revision"],
                "discrepancy_reason_code": "EXPLICIT_ZERO_COST",
            },
        )
        self.assertTrue(result["readiness"]["ready_to_confirm"])
        ready = confirm_acquisition(
            self.db,
            result["acquisition"]["id"],
            {
                "request_id": "P2-ZERO-CONFIRM",
                "expected_revision": result["acquisition"]["revision"],
                "confirm_authoritative_financial_facts": True,
                "confirm_reconciliation": True,
                "confirm_zero_cost": True,
            },
        )
        self.assertEqual(ready["acquisition"]["state"], "READY_FOR_INTAKE")
        self.assertEqual(ready["readiness"]["authoritative_cost_label"], "$0.00")
        self.assertEqual(ready["attention"]["decision_level"], "AUTOMATIC_VISIBLE")
        self.assertEqual(ready["projection"]["batch_ids"], [])

    def test_readiness_and_per_unit_values_are_backend_generated(self):
        result = self.create(purchase_subtotal_cents=1000, final_usd_paid_cents=1000)
        result = self.add_line(
            result,
            product_class="SEALED_PRODUCT",
            game="Pokemon",
            product_name="Three collection boxes",
            quantity=3,
            quantity_certainty="KNOWN",
        )
        result = confirm_line_allocation(
            self.db,
            result["lines"][0]["id"],
            {
                "request_id": "P2-CENTS",
                "expected_revision": result["acquisition"]["revision"],
                "assigned_landed_cost_cents": 1000,
                "allocation_method": "EQUAL",
                "confirm_allocation": True,
            },
        )
        per_unit = result["lines"][0]["per_unit_cost"]
        self.assertEqual((per_unit["base_cents"], per_unit["remainder_units"]), (333, 1))
        self.assertTrue(result["readiness"]["ready_to_confirm"])

    def test_single_line_confirmation_assigns_all_cost_and_records_audit_event(self):
        result = self.create(purchase_subtotal_cents=1000, final_usd_paid_cents=1000)
        result = self.add_line(
            result,
            product_class="SEALED_PRODUCT",
            game="Pokemon",
            set_code="Journey Together",
            product_name="Booster Box",
            quantity=3,
        )
        preview = result["automatic_single_line_allocation_preview"]
        self.assertEqual(preview["assigned_landed_cost_cents"], 1000)
        self.assertEqual(preview["allocation_method"], "SINGLE_LINE_100_PERCENT")
        self.assertEqual((preview["per_unit_cost"]["base_cents"], preview["per_unit_cost"]["remainder_units"]), (333, 1))
        self.assertEqual(preview["decision_level"], "AUTOMATIC_VISIBLE")
        self.assertEqual(result["attention"]["decision_level"], "AUTOMATIC_VISIBLE")
        ready = confirm_acquisition(
            self.db,
            result["acquisition"]["id"],
            {
                "request_id": "P2-AUTO-CONFIRM",
                "expected_revision": result["acquisition"]["revision"],
                "confirm_authoritative_financial_facts": True,
                "confirm_reconciliation": True,
            },
        )
        self.assertEqual(ready["lines"][0]["assigned_landed_cost_cents"], 1000)
        self.assertEqual(ready["lines"][0]["allocation_method"], "SINGLE_LINE_100_PERCENT")
        audit = next(event for event in ready["events"] if event["reason_code"] == "SINGLE_LINE_100_PERCENT")
        self.assertTrue(audit["payload"]["automatic"])
        self.assertEqual(audit["payload"]["calculation_version"], "inbound-acquisition-v1")
        self.assertEqual(audit["payload"]["source_facts"]["final_usd_paid_cents"], 1000)
        self.assertEqual(audit["payload"]["source_facts"]["quantity"], 3)
        self.assertEqual(audit["payload"]["result"]["assigned_landed_cost_cents"], 1000)
        self.assertEqual(audit["payload"]["result"]["per_unit_cost"]["remainder_units"], 1)
        confirmation = next(event for event in ready["events"] if event["event_type"] == "AUTHORITATIVE_CONFIRMATION")
        self.assertEqual(confirmation["payload"]["calculation_version"], "inbound-acquisition-v1")
        self.assertEqual(confirmation["payload"]["automatic_allocation_event_id"], audit["event_id"])
        self.assertTrue(confirmation["payload"]["operator_confirmed_acquisition"])
        self.assertEqual(ready["projection"]["batch_ids"], [])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM batches").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM cards").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sealed_units").fetchone()[0], 0)

    def test_unresolved_multi_line_allocation_is_needs_attention_and_cannot_confirm(self):
        result = self.create(purchase_subtotal_cents=3000, final_usd_paid_cents=3000)
        result = self.add_line(
            result,
            product_class="PACK_PRODUCT",
            game="One Piece",
            set_code="OP16",
            product_name="Single Pack",
            quantity=2,
        )
        result = self.add_line(
            result,
            request_id="P2-MULTI-2",
            product_class="SEALED_PRODUCT",
            game="One Piece",
            set_code="ST27",
            product_name="Starter Deck",
            quantity=1,
        )
        self.assertEqual(result["attention"]["decision_level"], "NEEDS_ATTENTION")
        self.assertEqual(result["attention"]["attention_level"], "REVIEW")
        self.assertEqual(result["attention"]["resolve_mode"], "MULTI_LINE_ALLOCATION")
        self.assertIn("ALLOCATION_NOT_RECONCILED", result["attention"]["reason_codes"])
        with self.assertRaisesRegex(ValueError, "landed-cost allocation is not confirmed"):
            confirm_acquisition(
                self.db,
                result["acquisition"]["id"],
                {
                    "request_id": "P2-MULTI-BLOCKED",
                    "expected_revision": result["acquisition"]["revision"],
                    "confirm_authoritative_financial_facts": True,
                    "confirm_reconciliation": True,
                },
            )
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM batches").fetchone()[0], 0)

    def test_missing_cost_and_severe_conflict_publish_attention_metadata(self):
        missing = self.create()
        missing = self.add_line(
            missing,
            product_class="SINGLE_CARDS",
            game="Pokemon",
            set_code="Journey Together",
            quantity=4,
        )
        self.assertEqual(missing["attention"]["decision_level"], "NEEDS_ATTENTION")
        self.assertEqual(missing["attention"]["attention_level"], "CRITICAL")
        self.assertEqual(missing["attention"]["resolve_mode"], "INCOMPLETE_FACTS")

        severe = create_acquisition(
            self.db,
            {
                "request_id": "P2-SEVERE-CREATE",
                "source_scope": "DOMESTIC",
                "merchant_name": "Conflict Shop",
                "purchased_on": "2026-08-15",
                "payment_method": "CASH",
                "purchase_subtotal_cents": 10000,
                "final_usd_paid_cents": 1000,
            },
        )
        severe = self.add_line(
            severe,
            request_id="P2-SEVERE-LINE",
            product_class="SEALED_PRODUCT",
            game="Pokemon",
            set_code="JTG",
            product_name="Booster Box",
            quantity=1,
        )
        self.assertTrue(severe["reconciliation"]["extreme"])
        self.assertEqual(severe["attention"]["decision_level"], "NEEDS_ATTENTION")
        self.assertEqual(severe["attention"]["attention_level"], "CRITICAL")
        self.assertEqual(severe["attention"]["resolve_mode"], "PURCHASE_DISCREPANCY")

    def test_phase2_contract_keeps_later_features_out_of_scope(self):
        contract = foundation_contract()
        self.assertEqual(contract["phase"], "INBOUND_2_PHASE_3_PRODUCT_CATALOG_UPC")
        self.assertEqual(contract["wizard_steps"], ["ACQUIRE", "PRODUCTS", "REVIEW"])
        self.assertIn("SOURCE", contract["legacy_persisted_wizard_steps"])
        self.assertIn("CREDIT_DEBIT_CARD", contract["payment_methods"])
        self.assertEqual(contract["decision_levels"], ["AUTOMATIC", "AUTOMATIC_VISIBLE", "NEEDS_ATTENTION"])
        self.assertEqual(contract["calculation_version"], "inbound-acquisition-v1")
        boundaries = contract["phase_2_boundaries"]
        self.assertTrue(boundaries["operator_workflow_replaced"])
        self.assertTrue(boundaries["legacy_batch_workflow_available"])
        self.assertTrue(boundaries["upc_catalog"])
        self.assertFalse(boundaries["documents_or_extraction"])
        self.assertFalse(boundaries["sam"])
        self.assertFalse(boundaries["batch_projection"])


if __name__ == "__main__":
    unittest.main()
