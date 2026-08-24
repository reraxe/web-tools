import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import app
from dex_inbound import (
    add_acquisition_line,
    autosave_acquisition,
    confirm_acquisition,
    confirm_line_allocation,
    create_acquisition,
    foundation_contract,
    mark_reconciliation_required,
)
from dex_migrations import DEFAULT_MIGRATIONS, MigrationError, apply_migrations
from tests.test_phase5_sealed import base_schema


class InboundFoundationFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.db_path = root / "inbound-phase1.db"
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

    def _create(self, request="CREATE-1", **fields):
        defaults = {
            "source_scope": "DOMESTIC",
            "merchant_name": "Phase 1 Fixture Shop",
            "purchased_on": "2026-08-15",
            "payment_method": "CASH",
        }
        defaults.update(fields)
        return create_acquisition(self.db, {"request_id": request, **defaults})

    def _add_line(self, acquisition, request="LINE-1", **fields):
        return add_acquisition_line(
            self.db,
            acquisition["acquisition"]["id"],
            {
                "request_id": request,
                "expected_revision": acquisition["acquisition"]["revision"],
                **fields,
            },
        )


class InboundPhase1MigrationTest(unittest.TestCase):
    def test_additive_migration_preserves_phase7c_rows_and_runs_once(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        base_schema(db)
        apply_migrations(db, DEFAULT_MIGRATIONS[:5])
        db.execute(
            "INSERT INTO batches (id,batch_code,total_cost) VALUES (1,'P7C-PRESERVED',42.50)"
        )
        db.execute("INSERT INTO cards (id,sku,batch_id) VALUES (1,'P7C-CARD',1)")
        before = tuple(db.execute("SELECT id,batch_code,total_cost FROM batches").fetchone())
        self.assertEqual(
            apply_migrations(db),
                ("0006_v22_phase1_inbound_acquisitions", "0007_v22_phase2_manual_acquisition_wizard", "0008_v22_phase2_ux_revision", "0009_v22_phase3_product_catalog_upc", "0010_v22_phase4_source_documents", "0011_v22_phase5_receipt_intelligence", "0012_v22_prephase_ux_safety_hotfix", "0013_v22_phase6_downstream_intake_bridge", "0014_v22_phase7_sam_recognition", "0015_v22_rc3_hf1_mixed_purchase_reconciliation", "0016_v23_inventory_intelligence_phase1_receipt_semantics", "0017_v24_sam_phase1_family_printing", "0018_v24_jarvis_economics_sam_phase2"),
        )
        self.assertEqual(tuple(db.execute("SELECT id,batch_code,total_cost FROM batches").fetchone()), before)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM acquisitions").fetchone()[0], 0)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM acquisition_lines").fetchone()[0], 0)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM acquisition_events").fetchone()[0], 0)
        self.assertIn("acquisition_line_id", {row[1] for row in db.execute("PRAGMA table_info(batches)")})
        self.assertIsNone(db.execute("SELECT acquisition_line_id FROM batches WHERE id=1").fetchone()[0])
        self.assertEqual(apply_migrations(db), ())
        db.close()

    def test_failed_migration_rolls_back_tables_linkage_and_marker(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        base_schema(db)
        apply_migrations(db, DEFAULT_MIGRATIONS[:5])
        db.execute("CREATE TABLE acquisition_lines (sentinel TEXT)")
        db.commit()
        with self.assertRaises(MigrationError):
            apply_migrations(db)
        self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='acquisitions'").fetchone())
        self.assertEqual([row[1] for row in db.execute("PRAGMA table_info(acquisition_lines)")], ["sentinel"])
        self.assertNotIn("acquisition_line_id", {row[1] for row in db.execute("PRAGMA table_info(batches)")})
        self.assertIsNone(db.execute("SELECT 1 FROM schema_migrations WHERE migration_id='0006_v22_phase1_inbound_acquisitions'").fetchone())
        db.close()


class InboundPhase1ServiceTest(InboundFoundationFixture):
    def test_draft_is_immediate_immutable_idempotent_and_missing_cost_stays_unknown(self):
        result = self._create(merchant_name="Demo Shop")
        acquisition = result["acquisition"]
        self.assertTrue(acquisition["acquisition_uuid"].startswith("ACQ-"))
        self.assertEqual(acquisition["state"], "ACQUISITION_INCOMPLETE")
        self.assertIsNone(acquisition["final_usd_paid_cents"])
        self.assertFalse(acquisition["financial_facts_confirmed"])
        self.assertFalse(acquisition["reconciliation_confirmed"])
        replay = self._create(merchant_name="Should not overwrite")
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(replay["acquisition"]["acquisition_uuid"], acquisition["acquisition_uuid"])
        self.assertEqual(replay["acquisition"]["merchant_name"], "Demo Shop")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM batches").fetchone()[0], 0)
        with self.assertRaisesRegex(ValueError, "never treated as \\$0.00"):
            confirm_acquisition(
                self.db,
                acquisition["id"],
                {
                    "request_id": "CONFIRM-MISSING",
                    "expected_revision": acquisition["revision"],
                    "confirm_authoritative_financial_facts": True,
                    "confirm_reconciliation": True,
                },
            )

    def test_autosave_never_confirms_and_rejects_confirmation_fields(self):
        result = self._create()
        saved = autosave_acquisition(
            self.db,
            result["acquisition"]["id"],
            {
                "request_id": "SAVE-1",
                "expected_revision": 1,
                "source_scope": "domestic",
                "final_usd_paid_cents": 1000,
            },
        )
        self.assertEqual(saved["acquisition"]["state"], "ACQUISITION_INCOMPLETE")
        self.assertFalse(saved["acquisition"]["financial_facts_confirmed"])
        self.assertFalse(saved["acquisition"]["reconciliation_confirmed"])
        with self.assertRaisesRegex(ValueError, "Autosave cannot confirm"):
            autosave_acquisition(
                self.db,
                saved["acquisition"]["id"],
                {
                    "request_id": "SAVE-BAD",
                    "expected_revision": 2,
                    "financial_facts_confirmed": True,
                },
            )

    def test_multiple_broad_product_classes_confirm_without_projecting_batches(self):
        result = self._create(
            source_scope="DOMESTIC",
            purchase_subtotal_cents=10000,
            final_usd_paid_cents=10000,
        )
        result = self._add_line(
            result,
            request="LINE-PACK",
            product_class="PACK_PRODUCT",
            game="One Piece",
            product_name="OP16 Sleeved Pack",
            set_code="OP16",
            pack_type="SLEEVED",
            quantity=10,
            quantity_certainty="KNOWN",
            intended_action="KEEP_SEALED",
        )
        result = self._add_line(
            result,
            request="LINE-SEALED",
            product_class="SEALED_PRODUCT",
            game="One Piece",
            product_name="ST27 Starter Deck",
            quantity=2,
            quantity_certainty="KNOWN",
            intended_action="RIP_OPEN",
        )
        for index, cents in ((0, 6000), (1, 4000)):
            line = result["lines"][index]
            result = confirm_line_allocation(
                self.db,
                line["id"],
                {
                    "request_id": f"ALLOC-{index}",
                    "expected_revision": result["acquisition"]["revision"],
                    "assigned_landed_cost_cents": cents,
                    "allocation_method": "MANUAL",
                    "confirm_allocation": True,
                },
            )
        result = mark_reconciliation_required(
            self.db,
            result["acquisition"]["id"],
            {
                "request_id": "RECONCILE-1",
                "expected_revision": result["acquisition"]["revision"],
            },
        )
        ready = confirm_acquisition(
            self.db,
            result["acquisition"]["id"],
            {
                "request_id": "CONFIRM-1",
                "expected_revision": result["acquisition"]["revision"],
                "confirm_authoritative_financial_facts": True,
                "confirm_reconciliation": True,
            },
        )
        self.assertEqual(ready["acquisition"]["state"], "READY_FOR_INTAKE")
        self.assertEqual([line["product_class"] for line in ready["lines"]], ["PACK_PRODUCT", "SEALED_PRODUCT"])
        self.assertEqual(ready["reconciliation"]["allocation_difference_cents"], 0)
        self.assertEqual(ready["projection"]["status"], "NOT_IMPLEMENTED_PHASE_1")
        self.assertEqual(ready["projection"]["batch_ids"], [])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sealed_units").fetchone()[0], 0)

    def test_suggestions_are_non_authoritative_and_extreme_difference_needs_escalation(self):
        result = self._create(
            source_scope="DOMESTIC",
            purchase_subtotal_cents=10000,
            final_usd_paid_cents=1000,
            discrepancy_reason_code="MERCHANT_TOTAL_CONTROLS",
            discrepancy_notes="Disposable extreme-discrepancy review.",
        )
        result = self._add_line(
            result,
            product_class="SINGLE_CARDS",
            game="One Piece",
            product_name="Singles lot",
            set_code="OP16",
            quantity=10,
            quantity_certainty="ESTIMATED",
            singles_cost_mode="LUMP_SUM",
            assigned_landed_cost_cents=1000,
            allocation_method="EQUAL",
        )
        self.assertEqual(result["lines"][0]["allocation_status"], "SUGGESTED")
        self.assertTrue(result["reconciliation"]["extreme"])
        self.assertEqual(result["reconciliation"]["severity"], "EXTREME")
        self.assertEqual(result["automatic_single_line_allocation_preview"]["allocation_method"], "SINGLE_LINE_100_PERCENT")
        self.assertFalse(result["acquisition"]["financial_facts_confirmed"])
        common = {
            "expected_revision": result["acquisition"]["revision"],
            "confirm_authoritative_financial_facts": True,
            "confirm_reconciliation": True,
            "confirm_material_discrepancy": True,
            "reentered_final_usd_paid_cents": 1000,
        }
        with self.assertRaisesRegex(ValueError, "severe-escalation"):
            confirm_acquisition(self.db, result["acquisition"]["id"], {"request_id": "CONFIRM-NO-EXTREME", **common})
        ready = confirm_acquisition(
            self.db,
            result["acquisition"]["id"],
            {"request_id": "CONFIRM-EXTREME", "confirm_extreme_discrepancy": True, **common},
        )
        self.assertEqual(ready["acquisition"]["state"], "READY_FOR_INTAKE")


class InboundPhase1ApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patches = (
            patch.object(app, "DB_PATH", root / "dex.db"),
            patch.object(app, "DATA_DIR", root),
            patch.object(app, "IMAGE_DIR", root / "images"),
            patch.object(app, "INBOUND_DIR", root / "inbound"),
            patch.object(app, "SOURCE_DB_DIR", root / "source"),
        )
        for item in self.patches:
            item.start()
        app.init_db()
        self.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.DexHandler)
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.thread.join(timeout=3); self.server.server_close()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def request(self, path, method="GET", body=None):
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())

    def test_foundation_contract_and_draft_api_remain_compatible_with_phase2_ui(self):
        status, contract = self.request("/api/inbound/foundation")
        self.assertEqual(status, 200)
        self.assertEqual(contract, foundation_contract())
        self.assertIn("PACK_PRODUCT", contract["product_classes"])
        self.assertIn("PERSONAL_NONBUSINESS", contract["receipt_line_classifications"])
        status, created = self.request(
            "/api/acquisitions", "POST", {"request_id": "API-CREATE", "merchant_name": "API Shop"}
        )
        self.assertEqual(status, 201)
        self.assertEqual(created["acquisition"]["state"], "ACQUISITION_INCOMPLETE")
        _, listed = self.request("/api/acquisitions")
        self.assertEqual(len(listed["acquisitions"]), 1)
        _, detail = self.request(f"/api/acquisitions/{created['acquisition']['id']}")
        self.assertEqual(detail["acquisition"]["acquisition_uuid"], created["acquisition"]["acquisition_uuid"])
        index = (Path(__file__).parents[1] / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function newBatchForm()", index)
        self.assertIn("function renderAcquisitionWizard", index)
        self.assertTrue(contract["phase_2_boundaries"]["operator_workflow_replaced"])
        self.assertTrue(contract["phase_2_boundaries"]["legacy_batch_workflow_available"])

    def test_draft_recycle_list_and_restore_api_preserve_tombstone(self):
        _, created = self.request(
            "/api/acquisitions", "POST", {"request_id": "API-REMOVE-CREATE", "merchant_name": "Recycle API Shop"}
        )
        acquisition_id = created["acquisition"]["id"]
        _, recycled = self.request(
            f"/api/acquisitions/{acquisition_id}/recycle",
            "POST",
            {
                "request_id": "API-REMOVE-RECYCLE",
                "expected_revision": created["acquisition"]["revision"],
                "reason_code": "TEST_OR_TRAINING_ENTRY",
                "notes": "Disposable API regression",
            },
        )
        self.assertEqual(recycled["acquisition"]["state"], "CANCELED")
        _, active = self.request("/api/acquisitions")
        self.assertEqual(active["acquisitions"], [])
        _, recycle = self.request("/api/recycle?q=Recycle%20API")
        self.assertEqual([item["id"] for item in recycle["acquisitions"]], [acquisition_id])
        self.assertEqual(recycle["cards"], [])
        _, restored = self.request(
            f"/api/acquisitions/{acquisition_id}/restore",
            "POST",
            {
                "request_id": "API-REMOVE-RESTORE",
                "expected_revision": recycled["acquisition"]["revision"],
            },
        )
        self.assertEqual(restored["acquisition"]["state"], "ACQUISITION_INCOMPLETE")
        self.assertEqual(len(restored["events"]), 3)


class InboundPhase1PackagingTest(unittest.TestCase):
    def test_runtime_package_and_version_contract(self):
        root = Path(__file__).parents[1]
        dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
        index = (root / "static" / "index.html").read_text(encoding="utf-8")
        self.assertEqual((root / "VERSION").read_text(encoding="utf-8").strip(), "v2.4-test")
        self.assertIn("COPY dex_inbound.py ./", dockerfile)
        self.assertIn('RUN python -c "import dex_inbound"', dockerfile)
        self.assertIn("COPY dex_catalog.py ./", dockerfile)
        self.assertIn('RUN python -c "import dex_catalog"', dockerfile)
        self.assertIn("v2.2-test-inbound-phase6-intake-bridge", index)
        self.assertEqual(DEFAULT_MIGRATIONS[-1].migration_id, "0018_v24_jarvis_economics_sam_phase2")


if __name__ == "__main__":
    unittest.main()
