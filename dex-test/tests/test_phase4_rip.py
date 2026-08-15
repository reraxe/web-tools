import importlib.util
import json
import os
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from dex_migrations import DEFAULT_MIGRATIONS, MigrationError, apply_migrations
from dex_rip import (
    activate_rip,
    allocation_preview,
    correct_rip,
    create_rip_session,
    finalize_rip,
    rip_session_payload,
)


ROOT = Path(__file__).parents[1]


def phase4_database() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(
        """
        CREATE TABLE batches (
            id INTEGER PRIMARY KEY,
            batch_code TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'OPEN',
            total_cost REAL NOT NULL DEFAULT 0,
            recycled_at TEXT
        );
        CREATE TABLE cards (
            id INTEGER PRIMARY KEY,
            sku TEXT NOT NULL UNIQUE,
            batch_id INTEGER NOT NULL REFERENCES batches(id),
            name TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            recycled_at TEXT
        );
        CREATE TABLE processed_scans (
            fingerprint TEXT PRIMARY KEY,
            batch_id INTEGER NOT NULL REFERENCES batches(id),
            processed_at TEXT NOT NULL
        );
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE activity_log (
            id INTEGER PRIMARY KEY,
            created_at TEXT NOT NULL,
            action_type TEXT NOT NULL,
            description TEXT NOT NULL,
            payload TEXT NOT NULL DEFAULT '{}',
            undone_at TEXT
        );
        CREATE TABLE sale_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            order_number TEXT NOT NULL DEFAULT '',
            sold_at TEXT NOT NULL,
            subtotal REAL NOT NULL DEFAULT 0,
            shipping_collected REAL NOT NULL DEFAULT 0,
            platform_fees REAL NOT NULL DEFAULT 0,
            postage_cost REAL NOT NULL DEFAULT 0,
            notes TEXT NOT NULL DEFAULT ''
        );
        """
    )
    apply_migrations(db)
    return db


def add_batch(
    db: sqlite3.Connection,
    batch_id: int,
    *,
    mode: str = "SEALED_RIP",
    cost_cents: int = 1000,
    units: int = 3,
) -> None:
    db.execute(
        """INSERT INTO batches
           (id, batch_code, status, total_cost, economics_mode, economics_status,
            product_name, final_usd_paid_cents, units_acquired)
           VALUES (?, ?, 'OPEN', ?, ?, 'DRAFT', ?, ?, ?)""",
        (
            batch_id,
            f"OP-B20260814-{batch_id:02d}",
            cost_cents / 100,
            mode,
            f"Product {batch_id}",
            cost_cents,
            units,
        ),
    )


def add_card(
    db: sqlite3.Connection,
    card_id: int,
    batch_id: int,
    rip_id: int | None,
    *,
    recycled_at: str | None = None,
) -> None:
    db.execute(
        "INSERT INTO cards (id, sku, batch_id, name, updated_at, recycled_at, rip_session_id) VALUES (?, ?, ?, ?, '', ?, ?)",
        (card_id, f"OP-B20260814-{card_id:03d}", batch_id, f"Card {card_id}", recycled_at, rip_id),
    )


class Phase4MigrationTest(unittest.TestCase):
    def test_phase4_migration_is_registered_once_and_adds_only_rip_infrastructure(self):
        db = phase4_database()
        try:
            self.assertEqual(
                [row[0] for row in db.execute("SELECT migration_id FROM schema_migrations ORDER BY migration_id")],
                [migration.migration_id for migration in DEFAULT_MIGRATIONS],
            )
            self.assertEqual(apply_migrations(db), ())
            self.assertTrue(
                {"rip_sessions", "rip_economic_events", "rip_basis_events"}
                <= {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            )
            self.assertIn("rip_session_id", {row[1] for row in db.execute("PRAGMA table_info(cards)")})
            self.assertIn("rip_session_id", {row[1] for row in db.execute("PRAGMA table_info(processed_scans)")})
        finally:
            db.close()

    def test_failed_phase4_migration_rolls_back_schema_and_completion_marker(self):
        db = sqlite3.connect(":memory:")
        try:
            db.executescript(
                """
                CREATE TABLE batches (id INTEGER PRIMARY KEY, batch_code TEXT, total_cost REAL, status TEXT);
                CREATE TABLE cards (id INTEGER PRIMARY KEY, batch_id INTEGER, sku TEXT);
                CREATE TABLE processed_scans (fingerprint TEXT PRIMARY KEY, batch_id INTEGER, processed_at TEXT);
                """
            )
            self.assertEqual(apply_migrations(db, DEFAULT_MIGRATIONS[:1]), ("0001_phase3_acquisition_facts",))
            db.execute("CREATE TABLE rip_economic_events (sentinel TEXT)")
            db.commit()
            with self.assertRaises(MigrationError):
                apply_migrations(db)
            self.assertIsNone(
                db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rip_sessions'").fetchone()
            )
            self.assertNotIn("rip_session_id", {row[1] for row in db.execute("PRAGMA table_info(cards)")})
            self.assertEqual(
                [row[0] for row in db.execute("SELECT migration_id FROM schema_migrations")],
                ["0001_phase3_acquisition_facts"],
            )
        finally:
            db.close()


class Phase4RipEconomicsTest(unittest.TestCase):
    def setUp(self):
        self.db = phase4_database()

    def tearDown(self):
        self.db.close()

    def test_explicit_intake_partial_unit_cost_equal_bulk_and_immutable_correction(self):
        add_batch(self.db, 1, cost_cents=1000, units=3)
        rip = create_rip_session(self.db, 1, {"units_opened": 1})
        self.assertEqual(rip["status"], "DRAFT")
        self.assertFalse(rip["active_for_intake"])
        activate_rip(self.db, rip["id"])
        add_card(self.db, 20, 1, rip["id"])
        add_card(self.db, 10, 1, rip["id"])

        payload = {
            "allocation_method": "EQUAL",
            "bulk_mode": "KNOWN_QUANTITY",
            "bulk_quantity": 1,
        }
        first = allocation_preview(self.db, rip["id"], payload)
        self.db.execute("UPDATE cards SET name='Renamed', sku='OP-B20260814-999' WHERE id=10")
        second = allocation_preview(self.db, rip["id"], payload)
        self.assertEqual(
            [(card["id"], card["basis_cents"]) for card in first["cards"]],
            [(card["id"], card["basis_cents"]) for card in second["cards"]],
        )
        self.assertEqual(first["reconciliation"]["rip_cost_cents"], 334)
        self.assertEqual(first["reconciliation"]["total_allocated_cents"], 334)
        self.assertEqual(first["reconciliation"]["difference_cents"], 0)
        self.assertEqual(first["unit_sequence_start"], 1)
        self.assertEqual(first["unit_sequence_end"], 1)

        finalized = finalize_rip(
            self.db,
            rip["id"],
            {
                **payload,
                "request_id": "finalize-1",
                "confirm_all_cards_accounted": True,
                "confirm_finalization": True,
            },
        )
        self.assertEqual(finalized["status"], "FINALIZED")
        self.assertEqual(finalized["reconciliation"]["difference_cents"], 0)
        self.assertFalse(finalized["active_for_intake"])
        with self.assertRaisesRegex(ValueError, "finalized rip"):
            activate_rip(self.db, rip["id"])

        add_card(self.db, 30, 1, None)
        original_event = self.db.execute(
            "SELECT payload FROM rip_economic_events WHERE request_id='finalize-1'"
        ).fetchone()[0]
        corrected = correct_rip(
            self.db,
            rip["id"],
            {
                "request_id": "correction-1",
                "reason_code": "LATE_CARD_ADDITION",
                "notes": "Late physical card was found and verified.",
                "bulk_delta": "0.00",
                "card_adjustments": [
                    {"sku": "OP-B20260814-020", "delta": "-0.01"},
                    {"sku": "OP-B20260814-030", "delta": "0.01"},
                ],
            },
        )
        self.assertEqual(corrected["reconciliation"]["difference_cents"], 0)
        self.assertEqual(len(corrected["events"]), 2)
        self.assertEqual(
            self.db.execute("SELECT rip_session_id FROM cards WHERE id=30").fetchone()[0],
            rip["id"],
        )
        self.assertEqual(
            self.db.execute("SELECT payload FROM rip_economic_events WHERE request_id='finalize-1'").fetchone()[0],
            original_event,
        )
        correct_rip(
            self.db,
            rip["id"],
            {
                "request_id": "correction-1",
                "reason_code": "OTHER",
                "notes": "Duplicate submission",
                "bulk_delta": "0",
                "card_adjustments": [],
            },
        )
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM rip_economic_events").fetchone()[0], 2
        )

    def test_unknown_bulk_requires_manual_reserve_and_marks_coverage_incomplete(self):
        add_batch(self.db, 1, cost_cents=1000, units=1)
        rip = create_rip_session(self.db, 1, {"units_opened": 1})
        activate_rip(self.db, rip["id"])
        add_card(self.db, 1, 1, rip["id"])
        with self.assertRaisesRegex(ValueError, "explicit .*reserve"):
            allocation_preview(
                self.db,
                rip["id"],
                {"allocation_method": "EQUAL", "bulk_mode": "MANUAL_RESERVE", "bulk_reserve": ""},
            )
        preview = allocation_preview(
            self.db,
            rip["id"],
            {"allocation_method": "EQUAL", "bulk_mode": "MANUAL_RESERVE", "bulk_reserve": "2.00"},
        )
        self.assertFalse(preview["valuation_complete"])
        self.assertIsNone(preview["bulk_quantity"])
        self.assertEqual(preview["cards"][0]["basis_cents"], 800)
        self.assertEqual(preview["reconciliation"]["bulk_reserve_basis_cents"], 200)
        self.assertEqual(preview["reconciliation"]["difference_cents"], 0)

    def test_known_cost_singles_require_actual_manual_card_costs(self):
        add_batch(self.db, 1, mode="SINGLES_KNOWN_COST", cost_cents=1000, units=0)
        rip = create_rip_session(self.db, 1, {})
        activate_rip(self.db, rip["id"])
        add_card(self.db, 1, 1, rip["id"])
        add_card(self.db, 2, 1, rip["id"])
        with self.assertRaisesRegex(ValueError, "every participating"):
            allocation_preview(
                self.db,
                rip["id"],
                {
                    "allocation_method": "MANUAL",
                    "bulk_mode": "NONE",
                    "card_overrides": [{"sku": "OP-B20260814-001", "basis": "3.25"}],
                },
            )
        preview = allocation_preview(
            self.db,
            rip["id"],
            {
                "allocation_method": "MANUAL",
                "bulk_mode": "NONE",
                "card_overrides": [
                    {"sku": "OP-B20260814-002", "basis": "6.75"},
                    {"sku": "OP-B20260814-001", "basis": "3.25"},
                ],
            },
        )
        self.assertEqual([card["basis_cents"] for card in preview["cards"]], [325, 675])
        self.assertEqual(preview["reconciliation"]["difference_cents"], 0)

    def test_pending_and_finalized_units_cannot_exceed_acquired_units(self):
        add_batch(self.db, 1, cost_cents=1000, units=3)
        first = create_rip_session(self.db, 1, {"units_opened": 2})
        with self.assertRaisesRegex(ValueError, "exceed"):
            create_rip_session(self.db, 1, {"units_opened": 2})
        add_card(self.db, 1, 1, first["id"])
        preview = allocation_preview(
            self.db, first["id"], {"allocation_method": "EQUAL", "bulk_mode": "NONE"}
        )
        self.assertEqual(preview["reconciliation"]["rip_cost_cents"], 667)

    def test_recycled_card_keeps_basis_and_reconciliation_history(self):
        add_batch(self.db, 1, cost_cents=100, units=1)
        rip = create_rip_session(self.db, 1, {"units_opened": 1})
        add_card(self.db, 1, 1, rip["id"])
        finalize_rip(
            self.db,
            rip["id"],
            {
                "allocation_method": "EQUAL",
                "bulk_mode": "NONE",
                "request_id": "finalize-recycle",
                "confirm_all_cards_accounted": True,
                "confirm_finalization": True,
            },
        )
        self.db.execute("UPDATE cards SET recycled_at='2026-08-14T12:00:00Z' WHERE id=1")
        result = rip_session_payload(self.db, rip["id"])
        self.assertEqual(result["cards"][0]["basis_cents"], 100)
        self.assertIsNotNone(result["cards"][0]["recycled_at"])
        self.assertEqual(result["reconciliation"]["difference_cents"], 0)


class Phase4ApiSwitchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        cls.environment = {
            "DEX_DATA_DIR": str(root / "data"),
            "DEX_DB_PATH": str(root / "data" / "dex.db"),
            "DEX_IMAGE_DIR": str(root / "data" / "images"),
            "DEX_INBOUND_DIR": str(root / "data" / "inbound"),
            "DEX_SOURCE_DB_DIR": str(root / "source-database"),
            "DEX_WATCH_INBOUND": "0",
            "DEX_SEED_DEMO": "0",
        }
        cls.environment_patch = patch.dict(os.environ, cls.environment)
        cls.environment_patch.start()
        spec = importlib.util.spec_from_file_location("dex_phase4_api_test", ROOT / "app.py")
        cls.dex = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.dex)
        cls.dex.init_db()
        cls.server = cls.dex.ThreadingHTTPServer(("127.0.0.1", 0), cls.dex.DexHandler)
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        cls.environment_patch.stop()
        cls.temp.cleanup()

    def request(self, path, body):
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(body).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=5) as response:
            return response.status, json.loads(response.read())

    def acquisition(self, set_code):
        status, batch = self.request(
            "/api/batches",
            {
                "game": "One Piece",
                "set_code": set_code,
                "set_name": set_code,
                "acquisition_type": "Booster Box",
                "economics_mode": "SEALED_RIP",
                "product_name": f"{set_code} Booster Box",
                "units_acquired": 1,
                "purchase_subtotal": "100.00",
                "final_usd_paid": "100.00",
            },
        )
        self.assertEqual(status, 201)
        return batch

    def test_switch_with_unprocessed_scanner_file_requires_confirmation(self):
        first = self.acquisition("OP01")
        second = self.acquisition("OP02")
        _, first_rip = self.request(f"/api/batches/{first['id']}/rips", {"units_opened": 1})
        _, second_rip = self.request(f"/api/batches/{second['id']}/rips", {"units_opened": 1})
        status, _ = self.request(f"/api/rip-sessions/{first_rip['id']}/activate", {"confirm_switch": False})
        self.assertEqual(status, 200)
        inbound = Path(self.environment["DEX_INBOUND_DIR"]) / first["batch_code"]
        inbound.mkdir(parents=True, exist_ok=True)
        (inbound / "unprocessed-front.jpg").write_bytes(b"disposable-test-image")
        status, blocked = self.request(
            f"/api/rip-sessions/{second_rip['id']}/activate", {"confirm_switch": False}
        )
        self.assertEqual(status, 409)
        self.assertTrue(blocked["requires_confirmation"])
        self.assertGreater(blocked["unprocessed_files"], 0)
        status, activated = self.request(
            f"/api/rip-sessions/{second_rip['id']}/activate", {"confirm_switch": True}
        )
        self.assertEqual(status, 200)
        self.assertTrue(activated["active_for_intake"])

    def test_browser_intake_is_unassigned_until_operator_explicitly_starts_rip(self):
        batch = self.acquisition("OP03")
        _, rip = self.request(f"/api/batches/{batch['id']}/rips", {"units_opened": 1})
        _, before = self.request(
            f"/api/batches/{batch['id']}/cards",
            {"card_number": "OP03-001", "name": "Before activation"},
        )
        self.assertIsNone(before["rip_session_id"])
        status, _ = self.request(
            f"/api/rip-sessions/{rip['id']}/activate", {"confirm_switch": True}
        )
        self.assertEqual(status, 200)
        _, after = self.request(
            f"/api/batches/{batch['id']}/cards",
            {"card_number": "OP03-002", "name": "After activation"},
        )
        self.assertEqual(after["rip_session_id"], rip["id"])
        _, repeated = self.request(
            f"/api/batches/{batch['id']}/cards",
            {"card_number": "OP03-003", "name": "Repeated active intake"},
        )
        self.assertEqual(repeated["rip_session_id"], rip["id"])
        _, contract = self.get(f"/api/batches/{batch['id']}/rips")
        self.assertIsInstance(contract["sessions"], list)
        self.assertIsInstance(contract["sessions"][0]["cards"], list)
        self.assertIsInstance(contract["sessions"][0]["events"], list)
        self.assertEqual(len(contract["sessions"][0]["cards"]), 2)
        self.assertTrue(contract["sessions"][0]["active_for_intake"])

    def test_completing_batch_stops_active_rip_and_reopen_allows_intake_again(self):
        batch = self.acquisition("OP04")
        _, rip = self.request(f"/api/batches/{batch['id']}/rips", {"units_opened": 1})
        status, _ = self.request(
            f"/api/rip-sessions/{rip['id']}/activate", {"confirm_switch": True}
        )
        self.assertEqual(status, 200)

        status, completed = self.request(f"/api/batches/{batch['id']}/complete", {})
        self.assertEqual(status, 200)
        self.assertEqual(completed["status"], "COMPLETE")
        _, stopped = self.get(f"/api/batches/{batch['id']}/rips")
        self.assertIsNone(stopped["active_intake"])
        self.assertEqual(stopped["sessions"][0]["status"], "DRAFT")

        status, blocked = self.request(
            f"/api/rip-sessions/{rip['id']}/activate", {"confirm_switch": True}
        )
        self.assertEqual(status, 400)
        self.assertIn("Reopen this batch", blocked["error"])

        status, reopened = self.request(f"/api/batches/{batch['id']}/reopen", {})
        self.assertEqual(status, 200)
        self.assertEqual(reopened["status"], "OPEN")
        status, _ = self.request(
            f"/api/rip-sessions/{rip['id']}/activate", {"confirm_switch": True}
        )
        self.assertEqual(status, 200)
        status, card = self.request(
            f"/api/batches/{batch['id']}/cards",
            {"card_number": "OP04-001", "name": "After reopen"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(card["rip_session_id"], rip["id"])


class Phase4UiAndPackagingContractTest(unittest.TestCase):
    def test_ui_requires_explicit_intake_and_exact_final_confirmation(self):
        javascript = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Scanner intake is currently assigned to", javascript)
        self.assertIn("Start intake", javascript)
        self.assertIn("I confirm every intended scanned card", javascript)
        self.assertIn("syncRipBulkFields", javascript)
        self.assertIn('data-bulk-field="quantity" hidden', javascript)
        self.assertIn('<span>I understand ordinary intake into this rip will be locked.</span>', javascript)
        self.assertIn("Basis finalized · audited corrections only", javascript)
        self.assertIn('${b.status === "OPEN" ? cardIngestForm(b) : ""}', javascript)
        self.assertIn("require an exact `$0.00` difference", (ROOT / "PATCH_PLAN_ACQUISITION_RIP_BATCH.md").read_text(encoding="utf-8"))
        self.assertIn("Array.isArray(rips?.sessions)", javascript)
        self.assertIn("v2.2-test-inbound-phase3-product-catalog-upc", html)
        self.assertIn('grid-template-columns: 16px minmax(0, 1fr)', (ROOT / "static" / "styles.css").read_text(encoding="utf-8"))
        self.assertIn("#confirm-rip-finalization .checkbox-label + .checkbox-label", (ROOT / "static" / "styles.css").read_text(encoding="utf-8"))

    def test_runtime_image_packages_phase4_module(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("dex_acquisition.py dex_rip.py dex_sealed.py ./", dockerfile)
        self.assertIn("dex_acquisition, dex_rip, dex_sealed", dockerfile)


if __name__ == "__main__":
    unittest.main()
