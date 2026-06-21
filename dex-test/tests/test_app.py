import base64
import importlib.util
import json
import os
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
        os.environ.update(
            {
                "DEX_DATA_DIR": str(root / "data"),
                "DEX_DB_PATH": str(root / "data" / "dex.db"),
                "DEX_IMAGE_DIR": str(root / "data" / "images"),
                "DEX_INBOUND_DIR": str(root / "data" / "inbound"),
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

    def request(self, path, method="GET", body=None):
        payload = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            self.base + path,
            data=payload,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
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
        self.assertEqual(health["version"], "v1.1b-test")
        with urllib.request.urlopen(self.base + "/", timeout=5) as response:
            html = response.read().decode()
        self.assertIn("<title>Dex</title>", html)

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


if __name__ == "__main__":
    unittest.main()
