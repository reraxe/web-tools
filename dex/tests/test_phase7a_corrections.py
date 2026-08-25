import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.request
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import app
from dex_batch_economics import batch_economics_payload
from dex_corrections import (
    batch_corrections_payload,
    card_has_economic_history,
    correct_acquisition_cost,
    current_acquisition_cost_cents,
    current_bulk_basis_cents,
    current_card_basis_cents,
    current_operational_loss_cents,
    current_sealed_basis_cents,
    dispose_card,
    dispose_sealed_unit,
    reverse_event,
    transfer_basis,
)
from dex_migrations import DEFAULT_MIGRATIONS, MigrationError, apply_migrations
from dex_sealed import batch_sealed_payload, synchronize_sealed_units


ROOT = Path(__file__).parents[1]


class Phase7AFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.db_path = root / "phase7a.db"
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

    def add_batch(self, batch_id, mode, cents=1000, units=0):
        self.db.execute(
            """INSERT INTO batches
               (id,batch_code,created_at,status,game,set_code,acquisition_type,total_cost,
                economics_mode,economics_status,product_name,final_usd_paid_cents,units_acquired)
               VALUES (?,?,'2026-08-14','OPEN','One Piece','OP01','Test',?,?,'FINALIZED','Phase 7A fixture',?,?)""",
            (batch_id, f"OP-P7A-{batch_id:02d}", cents / 100, mode, cents, units),
        )
        if mode == "SEALED_RIP":
            synchronize_sealed_units(self.db, batch_id)

    def add_singles(self, batch_id=1):
        self.add_batch(batch_id, "SINGLES_LUMP_SUM", 1000)
        rip_id = self.db.execute(
            """INSERT INTO rip_sessions
               (rip_code,batch_id,status,units_opened,allocation_method,bulk_mode,bulk_quantity,
                consumed_cost_cents,scanned_basis_cents,bulk_basis_cents,total_allocated_cents,
                difference_cents,cards_accounted_confirmed,created_at,finalized_at)
               VALUES (?,?, 'FINALIZED',0,'EQUAL','KNOWN_QUANTITY',1,1000,800,200,1000,0,1,'2026-08-14','2026-08-14')""",
            (f"RIP-P7A-{batch_id:02d}", batch_id),
        ).lastrowid
        card_ids = []
        for sequence in (1, 2):
            card_ids.append(self.db.execute(
                """INSERT INTO cards
                   (sku,batch_id,created_at,updated_at,name,status,rip_session_id)
                   VALUES (?,?, '2026-08-14','2026-08-14',?,'IN_STOCK',?)""",
                (f"OP-P7A-{batch_id:02d}-{sequence:03d}", batch_id, f"Card {sequence}", rip_id),
            ).lastrowid)
        self.db.execute(
            """INSERT INTO rip_economic_events
               (event_id,request_id,rip_session_id,event_type,effective_at,recorded_at,reason_code,notes,payload)
               VALUES ('RIP-FINAL','RIP-FINAL-REQ',?,'FINALIZATION','2026-08-14','2026-08-14','INITIAL','fixture','{}')""",
            (rip_id,),
        )
        for card_id in card_ids:
            self.db.execute(
                "INSERT INTO rip_basis_events (event_id,rip_session_id,target_type,card_id,amount_delta_cents,created_at) VALUES ('RIP-FINAL',?,'CARD',?,400,'2026-08-14')",
                (rip_id, card_id),
            )
        self.db.execute(
            "INSERT INTO rip_basis_events (event_id,rip_session_id,target_type,card_id,amount_delta_cents,created_at) VALUES ('RIP-FINAL',?,'BULK',NULL,200,'2026-08-14')",
            (rip_id,),
        )
        return rip_id, card_ids


class Phase7ACorrectionTest(Phase7AFixture):
    def test_phase7a_http_api_records_reads_and_reverses_event(self):
        self.add_batch(1, "SEALED_RIP", 1000, 3)
        self.db.commit()
        with patch.object(app, "DB_PATH", self.db_path):
            server = ThreadingHTTPServer(("127.0.0.1", 0), app.DexHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"

            def request(path, method="GET", payload=None):
                body = None if payload is None else json.dumps(payload).encode()
                req = urllib.request.Request(base + path, data=body, method=method, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req) as response:
                    return response.status, json.loads(response.read())

            try:
                status, event = request("/api/batches/1/corrections/acquisition", "POST", {
                    "request_id": "API-ACQ-1", "new_total_usd": "10.01",
                    "reason_code": "ACQUISITION_COST_ERROR", "notes": "API fixture correction.",
                })
                self.assertEqual(status, 201)
                self.assertTrue(event["event_id"].startswith("ECO7A-"))
                self.assertEqual(request("/api/batches/1/corrections")[1]["acquisition_cost"]["current_authoritative_cents"], 1001)
                status, reversal = request(f"/api/economic-events/{event['event_id']}/reverse", "POST", {
                    "request_id": "API-REV-1", "notes": "API fixture reversal."
                })
                self.assertEqual(status, 201)
                self.assertEqual(reversal["reverses_event_id"], event["event_id"])
            finally:
                server.shutdown()
                thread.join(timeout=3)
                server.server_close()

    def test_sealed_acquisition_correction_is_deterministic_and_reversible(self):
        self.add_batch(1, "SEALED_RIP", 1000, 3)
        original = [row[0] for row in self.db.execute("SELECT basis_cents FROM sealed_units ORDER BY id")]
        event = correct_acquisition_cost(self.db, 1, {
            "request_id": "ACQ-CORR-1", "new_total_usd": "10.02",
            "reason_code": "ACQUISITION_COST_ERROR", "notes": "Invoice total corrected.",
            "effective_at": "2026-08-14",
        })
        unit_ids = [row[0] for row in self.db.execute("SELECT id FROM sealed_units ORDER BY id")]
        self.assertEqual(original, [334, 333, 333])
        self.assertEqual([current_sealed_basis_cents(self.db, unit_id) for unit_id in unit_ids], [335, 334, 333])
        self.assertEqual(current_acquisition_cost_cents(self.db, 1), 1002)
        self.assertEqual(correct_acquisition_cost(self.db, 1, {
            "request_id": "ACQ-CORR-1", "new_total_usd": "999.99",
            "reason_code": "OTHER", "notes": "duplicate request",
        })["event_id"], event["event_id"])
        reversal = reverse_event(self.db, event["event_id"], {
            "request_id": "ACQ-REV-1", "notes": "Original invoice was correct."
        })
        self.assertEqual(reversal["reverses_event_id"], event["event_id"])
        self.assertEqual(current_acquisition_cost_cents(self.db, 1), 1000)
        self.assertEqual([current_sealed_basis_cents(self.db, unit_id) for unit_id in unit_ids], original)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM economic_events").fetchone()[0], 2)

    def test_card_bulk_transfer_duplicate_and_physical_loss_preserve_history(self):
        rip_id, card_ids = self.add_singles()
        transfer = transfer_basis(self.db, 1, {
            "request_id": "TRANSFER-1", "source_type": "CARD", "source_id": card_ids[0],
            "destination_type": "RIP_BULK", "destination_id": rip_id, "amount": "0.25",
            "reason_code": "BASIS_REALLOCATION", "notes": "Move identified bulk basis.",
        })
        self.assertEqual((current_card_basis_cents(self.db, card_ids[0]), current_bulk_basis_cents(self.db, rip_id)), (375, 225))
        reverse_event(self.db, transfer["event_id"], {"request_id": "TRANSFER-REV", "notes": "Undo transfer."})
        duplicate = dispose_card(self.db, "OP-P7A-01-001", {
            "request_id": "DUPLICATE-1", "reason_code": "DUPLICATE_ENTRY_ERROR",
            "notes": "Duplicate scan confirmed.", "destination_type": "CARD", "destination_id": card_ids[1],
        })
        self.assertEqual((current_card_basis_cents(self.db, card_ids[0]), current_card_basis_cents(self.db, card_ids[1])), (0, 800))
        self.assertEqual(current_operational_loss_cents(self.db, 1), 0)
        self.assertTrue(card_has_economic_history(self.db, card_ids[0]))
        self.assertIsNone(self.db.execute("SELECT purge_after FROM cards WHERE id=?", (card_ids[0],)).fetchone()[0])
        reverse_event(self.db, duplicate["event_id"], {"request_id": "DUPLICATE-REV", "notes": "Record was not duplicate."})
        loss = dispose_card(self.db, "OP-P7A-01-001", {
            "request_id": "LOSS-1", "reason_code": "DAMAGED", "notes": "Physical card damaged beyond use."
        })
        self.assertEqual(current_card_basis_cents(self.db, card_ids[0]), 0)
        self.assertEqual(current_operational_loss_cents(self.db, 1), 400)
        reverse_event(self.db, loss["event_id"], {"request_id": "LOSS-REV", "notes": "Card recovered undamaged."})
        self.assertEqual(current_card_basis_cents(self.db, card_ids[0]), 400)
        self.assertEqual(current_operational_loss_cents(self.db, 1), 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM economic_tombstones WHERE entity_id=?", (card_ids[0],)).fetchone()[0], 2)

    def test_sealed_duplicate_and_damage_reconcile_exact_units_and_loss(self):
        self.add_batch(1, "SEALED_RIP", 1000, 3)
        units = self.db.execute("SELECT id,unit_code FROM sealed_units ORDER BY id").fetchall()
        duplicate = dispose_sealed_unit(self.db, units[0]["id"], {
            "request_id": "UNIT-DUP", "reason_code": "DUPLICATE_ENTRY_ERROR", "notes": "Extra ledger row confirmed."
        })
        self.assertEqual([current_sealed_basis_cents(self.db, row["id"]) for row in units], [0, 500, 500])
        sealed = batch_sealed_payload(self.db, 1)
        self.assertEqual(sealed["counts"]["corrected_adjusted"], 1)
        self.assertEqual(sealed["reconciliation"]["difference"], 0)
        reverse_event(self.db, duplicate["event_id"], {"request_id": "UNIT-DUP-REV", "notes": "Unit exists."})
        damaged = dispose_sealed_unit(self.db, units[0]["id"], {
            "request_id": "UNIT-DAMAGE", "reason_code": "DAMAGED", "notes": "Crushed and discarded."
        })
        self.assertEqual(current_sealed_basis_cents(self.db, units[0]["id"]), 0)
        self.assertEqual(current_operational_loss_cents(self.db, 1), 334)
        report = batch_economics_payload(self.db, 1)
        self.assertTrue(report["reconciliation"]["basis"]["reconciled"])
        self.assertEqual(report["excluded"]["operational_loss_cents"], 334)
        reverse_event(self.db, damaged["event_id"], {"request_id": "UNIT-DAMAGE-REV", "notes": "Damage record entered against wrong unit."})
        self.assertEqual(self.db.execute("SELECT status FROM sealed_units WHERE id=?", (units[0]["id"],)).fetchone()[0], "REMAINING")

    def test_payload_exposes_source_current_events_and_tombstones(self):
        rip_id, card_ids = self.add_singles()
        transfer_basis(self.db, 1, {
            "request_id": "PAYLOAD-TRANSFER", "source_type": "RIP_BULK", "source_id": rip_id,
            "destination_type": "CARD", "destination_id": card_ids[0], "amount": "0.10",
            "reason_code": "BULK_CORRECTION", "notes": "Identified card from bulk."
        })
        payload = batch_corrections_payload(self.db, 1)
        self.assertTrue(payload["rules"]["append_only"])
        self.assertEqual(payload["acquisition_cost"]["preserved_source_cents"], 1000)
        self.assertEqual(len(payload["events"]), 1)
        self.assertEqual(payload["events"][0]["entries"][0]["amount_delta_cents"], -10)

    def test_large_finalized_batch_correction_payload_is_prompt(self):
        self.add_batch(1, "SINGLES_LUMP_SUM", 100000)
        rip_id = self.db.execute(
            """INSERT INTO rip_sessions
               (rip_code,batch_id,status,allocation_method,bulk_mode,consumed_cost_cents,
                scanned_basis_cents,bulk_basis_cents,total_allocated_cents,difference_cents,
                cards_accounted_confirmed,created_at,finalized_at)
               VALUES ('RIP-LARGE',1,'FINALIZED','EQUAL','NONE',100000,100000,0,100000,0,1,'2026-08-14','2026-08-14')"""
        ).lastrowid
        self.db.execute(
            """INSERT INTO rip_economic_events
               (event_id,request_id,rip_session_id,event_type,effective_at,recorded_at,reason_code,notes,payload)
               VALUES ('RIP-LARGE-EVENT','RIP-LARGE-REQ',?,'FINALIZATION','2026-08-14','2026-08-14','INITIAL','fixture','{}')""",
            (rip_id,),
        )
        for index in range(1, 1001):
            card_id = self.db.execute(
                "INSERT INTO cards (sku,batch_id,created_at,updated_at,name,status,rip_session_id) VALUES (?,1,'2026-08-14','2026-08-14','Large card','IN_STOCK',?)",
                (f"LARGE-{index:05d}", rip_id),
            ).lastrowid
            self.db.execute(
                "INSERT INTO rip_basis_events (event_id,rip_session_id,target_type,card_id,amount_delta_cents,created_at) VALUES ('RIP-LARGE-EVENT',?,'CARD',?,100,'2026-08-14')",
                (rip_id, card_id),
            )
        started = time.perf_counter()
        payload = batch_corrections_payload(self.db, 1)
        elapsed = time.perf_counter() - started
        self.assertEqual(len(payload["cards"]), 1000)
        self.assertLess(elapsed, 2.0)


class Phase7AMigrationAndUiContractTest(unittest.TestCase):
    def test_migration_is_transactional_and_has_no_backfill(self):
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE batches (id INTEGER PRIMARY KEY)")
        db.execute("CREATE TABLE activity_log (id INTEGER PRIMARY KEY, created_at TEXT, action_type TEXT, description TEXT, payload TEXT)")
        apply_migrations(db, ())
        with self.assertRaises(MigrationError):
            db.execute("CREATE TABLE economic_events (sentinel TEXT)")
            db.commit()
            apply_migrations(db, DEFAULT_MIGRATIONS[3:])
        self.assertIsNone(db.execute("SELECT 1 FROM schema_migrations WHERE migration_id='0004_phase7a_corrections_dispositions'").fetchone())
        self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='economic_event_entries'").fetchone())
        db.close()

    def test_ui_api_and_runtime_package_phase7a(self):
        app_js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        app_py = (ROOT / "app.py").read_text(encoding="utf-8")
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("Corrections &amp; Dispositions", app_js)
        self.assertIn("/corrections/acquisition", app_js)
        self.assertIn("/disposition", app_js)
        self.assertIn("reverse-economic-event", app_js)
        self.assertIn("card_has_economic_history", app_py)
        self.assertIn("COPY dex_corrections.py ./", dockerfile)
        self.assertIn('RUN python -c "import dex_corrections"', dockerfile)


if __name__ == "__main__":
    unittest.main()
