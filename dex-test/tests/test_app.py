import base64
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


class DexApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        (root / "reference-library").mkdir(parents=True)
        os.environ.update(
            {
                "DEX_DATA_DIR": str(root / "data"),
                "DEX_DB_PATH": str(root / "data" / "dex.db"),
                "DEX_IMAGE_DIR": str(root / "data" / "images"),
                "DEX_INBOUND_DIR": str(root / "data" / "inbound"),
                "DEX_SOURCE_DB_DIR": str(root / "source-database"),
                "DEX_ONE_PIECE_REFERENCE_DIR": str(root / "reference-library"),
                "DEX_WATCH_INBOUND": "0",
                "DEX_SEED_DEMO": "0",
            }
        )
        spec = importlib.util.spec_from_file_location("dex_app_test", Path(__file__).parents[1] / "app.py")
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
        cls.temp.cleanup()

    def request(self, path, method="GET", body=None, timeout=5):
        payload = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            self.base + path,
            data=payload,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read())

    def test_complete_inventory_flow(self):
        status, batch = self.request(
            "/api/batches",
            "POST",
            {
                "game": "One Piece",
                "set_code": "OP16",
                "set_name": "The Azure Sea's Seven",
                "color": "Yellow",
                "finish_group": "Rare / Foil",
                "acquisition_type": "Booster Box",
                "total_cost": 114.99,
            },
        )
        self.assertEqual(status, 201)
        self.assertRegex(batch["batch_code"], r"^OP-B\d{8}-01$")
        _, batch = self.request(
            f"/api/batches/{batch['id']}",
            "PATCH",
            {"color": "Red", "finish_group": "Common / Non-Foil", "location": "OP16-Red"},
        )
        self.assertEqual(batch["location"], "OP16-Red")

        one_pixel_png = "data:image/png;base64," + base64.b64encode(
            base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
            )
        ).decode()
        status, card = self.request(
            f"/api/batches/{batch['id']}/cards",
            "POST",
            {
                "card_number": "OP16-112",
                "name": "Boa Hancock",
                "rarity": "Super Rare",
                "variant": "Standard",
                "front_image": one_pixel_png,
                "back_image": one_pixel_png,
            },
        )
        self.assertEqual(status, 201)
        self.assertRegex(card["sku"], r"^OP-B\d{8}-001$")
        self.assertEqual(card["status"], "IN_STOCK")

        _, updated = self.request(
            f"/api/cards/{card['sku']}",
            "PATCH",
            {
                "market_low": 6.25,
                "market_average": 8.41,
                "market_high": 11.8,
                "listing_platform": "TCGplayer",
                "listing_price": 8.49,
            },
        )
        self.assertEqual(updated["market_average"], 8.41)

        _, inventory = self.request("/api/inventory?sort=average_desc")
        self.assertEqual(len(inventory["groups"]), 1)
        self.assertEqual(inventory["groups"][0]["quantity"], 1)
        with urllib.request.urlopen(self.base + "/api/export/inventory.csv", timeout=5) as response:
            exported = response.read().decode("utf-8-sig")
        self.assertIn(card["sku"], exported)

        _, dash = self.request("/api/dashboard")
        self.assertEqual(dash["tcg_slots"], 1)
        self.assertEqual(dash["labels_waiting"], 0)
        self.request(f"/api/batches/{batch['id']}/complete", "POST", {})
        _, dash = self.request("/api/dashboard")
        self.assertEqual(dash["labels_waiting"], 1)

        status, order = self.request(
            "/api/sales",
            "POST",
            {
                "platform": "TCGplayer",
                "order_number": "TEST-1001",
                "sold_at": "2026-06-17",
                "subtotal": 8.49,
                "shipping_collected": 2.49,
                "platform_fees": 1.12,
                "postage_cost": 0.78,
                "skus": [card["sku"]],
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(order["platform"], "TCGplayer")
        _, sold_card = self.request(f"/api/cards/{card['sku']}")
        self.assertEqual(sold_card["status"], "SOLD")
        _, order_search = self.request("/api/inventory?q=TEST-1001&status=SOLD")
        self.assertEqual(len(order_search["groups"]), 1)
        self.assertEqual(order_search["groups"][0]["copies"][0]["sku"], card["sku"])
        self.request(f"/api/cards/{card['sku']}/recycle", "POST", {"reason": "Audit protection test"})
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request(f"/api/cards/{card['sku']}/purge", "POST", {})
        self.assertEqual(error.exception.code, 400)
        self.request(f"/api/cards/{card['sku']}/restore", "POST", {})

    def test_health_and_static_app(self):
        status, health = self.request("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(health["name"], "Dex")
        self.assertEqual(health["version"], "v2.4-test")
        with urllib.request.urlopen(self.base + "/", timeout=5) as response:
            html = response.read().decode()
        self.assertIn("<title>Dex</title>", html)

    def test_phase1_migration_ledger_initialized(self):
        with self.dex.connect() as db:
            table = db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
            ).fetchone()
        self.assertIsNotNone(table)

    def test_phase2_estimated_economics_api_is_read_only(self):
        _, batch = self.request(
            "/api/batches", "POST",
            {"game": "One Piece", "set_code": "OP16", "acquisition_type": "Booster Box", "total_cost": 120},
        )
        with self.dex.connect() as db:
            before = {
                "cards": db.execute("SELECT COUNT(*) FROM cards").fetchone()[0],
                "activity": db.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0],
                "migrations": db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0],
                "batch": tuple(db.execute("SELECT * FROM batches WHERE id = ?", (batch["id"],)).fetchone()),
            }
        status, estimate = self.request(f"/api/batches/{batch['id']}/economics/estimate")
        self.assertEqual(status, 200)
        self.assertEqual(estimate["state"], "ESTIMATED")
        self.assertEqual(estimate["notice"], "Estimate only. Cost basis not finalized.")
        self.assertIsNone(estimate["acquisition"]["authoritative_cost_cents"])
        with self.dex.connect() as db:
            after = {
                "cards": db.execute("SELECT COUNT(*) FROM cards").fetchone()[0],
                "activity": db.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0],
                "migrations": db.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0],
                "batch": tuple(db.execute("SELECT * FROM batches WHERE id = ?", (batch["id"],)).fetchone()),
            }
        self.assertEqual(after, before)

    def test_phase3_acquisition_facts_receipt_group_audit_and_csv(self):
        common = {
            "game": "One Piece",
            "set_code": "OP16",
            "set_name": "The Time of Battle",
            "color": "Yellow",
            "finish_group": "Sealed",
            "acquisition_type": "Booster Box",
            "economics_mode": "SEALED_RIP",
            "receipt_group_reference": "phase3-receipt-001",
            "invoice_reference": "ORDER-PHASE3",
        }
        status, boxes = self.request(
            "/api/batches", "POST",
            common | {
                "product_name": "OP16 Booster Box",
                "product_code": "OP16-BOX",
                "units_acquired": 6,
                "original_currency": "CAD",
                "original_foreign_amount": "900.00",
                "purchase_subtotal": "600.00",
                "acquisition_tax": "48.00",
                "inbound_shipping": "15.00",
                "acquisition_fees": "2.00",
                "acquisition_discount": "5.00",
                "final_usd_paid": "660.00",
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(boxes["total_cost"], 660.0)
        self.assertEqual(boxes["final_usd_paid_cents"], 66000)

        status, decks = self.request(
            "/api/batches", "POST",
            common | {
                "set_code": "ST27",
                "set_name": "Starter Deck 27",
                "acquisition_type": "Starter Deck",
                "product_name": "ST27 Starter Deck",
                "product_code": "ST27-DECK",
                "units_acquired": 2,
                "purchase_subtotal": "80.00",
                "acquisition_tax": "6.40",
                "inbound_shipping": "0.00",
                "acquisition_fees": "0.00",
                "acquisition_discount": "0.00",
                "final_usd_paid": "86.40",
            },
        )
        self.assertEqual(status, 201)

        _, facts = self.request(f"/api/batches/{boxes['id']}/economics")
        self.assertEqual(facts["authoritative_cost"]["final_usd_paid_cents"], 66000)
        self.assertTrue(facts["cost_breakdown"]["reconciled"])
        self.assertEqual(facts["receipt_group"]["reference"], "PHASE3-RECEIPT-001")
        self.assertEqual(len(facts["receipt_group"]["batches"]), 2)
        self.assertEqual(facts["receipt_group"]["known_assigned_cost_cents"], 74640)
        self.assertIn("not allocated automatically", facts["receipt_group"]["notice"])

        with self.assertRaises(urllib.error.HTTPError) as mismatch_error:
            self.request(
                f"/api/batches/{boxes['id']}/economics", "PATCH",
                {"final_usd_paid": "665.00", "cost_reconciliation_acknowledged": False},
            )
        self.assertEqual(mismatch_error.exception.code, 400)
        mismatch_body = json.loads(mismatch_error.exception.read())
        self.assertIn("$5.00 above", mismatch_body["error"])

        _, updated = self.request(
            f"/api/batches/{boxes['id']}/economics", "PATCH",
            {"final_usd_paid": "665.00", "cost_reconciliation_acknowledged": True},
        )
        self.assertEqual(updated["authoritative_cost"]["final_usd_paid_cents"], 66500)
        self.assertEqual(updated["cost_breakdown"]["difference_cents"], 500)
        self.assertTrue(updated["cost_breakdown"]["acknowledged"])
        with self.dex.connect() as db:
            batch_row = db.execute("SELECT * FROM batches WHERE id = ?", (boxes["id"],)).fetchone()
            audit = db.execute(
                "SELECT action_type, payload FROM activity_log WHERE action_type='ACQUISITION_UPDATE' ORDER BY id DESC"
            ).fetchone()
        self.assertEqual(batch_row["total_cost"], 665.0)
        self.assertEqual(audit["action_type"], "ACQUISITION_UPDATE")
        self.assertIn("final_usd_paid_cents", json.loads(audit["payload"])["changes"])

        with urllib.request.urlopen(self.base + "/api/export/inventory.csv", timeout=5) as response:
            header = response.read().decode("utf-8-sig").splitlines()[0]
        self.assertIn("receipt_group_reference", header)
        self.assertIn("final_usd_paid_cents", header)

        with self.dex.connect() as db:
            db.execute("UPDATE batches SET economics_status='FINALIZED' WHERE id = ?", (decks["id"],))
        with self.assertRaises(urllib.error.HTTPError) as finalized_error:
            self.request(
                f"/api/batches/{decks['id']}/economics", "PATCH",
                {"product_name": "Silently rewritten"},
            )
        self.assertEqual(finalized_error.exception.code, 400)

    def test_phase5_sealed_sale_api_reconciles_and_undo_restores_exact_units(self):
        _, batch = self.request(
            "/api/batches",
            "POST",
            {
                "game": "One Piece",
                "set_code": "OP05",
                "set_name": "Phase 5 Disposable",
                "acquisition_type": "Booster Box",
                "economics_mode": "SEALED_RIP",
                "product_name": "Disposable Phase 5 Boxes",
                "units_acquired": 3,
                "purchase_subtotal": "10.00",
                "final_usd_paid": "10.00",
                "receipt_group_reference": "PHASE5-DISPOSABLE",
            },
        )
        _, sealed = self.request(f"/api/batches/{batch['id']}/sealed-units")
        self.assertEqual([unit["basis_cents"] for unit in sealed["units"]], [334, 333, 333])

        facts = {
            "batch_id": batch["id"],
            "quantity": 2,
            "platform": "eBay",
            "order_number": "PHASE5-API-1",
            "sold_at": "2026-08-14",
            "merchandise_total": "15.00",
            "shipping_collected": "2.00",
            "marketplace_fees": "1.00",
            "actual_postage": "3.00",
            "marketplace_tax": "1.25",
            "request_id": "PHASE5-API-REQUEST-1",
        }
        _, preview = self.request("/api/sealed-sales/preview", "POST", facts)
        self.assertEqual(preview["net_proceeds_cents"], 1300)
        self.assertEqual(preview["sold_basis_cents"], 667)
        self.assertEqual(preview["realized_profit_loss_cents"], 633)
        self.assertEqual([unit["unit_sequence"] for unit in preview["sealed_units"]], [1, 2])

        status, order = self.request("/api/sealed-sales", "POST", facts)
        self.assertEqual(status, 201)
        self.assertEqual(order["order_type"], "SEALED")
        self.assertEqual(order["marketplace_tax_cents"], 125)
        self.assertTrue(order["undo_eligible"])
        self.assertEqual([unit["unit_code"] for unit in order["sealed_units"]], [
            f"{batch['batch_code']}-UNIT-0001",
            f"{batch['batch_code']}-UNIT-0002",
        ])
        _, after = self.request(f"/api/batches/{batch['id']}/sealed-units")
        self.assertEqual(after["counts"], {"remaining": 1, "opened": 0, "sold": 2, "corrected_adjusted": 0})
        self.assertTrue(after["reconciliation"]["reconciled"])

        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request("/api/sealed-sales", "POST", {**facts, "quantity": 2, "request_id": "PHASE5-OVERSELL"})
        self.assertEqual(error.exception.code, 400)
        _, undo = self.request(f"/api/sealed-sales/{order['id']}/undo", "POST", {})
        self.assertEqual(undo["restored_unit_ids"], [unit["id"] for unit in order["sealed_units"]])
        _, restored = self.request(f"/api/batches/{batch['id']}/sealed-units")
        self.assertEqual(restored["counts"]["remaining"], 3)
        _, retained = self.request(f"/api/sealed-sales/{order['id']}")
        self.assertTrue(retained["canceled"])
        self.assertFalse(retained["undo_eligible"])
        self.assertEqual([unit["id"] for unit in retained["sealed_units"]], undo["restored_unit_ids"])
        _, sales = self.request("/api/sales")
        canceled = next(row for row in sales["sales"] if row["id"] == order["id"])
        self.assertIsNotNone(canceled["canceled_at"])

    def test_phase6_batch_report_group_rollup_and_exports_are_read_only(self):
        _, batch = self.request(
            "/api/batches",
            "POST",
            {
                "game": "One Piece",
                "set_code": "OP06",
                "set_name": "Phase 6 Disposable",
                "acquisition_type": "Booster Box",
                "economics_mode": "SEALED_RIP",
                "product_name": "Disposable Phase 6 Boxes",
                "units_acquired": 2,
                "purchase_subtotal": "20.00",
                "final_usd_paid": "20.00",
                "receipt_group_reference": "PHASE6-API-GROUP",
            },
        )
        with self.dex.connect() as db:
            before = {
                "changes": db.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0],
                "batch": tuple(db.execute("SELECT * FROM batches WHERE id=?", (batch["id"],)).fetchone()),
                "units": [tuple(row) for row in db.execute(
                    "SELECT * FROM sealed_units WHERE batch_id=? ORDER BY id", (batch["id"],)
                )],
            }

        status, report = self.request(f"/api/batches/{batch['id']}/economics/report")
        self.assertEqual(status, 200)
        self.assertEqual(report["calculation_version"], self.dex.CALCULATION_VERSION)
        self.assertEqual(report["summary"]["authoritative_cost_cents"], 2000)
        self.assertEqual(report["remaining"]["remaining_sealed_unit_count"], 2)
        self.assertFalse(report["remaining"]["market"]["complete"])
        self.assertEqual(report["remaining"]["market"]["freshness_label"], "Freshness Unknown")
        self.assertIsNotNone(report["receipt_group_rollup"])

        _, group = self.request("/api/acquisition-groups/PHASE6-API-GROUP/economics")
        self.assertEqual(group["authoritative_assigned_cost_cents"], 2000)
        self.assertEqual(group["realized"]["unique_order_count"], 0)
        self.assertIn("Informational aggregation only", group["notice"])

        with urllib.request.urlopen(
            self.base + f"/api/export/batch-economics.csv?batch_id={batch['id']}", timeout=5
        ) as response:
            export = response.read().decode("utf-8-sig")
        header, row = export.splitlines()[:2]
        self.assertIn("calculation_version", header)
        self.assertIn("current_economic_position_cents", header)
        self.assertIn(batch["batch_code"], row)

        with urllib.request.urlopen(self.base + "/api/export/sales.csv", timeout=5) as response:
            sales_header = response.read().decode("utf-8-sig").splitlines()[0]
        self.assertIn("economics_included,attribution_method,attributed_batch_ids", sales_header)
        self.assertTrue(sales_header.endswith("effective_realized_profit_loss_cents,returned_item_count"))

        with self.dex.connect() as db:
            after = {
                "changes": db.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0],
                "batch": tuple(db.execute("SELECT * FROM batches WHERE id=?", (batch["id"],)).fetchone()),
                "units": [tuple(row) for row in db.execute(
                    "SELECT * FROM sealed_units WHERE batch_id=? ORDER BY id", (batch["id"],)
                )],
            }
        self.assertEqual(after, before)

    def test_scan_filename_pairing(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = [Path(folder) / name for name in ("001_front.png", "001_back.png", "002.png", "003.png")]
            for path in paths:
                path.write_bytes(b"scan")
            pairs = self.dex.pair_scan_files(paths)
            self.assertEqual(pairs[0], (paths[0], paths[1]))
            self.assertEqual(pairs[1], (paths[2], paths[3]))
            back_first = self.dex.pair_scan_files(paths, "BACK_FIRST")
            self.assertEqual(back_first[0], (paths[0], paths[1]))
            self.assertEqual(back_first[1], (paths[3], paths[2]))

    def test_v11a_recycle_swap_and_label_gating(self):
        _, batch = self.request(
            "/api/batches", "POST",
            {"game": "One Piece", "set_code": "OP16", "set_name": "The Time of Battle",
             "acquisition_type": "Existing Inventory", "scan_order": "FRONT_FIRST"},
        )
        one_pixel_png = "data:image/png;base64," + base64.b64encode(
            base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
            )
        ).decode()
        _, card = self.request(
            f"/api/batches/{batch['id']}/cards", "POST",
            {"front_image": one_pixel_png, "back_image": one_pixel_png},
        )
        original_front, original_back = card["front_image"], card["back_image"]
        _, swapped = self.request(f"/api/cards/{card['sku']}/swap-images", "POST", {})
        self.assertEqual(swapped["front_image"], original_back)
        self.assertEqual(swapped["back_image"], original_front)

        _, dash = self.request("/api/dashboard")
        open_labels = dash["labels_waiting"]
        self.request(f"/api/batches/{batch['id']}/complete", "POST", {})
        _, dash = self.request("/api/dashboard")
        self.assertEqual(dash["labels_waiting"], open_labels + 1)

        _, recycled = self.request(
            f"/api/cards/{card['sku']}/recycle", "POST", {"reason": "Duplicate test scan"}
        )
        self.assertIsNotNone(recycled["recycled_at"])
        _, recycle_bin = self.request("/api/recycle")
        self.assertIn(card["sku"], {item["sku"] for item in recycle_bin["cards"]})
        _, inventory = self.request(f"/api/inventory?q={card['sku']}")
        self.assertEqual(inventory["groups"], [])

        _, restored = self.request(f"/api/cards/{card['sku']}/restore", "POST", {})
        self.assertIsNone(restored["recycled_at"])
        _, inventory = self.request(f"/api/inventory?q={card['sku']}")
        self.assertEqual(len(inventory["groups"]), 1)

        self.request(f"/api/cards/{card['sku']}/recycle", "POST", {"reason": "Purge test"})
        _, purged = self.request(f"/api/cards/{card['sku']}/purge", "POST", {})
        self.assertTrue(purged["purged"])

    def test_v11_batch_settings_exports_and_undo(self):
        _, settings = self.request("/api/settings")
        self.assertEqual(settings["tcg_capacity"], 500)
        _, settings = self.request(
            "/api/settings", "POST", {"timezone": "America/New_York", "tcg_capacity": 500}
        )
        self.assertEqual(settings["tcg_capacity"], 500)

        _, batch = self.request(
            "/api/batches", "POST",
            {"game": "One Piece", "set_code": "OP16", "acquisition_type": "Booster Box"},
        )
        one_pixel_png = "data:image/png;base64," + base64.b64encode(
            base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
            )
        ).decode()
        status, result = self.request(
            f"/api/batches/{batch['id']}/cards/bulk", "POST",
            {"cards": [
                {"front_image": one_pixel_png, "back_image": one_pixel_png},
                {"front_image": one_pixel_png, "back_image": one_pixel_png},
            ]},
        )
        self.assertEqual(status, 201)
        self.assertEqual(result["created"], 2)
        self.assertEqual(len({card["sku"] for card in result["cards"]}), 2)

        _, completed = self.request(f"/api/batches/{batch['id']}/complete", "POST", {})
        self.assertEqual(completed["status"], "COMPLETE")
        _, reopened = self.request(f"/api/batches/{batch['id']}/reopen", "POST", {})
        self.assertEqual(reopened["status"], "OPEN")
        _, added = self.request(
            f"/api/batches/{batch['id']}/cards", "POST",
            {"card_number": "OP16-001", "name": "Test Card"},
        )
        self.assertNotIn(added["sku"], {card["sku"] for card in result["cards"]})

        _, dash = self.request("/api/dashboard")
        self.assertEqual(dash["tcg_capacity"], 500)
        self.assertGreaterEqual(dash["needs_review"], 2)
        self.assertLess(dash["in_stock"], dash["physically_available"])

        with urllib.request.urlopen(self.base + "/api/export/sales.csv", timeout=5) as response:
            sales_csv = response.read().decode("utf-8-sig")
        self.assertIn("net_proceeds", sales_csv)

        _, undo = self.request("/api/undo", "POST", {})
        self.assertIn("Undone", "Undone: " + undo["undone"])

    def test_v11b_batch_recycle_and_undo(self):
        _, batch = self.request(
            "/api/batches", "POST",
            {"game": "One Piece", "set_code": "OP16", "acquisition_type": "Booster Box"},
        )
        one_pixel_png = "data:image/png;base64," + base64.b64encode(
            base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
            )
        ).decode()
        _, result = self.request(
            f"/api/batches/{batch['id']}/cards/bulk", "POST",
            {"cards": [
                {"front_image": one_pixel_png, "back_image": one_pixel_png},
                {"front_image": one_pixel_png, "back_image": one_pixel_png},
            ]},
        )
        skus = {card["sku"] for card in result["cards"]}
        _, recycled = self.request(
            f"/api/batches/{batch['id']}/recycle", "POST",
            {"reason": "Duplicate batch test"},
        )
        self.assertEqual(recycled["recycled"], 2)
        self.assertIsNotNone(recycled["batch"]["recycled_at"])

        _, batches = self.request("/api/batches")
        self.assertNotIn(batch["id"], {item["id"] for item in batches["batches"]})
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request(f"/api/batches/{batch['id']}")
        self.assertEqual(error.exception.code, 404)

        _, recycle_bin = self.request(f"/api/recycle?q={batch['batch_code']}")
        self.assertTrue(skus.issubset({item["sku"] for item in recycle_bin["cards"]}))

        _, undo = self.request("/api/undo", "POST", {})
        self.assertIn(batch["batch_code"], undo["undone"])
        _, restored_batch = self.request(f"/api/batches/{batch['id']}")
        self.assertEqual({card["sku"] for card in restored_batch["cards"]}, skus)

    def test_v20_sam_source_scan_and_match(self):
        raw_png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        source_dir = self.dex.SOURCE_DB_DIR
        (source_dir / "OP16").mkdir(parents=True, exist_ok=True)
        (source_dir / "OP16" / "OP16-067.png").write_bytes(raw_png)
        (source_dir / "cards.csv").write_text(
            "card_number,name,set_code,set_name,rarity,color,card_type\n"
            "OP16-067,Tsuru,OP16,The Time of Battle,Uncommon,Purple,Character\n",
            encoding="utf-8",
        )

        _, source = self.request("/api/sam/source/rescan", "POST", {})
        self.assertGreaterEqual(source["indexed"], 1)
        self.assertGreaterEqual(source["summary"]["with_images"], 1)

        _, batch = self.request(
            "/api/batches", "POST",
            {"game": "One Piece", "set_code": "OP16", "set_name": "The Time of Battle",
             "color": "Purple", "acquisition_type": "Booster Box"},
        )
        scan = "data:image/png;base64," + base64.b64encode(raw_png).decode()
        _, result = self.request(
            f"/api/batches/{batch['id']}/cards/bulk", "POST",
            {"cards": [{"front_image": scan}]},
        )
        sku = result["cards"][0]["sku"]
        _, match = self.request(f"/api/cards/{sku}/sam", "POST", {})
        self.assertTrue(match["matched"])
        self.assertGreaterEqual(match["confidence"], 0.84)

        _, card = self.request(f"/api/cards/{sku}")
        self.assertEqual(card["card_number"], "OP16-067")
        self.assertEqual(card["name"], "Tsuru")
        self.assertEqual(card["rarity"], "")
        self.assertIsNone(card["sam_printing_id"])
        self.assertEqual(card["sam_printing_certainty"], "UNRESOLVED")
        self.assertEqual(card["color"], "Purple")
        self.assertEqual(card["status"], "IN_STOCK")
        self.assertEqual(card["match_source"], "Image Fingerprint")

    def test_v20_upgrade_adds_sam_columns_before_indexes(self):
        with tempfile.TemporaryDirectory() as legacy_root:
            legacy_root = Path(legacy_root)
            db_path = legacy_root / "data" / "dex.db"
            db_path.parent.mkdir(parents=True)
            legacy = sqlite3.connect(db_path)
            try:
                legacy.executescript(
                    """
                    CREATE TABLE batches (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        batch_code TEXT NOT NULL UNIQUE,
                        created_at TEXT NOT NULL,
                        completed_at TEXT,
                        status TEXT NOT NULL DEFAULT 'OPEN',
                        game TEXT NOT NULL,
                        set_code TEXT NOT NULL,
                        set_name TEXT NOT NULL DEFAULT '',
                        color TEXT NOT NULL DEFAULT '',
                        finish_group TEXT NOT NULL DEFAULT 'Non-Foil',
                        default_condition TEXT NOT NULL DEFAULT 'Near Mint',
                        acquisition_type TEXT NOT NULL,
                        total_cost REAL NOT NULL DEFAULT 0,
                        location TEXT NOT NULL DEFAULT '',
                        notes TEXT NOT NULL DEFAULT ''
                    );
                    CREATE TABLE cards (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        sku TEXT NOT NULL UNIQUE,
                        batch_id INTEGER NOT NULL REFERENCES batches(id),
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        card_number TEXT NOT NULL DEFAULT '',
                        name TEXT NOT NULL DEFAULT 'Needs identification',
                        set_name TEXT NOT NULL DEFAULT '',
                        rarity TEXT NOT NULL DEFAULT '',
                        color TEXT NOT NULL DEFAULT '',
                        variant TEXT NOT NULL DEFAULT 'Standard',
                        condition TEXT NOT NULL DEFAULT 'Near Mint',
                        status TEXT NOT NULL DEFAULT 'REVIEW',
                        location TEXT NOT NULL DEFAULT '',
                        front_image TEXT,
                        back_image TEXT,
                        source_hash TEXT,
                        label_printed INTEGER NOT NULL DEFAULT 0,
                        market_low REAL,
                        market_average REAL,
                        market_high REAL,
                        market_updated_at TEXT,
                        listing_platform TEXT,
                        listing_price REAL,
                        listing_reference TEXT
                    );
                    """
                )
                legacy.commit()
            finally:
                legacy.close()

            saved = (
                self.dex.DATA_DIR,
                self.dex.DB_PATH,
                self.dex.IMAGE_DIR,
                self.dex.INBOUND_DIR,
                self.dex.SOURCE_DB_DIR,
            )
            try:
                self.dex.DATA_DIR = legacy_root / "data"
                self.dex.DB_PATH = db_path
                self.dex.IMAGE_DIR = legacy_root / "data" / "images"
                self.dex.INBOUND_DIR = legacy_root / "data" / "inbound"
                self.dex.SOURCE_DB_DIR = legacy_root / "source-database"
                self.dex.init_db()
                with self.dex.connect() as db:
                    columns = {row["name"] for row in db.execute("PRAGMA table_info(cards)")}
                    indexes = {row["name"] for row in db.execute("PRAGMA index_list(cards)")}
                    batch_columns = {row["name"] for row in db.execute("PRAGMA table_info(batches)")}
                    migration = db.execute(
                        "SELECT migration_id FROM schema_migrations WHERE migration_id='0001_phase3_acquisition_facts'"
                    ).fetchone()
                self.assertIn("source_card_id", columns)
                self.assertIn("match_confidence", columns)
                self.assertIn("idx_cards_source", indexes)
                self.assertIn("final_usd_paid_cents", batch_columns)
                self.assertIn("receipt_group_reference", batch_columns)
                self.assertIsNotNone(migration)
            finally:
                (
                    self.dex.DATA_DIR,
                    self.dex.DB_PATH,
                    self.dex.IMAGE_DIR,
                    self.dex.INBOUND_DIR,
                    self.dex.SOURCE_DB_DIR,
                ) = saved


if __name__ == "__main__":
    unittest.main()
