import json
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

import app
from dex_catalog import create_catalog_product
from dex_inbound import acquisition_removal_eligibility
from dex_intake_bridge import confirm_intake_routing, intake_preview, intake_status
from dex_migrations import DEFAULT_MIGRATIONS, MigrationError, apply_migrations
from dex_portfolio_economics import portfolio_economics_payload
from dex_rip import finalize_rip
from dex_sealed import sealed_sale_preview
from tests.test_phase5_sealed import base_schema


class Phase6BridgeFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db_path = self.root / "dex.db"
        with patch.object(app, "DB_PATH", self.db_path), patch.object(app, "DATA_DIR", self.root), patch.object(app, "IMAGE_DIR", self.root / "images"), patch.object(app, "INBOUND_DIR", self.root / "inbound"), patch.object(app, "SOURCE_DB_DIR", self.root / "source"):
            app.init_db()
        self.db = sqlite3.connect(self.db_path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def acquisition(self, lines):
        now = "2026-08-15T12:00:00+00:00"
        total = sum(line["cost"] for line in lines)
        cursor = self.db.execute(
            """INSERT INTO acquisitions
               (acquisition_uuid,acquisition_code,creation_request_id,state,revision,source_scope,
                merchant_name,purchased_on,order_reference,final_usd_paid_cents,
                financial_facts_confirmed,reconciliation_confirmed,confirmed_at,created_at,updated_at,payment_method)
               VALUES ('ACQ-UUID-6','ACQ-20260815-0001','CREATE-6','READY_FOR_INTAKE',7,'DOMESTIC',
                       'Bridge Shop','2026-08-15','ORDER-6',?,1,1,?,?,?,'CREDIT_DEBIT_CARD')""",
            (total, now, now, now),
        )
        acquisition_id = int(cursor.lastrowid)
        for sequence, line in enumerate(lines, 1):
            self.db.execute(
                """INSERT INTO acquisition_lines
                   (line_uuid,acquisition_id,line_sequence,product_class,game,product_name,set_code,
                    pack_type,quantity,quantity_certainty,singles_cost_mode,intended_action,
                    assigned_landed_cost_cents,allocation_method,allocation_status,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,'KNOWN',?,'DECIDE_LATER',?,'MANUAL','CONFIRMED',?,?)""",
                (f"LINE-UUID-{sequence}", acquisition_id, sequence, line["class"], "One Piece",
                 line["name"], "OP16", line.get("pack_type", ""), line["quantity"],
                 line.get("singles_mode", ""), line["cost"], now, now),
            )
        self.db.commit()
        return acquisition_id

    def confirm(self, acquisition_id, lines, request="ROUTE-1"):
        revision = intake_status(self.db, acquisition_id)["revision"]
        payload = {"expected_revision": revision, "lines": lines}
        preview = intake_preview(self.db, acquisition_id, payload)
        return confirm_intake_routing(self.db, acquisition_id, {
            **payload, "request_id": request, "preview_token": preview["preview_token"],
            "confirm_routing": True,
        })


class Phase6BridgeTest(Phase6BridgeFixture):
    def test_partial_sealed_routing_uses_exact_units_and_blocks_pending_sale(self):
        acquisition_id = self.acquisition([
            {"class": "SEALED_PRODUCT", "name": "OP16 Booster Box", "quantity": 3, "cost": 1000}
        ])
        line_id = self.db.execute("SELECT id FROM acquisition_lines").fetchone()[0]
        catalog = create_catalog_product(self.db, {
            "request_id": "CATALOG-P6", "game": "One Piece", "display_name": "OP16 Booster Box",
            "set_code": "OP16", "product_class": "SEALED_PRODUCT", "product_subtype": "Booster Box",
            "provenance": "OPERATOR_CONFIRMED",
        })
        self.db.execute("UPDATE acquisition_lines SET catalog_product_id=? WHERE id=?", (catalog["id"], line_id))
        result = self.confirm(acquisition_id, [{
            "line_id": line_id, "rip_open_quantity": 1, "keep_sealed_quantity": 1,
        }])
        self.assertEqual(result["state"], "INTAKE_IN_PROGRESS")
        self.assertEqual(result["summary"]["quantity_undecided"], 1)
        self.assertEqual(result["lines"][0]["basis"]["rip_open_cents"], 334)
        self.assertEqual(result["lines"][0]["basis"]["keep_sealed_cents"], 333)
        self.assertEqual(self.db.execute(
            "SELECT catalog_product_id FROM acquisition_line_projections WHERE acquisition_line_id=?", (line_id,)
        ).fetchone()[0], catalog["id"])
        self.assertTrue(acquisition_removal_eligibility(self.db, acquisition_id)["protected_history"])
        portfolio = portfolio_economics_payload(self.db)
        self.assertEqual(portfolio["summary"]["authoritative_acquisition_cost_cents"], 1000)
        self.assertEqual(portfolio["scope"]["finalized_batch_count"], 1)
        units = self.db.execute(
            "SELECT unit_sequence,basis_cents,status,intake_disposition FROM sealed_units ORDER BY unit_sequence"
        ).fetchall()
        self.assertEqual([tuple(row) for row in units], [
            (1, 334, "OPENED", "RIP_OPEN"),
            (2, 333, "REMAINING", "KEEP_SEALED"),
            (3, 333, "REMAINING", "PENDING"),
        ])
        batch_id = result["lines"][0]["batch_id"]
        sale = sealed_sale_preview(self.db, {
            "batch_id": batch_id, "quantity": 1, "merchandise_total": "5.00",
            "shipping_collected": "0", "marketplace_fees": "0", "actual_postage": "0",
            "marketplace_tax": "0",
        })
        self.assertEqual([unit["unit_sequence"] for unit in sale["sealed_units"]], [2])
        replay = confirm_intake_routing(self.db, acquisition_id, {
            "request_id": "ROUTE-1", "expected_revision": 7, "lines": [{
                "line_id": line_id, "rip_open_quantity": 1, "keep_sealed_quantity": 1,
            }], "preview_token": "ignored-on-replay", "confirm_routing": True,
        })
        self.assertEqual(replay["summary"]["quantity_routed"], 2)
        completed = self.confirm(acquisition_id, [{"line_id": line_id, "keep_sealed_quantity": 1}], "ROUTE-2")
        self.assertEqual(completed["state"], "INTAKE_COMPLETE")
        self.assertEqual(completed["summary"]["difference_cents"], 0)

    def test_pack_and_sealed_lines_project_to_distinct_batches(self):
        acquisition_id = self.acquisition([
            {"class": "PACK_PRODUCT", "name": "OP16 Sleeved Pack", "quantity": 2, "cost": 800, "pack_type": "Sleeved Pack"},
            {"class": "SEALED_PRODUCT", "name": "OP16 Double Pack", "quantity": 1, "cost": 1200},
        ])
        lines = self.db.execute("SELECT id FROM acquisition_lines ORDER BY line_sequence").fetchall()
        result = self.confirm(acquisition_id, [
            {"line_id": lines[0][0], "keep_sealed_quantity": 2},
            {"line_id": lines[1][0], "rip_open_quantity": 1},
        ])
        self.assertEqual(result["state"], "INTAKE_COMPLETE")
        self.assertEqual(len({line["batch_id"] for line in result["lines"]}), 2)
        pack_batch = self.db.execute("SELECT acquisition_type,product_name FROM batches WHERE acquisition_line_id=?", (lines[0][0],)).fetchone()
        self.assertEqual(tuple(pack_batch), ("Pack Product", "OP16 Sleeved Pack"))

    def test_singles_route_creates_one_pending_allocation_session_and_requires_complete_route_to_finalize(self):
        acquisition_id = self.acquisition([
            {"class": "SINGLE_CARDS", "name": "OP16 Singles Lot", "quantity": 4, "cost": 999, "singles_mode": "LUMP_SUM"}
        ])
        line_id = self.db.execute("SELECT id FROM acquisition_lines").fetchone()[0]
        result = self.confirm(acquisition_id, [{"line_id": line_id, "scan_identify_quantity": 2}])
        batch_id = result["lines"][0]["batch_id"]
        rip_id = self.db.execute("SELECT id FROM rip_sessions WHERE batch_id=?", (batch_id,)).fetchone()[0]
        self.assertEqual(self.db.execute("SELECT status FROM rip_sessions WHERE id=?", (rip_id,)).fetchone()[0], "DRAFT")
        with self.assertRaisesRegex(ValueError, "Finish routing"):
            finalize_rip(self.db, rip_id, {"confirm_all_cards_accounted": True, "confirm_finalization": True})
        completed = self.confirm(acquisition_id, [{"line_id": line_id, "scan_identify_quantity": 2}], "ROUTE-SINGLES-2")
        self.assertEqual(completed["state"], "INTAKE_COMPLETE")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM rip_sessions WHERE batch_id=?", (batch_id,)).fetchone()[0], 1)

    def test_stale_concurrent_route_cannot_project_or_consume_twice(self):
        acquisition_id = self.acquisition([
            {"class": "SEALED_PRODUCT", "name": "Concurrent Box", "quantity": 2, "cost": 501}
        ])
        line_id = self.db.execute("SELECT id FROM acquisition_lines").fetchone()[0]
        stale_payload = {"expected_revision": 7, "lines": [{"line_id": line_id, "keep_sealed_quantity": 1}]}
        stale_preview = intake_preview(self.db, acquisition_id, stale_payload)
        self.confirm(acquisition_id, [{"line_id": line_id, "keep_sealed_quantity": 1}], "ROUTE-WINNER")
        self.db.commit()
        second = sqlite3.connect(self.db_path, timeout=2)
        second.row_factory = sqlite3.Row
        second.execute("PRAGMA foreign_keys=ON")
        try:
            second.execute("BEGIN IMMEDIATE")
            with self.assertRaisesRegex(ValueError, "changed in another view"):
                confirm_intake_routing(second, acquisition_id, {
                    **stale_payload, "request_id": "ROUTE-STALE", "preview_token": stale_preview["preview_token"],
                    "confirm_routing": True,
                })
        finally:
            second.rollback(); second.close()
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM acquisition_line_projections").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sealed_units").fetchone()[0], 2)

    def test_large_multiline_routing_remains_prompt_and_reconciled(self):
        line_count = 75
        acquisition_id = self.acquisition([
            {"class": "PACK_PRODUCT", "name": f"Pack Product {index:03d}", "quantity": 2, "cost": 101}
            for index in range(line_count)
        ])
        lines = self.db.execute("SELECT id FROM acquisition_lines ORDER BY id").fetchall()
        choices = [{"line_id": int(row[0]), "keep_sealed_quantity": 2} for row in lines]
        started = time.perf_counter()
        result = self.confirm(acquisition_id, choices, "ROUTE-LARGE")
        elapsed = time.perf_counter() - started
        self.assertEqual(result["state"], "INTAKE_COMPLETE")
        self.assertEqual(result["summary"]["quantity_routed"], 150)
        self.assertEqual(result["summary"]["difference_cents"], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM acquisition_line_projections").fetchone()[0], line_count)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sealed_units").fetchone()[0], 150)
        self.assertLess(elapsed, 5.0)
        print(f"Phase 6 performance: {line_count} lines / 150 exact units routed in {elapsed * 1000:.2f} ms")


class Phase6MigrationTest(unittest.TestCase):
    def test_migration_is_additive_and_does_not_backfill_historical_links(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        base_schema(db)
        apply_migrations(db, DEFAULT_MIGRATIONS[:-6])
        db.execute("INSERT INTO batches (id,batch_code,total_cost) VALUES (1,'LEGACY-P6',12.34)")
        db.commit()
        self.assertEqual(apply_migrations(db, DEFAULT_MIGRATIONS[:-5]), ("0013_v22_phase6_downstream_intake_bridge",))
        self.assertIsNone(db.execute("SELECT acquisition_line_id FROM batches WHERE id=1").fetchone()[0])
        self.assertEqual(db.execute("SELECT COUNT(*) FROM acquisition_line_projections").fetchone()[0], 0)
        self.assertEqual(apply_migrations(db), ("0014_v22_phase7_sam_recognition", "0015_v22_rc3_hf1_mixed_purchase_reconciliation", "0016_v23_inventory_intelligence_phase1_receipt_semantics", "0017_v24_sam_phase1_family_printing", "0018_v24_jarvis_economics_sam_phase2"))
        self.assertEqual(apply_migrations(db), ())
        db.close()

    def test_failed_migration_rolls_back_schema_and_ledger_marker(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        base_schema(db)
        apply_migrations(db, DEFAULT_MIGRATIONS[:-6])
        db.execute("CREATE TABLE acquisition_intake_operations (id INTEGER)")
        db.commit()
        with self.assertRaises(MigrationError):
            apply_migrations(db, DEFAULT_MIGRATIONS[:-5])
        self.assertIsNone(db.execute(
            "SELECT 1 FROM schema_migrations WHERE migration_id='0013_v22_phase6_downstream_intake_bridge'"
        ).fetchone())
        self.assertNotIn("intake_disposition", {row[1] for row in db.execute("PRAGMA table_info(sealed_units)")})
        self.assertNotIn("acquisition_line_projections", {
            row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        })
        db.close()


class Phase6BridgeApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patches = (
            patch.object(app, "DB_PATH", root / "dex.db"), patch.object(app, "DATA_DIR", root),
            patch.object(app, "IMAGE_DIR", root / "images"), patch.object(app, "INBOUND_DIR", root / "inbound"),
            patch.object(app, "SOURCE_DB_DIR", root / "source"),
        )
        for item in self.patches: item.start()
        app.init_db()
        with app.connect() as db:
            now = "2026-08-15T12:00:00+00:00"
            cursor = db.execute(
                """INSERT INTO acquisitions
                   (acquisition_uuid,acquisition_code,creation_request_id,state,revision,source_scope,
                    merchant_name,purchased_on,final_usd_paid_cents,financial_facts_confirmed,
                    reconciliation_confirmed,confirmed_at,created_at,updated_at,payment_method)
                   VALUES ('API-UUID-6','ACQ-API-P6','API-CREATE-6','READY_FOR_INTAKE',3,'DOMESTIC',
                           'API Bridge','2026-08-15',1000,1,1,?,?,?,'CREDIT_DEBIT_CARD')""",
                (now, now, now),
            )
            self.acquisition_id = int(cursor.lastrowid)
            line = db.execute(
                """INSERT INTO acquisition_lines
                   (line_uuid,acquisition_id,line_sequence,product_class,game,product_name,set_code,
                    quantity,quantity_certainty,assigned_landed_cost_cents,allocation_method,
                    allocation_status,created_at,updated_at)
                   VALUES ('API-LINE-6',?,1,'PACK_PRODUCT','One Piece','OP16 Pack','OP16',2,
                           'KNOWN',1000,'MANUAL','CONFIRMED',?,?)""",
                (self.acquisition_id, now, now),
            )
            self.line_id = int(line.lastrowid)
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
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())

    def test_status_preview_and_confirm_routes(self):
        status, current = self.request(f"/api/acquisitions/{self.acquisition_id}/intake-routing")
        self.assertEqual(status, 200)
        payload = {"expected_revision": 3, "lines": [{"line_id": self.line_id, "keep_sealed_quantity": 2}]}
        status, preview = self.request(f"/api/acquisitions/{self.acquisition_id}/intake-routing/preview", "POST", payload)
        self.assertEqual(status, 200)
        status, confirmed = self.request(f"/api/acquisitions/{self.acquisition_id}/intake-routing/confirm", "POST", {
            **payload, "request_id": "API-ROUTE-6", "preview_token": preview["preview_token"], "confirm_routing": True,
        })
        self.assertEqual(status, 200)
        self.assertEqual(confirmed["state"], "INTAKE_COMPLETE")
        self.assertEqual(confirmed["summary"]["difference_cents"], 0)
