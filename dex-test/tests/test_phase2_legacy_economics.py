import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from dex_legacy_economics import ESTIMATE_NOTICE, estimate_legacy_batch, open_readonly_database


SCHEMA = """
CREATE TABLE batches (
    id INTEGER PRIMARY KEY,
    batch_code TEXT NOT NULL,
    status TEXT NOT NULL,
    total_cost REAL NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE cards (
    id INTEGER PRIMARY KEY,
    batch_id INTEGER NOT NULL,
    sku TEXT NOT NULL,
    status TEXT NOT NULL,
    recycled_at TEXT,
    market_average REAL,
    market_updated_at TEXT,
    listing_price REAL
);
CREATE TABLE sale_orders (
    id INTEGER PRIMARY KEY,
    subtotal REAL NOT NULL,
    shipping_collected REAL NOT NULL,
    platform_fees REAL NOT NULL,
    postage_cost REAL NOT NULL
);
CREATE TABLE sale_items (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL,
    card_id INTEGER NOT NULL,
    sale_price REAL NOT NULL
);
"""


def connect_fixture(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


class LegacyEconomicsCalculationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "legacy-copy.db"
        connection = connect_fixture(self.path)
        try:
            connection.executescript(SCHEMA)
            connection.executemany(
                "INSERT INTO batches (id, batch_code, status, total_cost, notes) VALUES (?, ?, ?, ?, ?)",
                [
                    (1, "OP-B-01", "COMPLETE", 90.00, ""),
                    (2, "OP-B-02", "COMPLETE", 60.00, ""),
                    (3, "OP-B-03", "OPEN", 0, "Contains unscanned bulk"),
                ],
            )
            connection.executemany(
                """INSERT INTO cards
                   (id, batch_id, sku, status, recycled_at, market_average, market_updated_at, listing_price)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (1, 1, "OP-001", "SOLD", None, 20, "2026-08-01T12:00:00+00:00", 22),
                    (2, 1, "OP-002", "IN_STOCK", None, 25, "2026-08-02T12:00:00+00:00", None),
                    (3, 1, "OP-003", "IN_STOCK", None, None, None, 8),
                    (4, 1, "OP-004", "REVIEW", "2026-08-03T12:00:00+00:00", 5, None, 6),
                    (5, 2, "OP-005", "SOLD", None, 15, "2026-08-01T12:00:00+00:00", 17),
                ],
            )
            connection.execute(
                "INSERT INTO sale_orders VALUES (1, 30, 3, 3, 3)"
            )
            connection.executemany(
                "INSERT INTO sale_items VALUES (?, 1, ?, 15)",
                [(1, 1), (2, 5)],
            )
            connection.commit()
        finally:
            connection.close()

    def tearDown(self):
        self.temp.cleanup()

    def test_estimate_separates_unknown_active_and_recycled_value(self):
        with open_readonly_database(self.path) as connection:
            estimate = estimate_legacy_batch(connection, 1)
        self.assertEqual(estimate["notice"], "Estimate only. Cost basis not finalized.")
        self.assertEqual(estimate["acquisition"]["estimated_cost_cents"], 9000)
        self.assertIsNone(estimate["acquisition"]["authoritative_cost_cents"])
        self.assertEqual(estimate["remaining"]["market"]["known_value_cents"], 2500)
        self.assertEqual(estimate["remaining"]["market"]["valued_count"], 1)
        self.assertEqual(estimate["remaining"]["market"]["total_count"], 2)
        self.assertFalse(estimate["remaining"]["market"]["complete"])
        self.assertEqual(estimate["excluded_recycled"]["market"]["known_value_cents"], 500)
        self.assertEqual(estimate["excluded_recycled"]["card_count"], 1)
        self.assertIn("MARKET_VALUE_INCOMPLETE", {item["code"] for item in estimate["warnings"]})
        self.assertEqual(estimate["state"], "ESTIMATED")

    def test_cross_batch_order_is_allocated_once(self):
        with open_readonly_database(self.path) as connection:
            first = estimate_legacy_batch(connection, 1)
            second = estimate_legacy_batch(connection, 2)
        self.assertEqual(first["realized"]["gross_merchandise_cents"], 1500)
        self.assertEqual(second["realized"]["gross_merchandise_cents"], 1500)
        self.assertEqual(
            first["realized"]["net_proceeds_cents"] + second["realized"]["net_proceeds_cents"],
            2700,
        )
        self.assertIn("estimated", first["realized"]["allocation_notice"].lower())

    def test_unknown_cost_and_detected_bulk_are_prominent_incomplete_warnings(self):
        with open_readonly_database(self.path) as connection:
            estimate = estimate_legacy_batch(connection, 3)
        self.assertFalse(estimate["acquisition"]["cost_known"])
        self.assertEqual(estimate["acquisition"]["label"], "Cost Unknown / Incomplete")
        codes = {item["code"] for item in estimate["warnings"] if item["severity"] == "material"}
        self.assertTrue({"COST_UNKNOWN", "OPEN_BATCH", "POSSIBLE_UNTRACKED_INVENTORY"} <= codes)

    def test_readonly_connection_rejects_writes_and_preserves_source_rows(self):
        with open_readonly_database(self.path) as connection:
            before = connection.execute("SELECT * FROM batches ORDER BY id").fetchall()
            estimate_legacy_batch(connection, 1)
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("UPDATE batches SET total_cost = 1 WHERE id = 1")
        with open_readonly_database(self.path) as connection:
            after = connection.execute("SELECT * FROM batches ORDER BY id").fetchall()
        self.assertEqual([tuple(row) for row in after], [tuple(row) for row in before])


class LegacyEconomicsPerformanceTest(unittest.TestCase):
    def test_2500_card_batch_preview_remains_responsive(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "large-legacy-copy.db"
            connection = connect_fixture(path)
            try:
                connection.executescript(SCHEMA)
                connection.execute(
                    "INSERT INTO batches VALUES (1, 'OP-LARGE', 'COMPLETE', 2500, '')"
                )
                connection.executemany(
                    """INSERT INTO cards
                       (id, batch_id, sku, status, recycled_at, market_average, market_updated_at, listing_price)
                       VALUES (?, 1, ?, 'IN_STOCK', NULL, ?, '2026-08-01T12:00:00+00:00', ?)""",
                    [
                        (index, f"OP-LARGE-{index:05d}", 1.25 if index % 4 else None, 1.50 if index % 5 else None)
                        for index in range(1, 2501)
                    ],
                )
                connection.commit()
            finally:
                connection.close()
            started = time.perf_counter()
            with open_readonly_database(path) as readonly:
                estimate = estimate_legacy_batch(readonly, 1)
            elapsed = time.perf_counter() - started
            self.assertEqual(estimate["reconciliation"]["recorded_card_count"], 2500)
            self.assertLess(elapsed, 2.0, f"Large batch estimate took {elapsed:.3f}s")


class EstimatedEconomicsUiContractTest(unittest.TestCase):
    def test_panel_contains_required_labels_and_no_frontend_economics_formula(self):
        source = (Path(__file__).parents[1] / "static" / "app.js").read_text(encoding="utf-8")
        self.assertEqual(ESTIMATE_NOTICE, "Estimate only. Cost basis not finalized.")
        self.assertIn("escapeHtml(estimate.notice)", source)
        self.assertIn("Realized Economics", source)
        self.assertIn("Unrealized / Remaining Value", source)
        self.assertIn("valuation.freshness_label", source)
        self.assertIn("Calculation version", source)
        self.assertNotIn("net_proceeds_cents =", source)


if __name__ == "__main__":
    unittest.main()
