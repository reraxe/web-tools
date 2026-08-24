import sqlite3
import tempfile
import threading
import unittest
import json
import urllib.request
from pathlib import Path
from unittest.mock import patch

import app
from dex_batch_economics import acquisition_group_economics_payload, batch_economics_payload
from dex_migrations import DEFAULT_MIGRATIONS, MigrationError, apply_migrations
from dex_post_sale import (
    create_chargeback,
    create_fee_credit,
    create_postage_refund,
    create_refund,
    create_return,
    create_sale_correction,
    financial_facts,
    order_payload,
    reverse_event,
)
from dex_sealed import create_sealed_sale, synchronize_sealed_units
from tests.test_phase5_sealed import base_schema


class Phase7BFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.db_path = root / "phase7b.db"
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

    def add_singles_batch(self, batch_id=1, card_count=2, group="P7B-RECEIPT"):
        self.db.execute(
            """INSERT INTO batches
               (id,batch_code,created_at,status,game,set_code,acquisition_type,total_cost,
                economics_mode,economics_status,product_name,receipt_group_reference,
                final_usd_paid_cents,units_acquired)
               VALUES (?,?,'2026-08-14','OPEN','One Piece','OP16','Singles',10,
                       'SINGLES_LUMP_SUM','FINALIZED','Phase 7B singles',?,1000,0)""",
            (batch_id, f"OP-P7B-{batch_id:02d}", group),
        )
        rip_id = self.db.execute(
            """INSERT INTO rip_sessions
               (rip_code,batch_id,status,units_opened,allocation_method,bulk_mode,
                consumed_cost_cents,scanned_basis_cents,bulk_basis_cents,total_allocated_cents,
                difference_cents,cards_accounted_confirmed,created_at,finalized_at)
               VALUES (?,?,'FINALIZED',0,'EQUAL','NONE',1000,1000,0,1000,0,1,
                       '2026-08-14','2026-08-14')""",
            (f"RIP-P7B-{batch_id:02d}", batch_id),
        ).lastrowid
        self.db.execute(
            """INSERT INTO rip_economic_events
               (event_id,request_id,rip_session_id,event_type,effective_at,recorded_at,reason_code,notes,payload)
               VALUES (?,?,?,'FINALIZATION','2026-08-14','2026-08-14','INITIAL','fixture','{}')""",
            (f"P7B-FINAL-{batch_id}", f"P7B-FINAL-REQ-{batch_id}", rip_id),
        )
        ids = []
        base, remainder = divmod(1000, card_count)
        for sequence in range(1, card_count + 1):
            card_id = self.db.execute(
                """INSERT INTO cards
                   (sku,batch_id,created_at,updated_at,name,status,rip_session_id)
                   VALUES (?,?,'2026-08-14','2026-08-14',?,'IN_STOCK',?)""",
                (f"OP-P7B-{batch_id:02d}-{sequence:03d}", batch_id, f"Card {sequence}", rip_id),
            ).lastrowid
            ids.append(card_id)
            self.db.execute(
                """INSERT INTO rip_basis_events
                   (event_id,rip_session_id,target_type,card_id,amount_delta_cents,created_at)
                   VALUES (?,?,'CARD',?,?,'2026-08-14')""",
                (f"P7B-FINAL-{batch_id}", rip_id, card_id, base + (1 if sequence <= remainder else 0)),
            )
        return ids

    def card_order(self, card_ids, *, merchandise=2000, shipping=200, fees=300, postage=400, number="P7B-CARD"):
        order_id = self.db.execute(
            """INSERT INTO sale_orders
               (platform,order_number,sold_at,subtotal,shipping_collected,platform_fees,
                postage_cost,notes,order_type,merchandise_total_cents,
                shipping_collected_cents,marketplace_fees_cents,actual_postage_cents)
               VALUES ('eBay',?,'2026-08-14',?,?,?,?,?,'CARD',?,?,?,?)""",
            (number, merchandise / 100, shipping / 100, fees / 100, postage / 100, "",
             merchandise, shipping, fees, postage),
        ).lastrowid
        for card_id in card_ids:
            self.db.execute("INSERT INTO sale_items (order_id,card_id,sale_price) VALUES (?,?,?)", (order_id, card_id, merchandise / 100 / len(card_ids)))
            self.db.execute("UPDATE cards SET status='SOLD' WHERE id=?", (card_id,))
        return order_id


class Phase7BMigrationTest(unittest.TestCase):
    def test_legacy_sale_item_ids_survive_and_returned_card_can_be_sold_again(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        base_schema(db)
        db.execute("INSERT INTO batches (id,batch_code) VALUES (1,'LEGACY-P7B')")
        db.execute("INSERT INTO cards (id,sku,batch_id) VALUES (1,'LEGACY-CARD',1)")
        db.execute("INSERT INTO sale_orders (id,platform,sold_at) VALUES (1,'eBay','2026-08-01')")
        db.execute("INSERT INTO sale_items (id,order_id,card_id,sale_price) VALUES (9,1,1,5.00)")
        apply_migrations(db, DEFAULT_MIGRATIONS[:4])
        self.assertEqual(
            apply_migrations(db),
            (
                "0005_phase7b_post_sale_events",
                "0006_v22_phase1_inbound_acquisitions",
                "0007_v22_phase2_manual_acquisition_wizard",
                "0008_v22_phase2_ux_revision",
                "0009_v22_phase3_product_catalog_upc",
                "0010_v22_phase4_source_documents",
                "0011_v22_phase5_receipt_intelligence",
                "0012_v22_prephase_ux_safety_hotfix",
                "0013_v22_phase6_downstream_intake_bridge",
                "0014_v22_phase7_sam_recognition",
                "0015_v22_rc3_hf1_mixed_purchase_reconciliation",
                "0016_v23_inventory_intelligence_phase1_receipt_semantics",
                "0017_v24_sam_phase1_family_printing",
                "0018_v24_jarvis_economics_sam_phase2",
            ),
        )
        self.assertEqual(tuple(db.execute("SELECT id,order_id,card_id,sale_price FROM sale_items").fetchone()), (9, 1, 1, 5.0))
        db.execute("INSERT INTO sale_orders (id,platform,sold_at) VALUES (2,'eBay','2026-08-02')")
        db.execute("INSERT INTO sale_items (order_id,card_id,sale_price) VALUES (2,1,6.00)")
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("INSERT INTO sale_items (order_id,card_id,sale_price) VALUES (2,1,7.00)")
        self.assertEqual(apply_migrations(db), ())
        db.close()

    def test_failed_phase7b_migration_rolls_back_sale_item_rebuild_and_marker(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        base_schema(db)
        db.execute("INSERT INTO batches (id,batch_code) VALUES (1,'ROLLBACK-P7B')")
        db.execute("INSERT INTO cards (id,sku,batch_id) VALUES (1,'ROLLBACK-CARD',1)")
        db.execute("INSERT INTO sale_orders (id,platform,sold_at) VALUES (1,'eBay','2026-08-01')")
        db.execute("INSERT INTO sale_items (id,order_id,card_id,sale_price) VALUES (4,1,1,5.00)")
        apply_migrations(db, DEFAULT_MIGRATIONS[:4])
        db.execute("CREATE TABLE post_sale_events (sentinel TEXT)")
        db.commit()
        with self.assertRaises(MigrationError):
            apply_migrations(db)
        self.assertIsNone(db.execute("SELECT 1 FROM schema_migrations WHERE migration_id='0005_phase7b_post_sale_events'").fetchone())
        self.assertEqual(tuple(db.execute("SELECT id,order_id,card_id,sale_price FROM sale_items").fetchone()), (4, 1, 1, 5.0))
        db.execute("INSERT INTO sale_orders (id,platform,sold_at) VALUES (2,'eBay','2026-08-02')")
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("INSERT INTO sale_items (order_id,card_id,sale_price) VALUES (2,1,6.00)")
        self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='post_sale_return_items'").fetchone())
        db.close()


class Phase7BFinancialTest(Phase7BFixture):
    def test_http_api_exposes_original_and_effective_facts_and_duplicate_safe_events(self):
        card_id = self.add_singles_batch(card_count=1)[0]
        order_id = self.card_order([card_id])
        self.db.commit()
        with patch.object(app, "DB_PATH", self.db_path):
            server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.DexHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"

            def request(path, method="GET", payload=None):
                body = None if payload is None else json.dumps(payload).encode()
                req = urllib.request.Request(base + path, data=body, method=method, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=5) as response:
                    return response.status, json.loads(response.read())

            try:
                event_payload = {"request_id": "API-P7B-REFUND", "reason_code": "CUSTOMER_REQUEST", "merchandise_amount": "1.25", "shipping_amount": "0"}
                status, event = request(f"/api/sales/{order_id}/refunds", "POST", event_payload)
                self.assertEqual(status, 201)
                self.assertEqual(request(f"/api/sales/{order_id}/refunds", "POST", event_payload)[1]["event_id"], event["event_id"])
                detail = request(f"/api/sales/{order_id}")[1]
                self.assertEqual(detail["financials"]["original"]["net_proceeds_cents"], 1500)
                self.assertEqual(detail["financials"]["effective"]["net_proceeds_cents"], 1375)
                self.assertEqual(detail["post_sale_event_count"], 1)
                sales = request("/api/sales")[1]["sales"]
                self.assertEqual(sales[0]["net_proceeds_cents"], 1375)
            finally:
                server.shutdown(); thread.join(timeout=3); server.server_close()

    def test_distinct_financial_events_are_idempotent_append_only_and_reversible(self):
        cards = self.add_singles_batch(card_count=1)
        order_id = self.card_order(cards)
        refund = create_refund(self.db, order_id, {
            "request_id": "REFUND-1", "reason_code": "CUSTOMER_REQUEST",
            "merchandise_amount": "5.00", "shipping_amount": "1.00",
        })
        duplicate = create_refund(self.db, order_id, {
            "request_id": "REFUND-1", "reason_code": "OTHER",
            "merchandise_amount": "999", "notes": "duplicate payload is ignored",
        })
        self.assertEqual(refund["event_id"], duplicate["event_id"])
        create_chargeback(self.db, order_id, {
            "request_id": "CHARGEBACK-1", "reason_code": "PAYMENT_DISPUTE", "amount": "2.00"
        })
        fee = create_fee_credit(self.db, order_id, {
            "request_id": "FEE-1", "reason_code": "MARKETPLACE_CREDIT", "amount": "1.00"
        })
        create_postage_refund(self.db, order_id, {
            "request_id": "POSTAGE-1", "reason_code": "CARRIER_REFUND", "amount": "1.50"
        })
        create_sale_correction(self.db, order_id, {
            "request_id": "CORRECT-1", "reason_code": "DATA_ENTRY_ERROR",
            "notes": "Shipping adjustment from marketplace statement.", "shipping_delta": "0.50"
        })
        facts = financial_facts(self.db, order_id)
        self.assertEqual(facts["original"]["net_proceeds_cents"], 1500)
        self.assertEqual(facts["effective"]["net_proceeds_cents"], 1000)
        reversal = reverse_event(self.db, fee["event_id"], {
            "request_id": "REVERSE-FEE-1", "reason_code": "DATA_ENTRY_ERROR",
            "notes": "Marketplace credit was posted to another order."
        })
        self.assertEqual(reversal["reverses_event_id"], fee["event_id"])
        self.assertEqual(financial_facts(self.db, order_id)["effective"]["net_proceeds_cents"], 900)
        original = self.db.execute("SELECT merchandise_total_cents,shipping_collected_cents,marketplace_fees_cents,actual_postage_cents FROM sale_orders WHERE id=?", (order_id,)).fetchone()
        self.assertEqual(tuple(original), (2000, 200, 300, 400))
        self.assertEqual(self.db.execute("SELECT status FROM cards WHERE id=?", (cards[0],)).fetchone()[0], "SOLD")

    def test_full_refund_uses_backend_remaining_revenue_and_does_not_restore_inventory(self):
        card_id = self.add_singles_batch(card_count=1)[0]
        order_id = self.card_order([card_id], merchandise=1000, shipping=250, fees=100, postage=200)
        create_refund(self.db, order_id, {
            "request_id": "FULL-FIRST-PARTIAL", "reason_code": "CUSTOMER_REQUEST",
            "merchandise_amount": "2.00", "shipping_amount": "0.50",
        })
        full = create_refund(self.db, order_id, {
            "request_id": "FULL-REMAINDER", "reason_code": "ORDER_CANCELLATION",
        }, full=True)
        self.assertEqual(full["event_type"], "FULL_REFUND")
        self.assertEqual(full["payload"], {"merchandise_refund_cents": 800, "shipping_refund_cents": 200})
        self.assertEqual(financial_facts(self.db, order_id)["effective"]["net_proceeds_cents"], -300)
        self.assertEqual(self.db.execute("SELECT status FROM cards WHERE id=?", (card_id,)).fetchone()[0], "SOLD")

    def test_refund_never_restores_inventory_but_confirmed_return_restores_exact_card_once(self):
        card_id = self.add_singles_batch(card_count=1)[0]
        order_id = self.card_order([card_id])
        sale_item_id = self.db.execute("SELECT id FROM sale_items WHERE order_id=?", (order_id,)).fetchone()[0]
        create_refund(self.db, order_id, {
            "request_id": "REFUND-NO-RETURN", "reason_code": "CUSTOMER_REQUEST",
            "merchandise_amount": "2.00", "shipping_amount": "0.00",
        })
        self.assertEqual(self.db.execute("SELECT status FROM cards WHERE id=?", (card_id,)).fetchone()[0], "SOLD")
        returned = create_return(self.db, order_id, {
            "request_id": "RETURN-1", "reason_code": "CUSTOMER_RETURN",
            "physical_received_confirmed": True, "condition_confirmed": True,
            "items": [{"item_type": "CARD", "sale_item_id": sale_item_id, "outcome": "RESTOCKED"}],
        })
        self.assertEqual(self.db.execute("SELECT status FROM cards WHERE id=?", (card_id,)).fetchone()[0], "IN_STOCK")
        self.assertEqual(order_payload(self.db, order_id)["sold_basis_cents"], 0)
        with self.assertRaisesRegex(ValueError, "already been returned"):
            create_return(self.db, order_id, {
                "request_id": "RETURN-2", "reason_code": "CUSTOMER_RETURN",
                "physical_received_confirmed": True, "condition_confirmed": True,
                "items": [{"item_type": "CARD", "sale_item_id": sale_item_id, "outcome": "RESTOCKED"}],
            })
        reverse_event(self.db, returned["event_id"], {
            "request_id": "RETURN-REV-1", "reason_code": "DATA_ENTRY_ERROR",
            "notes": "Physical receipt was assigned to the wrong order."
        })
        self.assertEqual(self.db.execute("SELECT status FROM cards WHERE id=?", (card_id,)).fetchone()[0], "SOLD")
        self.assertEqual(order_payload(self.db, order_id)["sold_basis_cents"], 1000)

    def test_two_concurrent_return_requests_restore_one_exact_identity_at_most_once(self):
        card_id = self.add_singles_batch(card_count=1)[0]
        order_id = self.card_order([card_id])
        sale_item_id = self.db.execute("SELECT id FROM sale_items WHERE order_id=?", (order_id,)).fetchone()[0]
        self.db.commit()
        barrier = threading.Barrier(2)
        outcomes = []

        def worker(sequence):
            connection = sqlite3.connect(self.db_path, timeout=10)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            try:
                barrier.wait()
                connection.execute("BEGIN IMMEDIATE")
                create_return(connection, order_id, {
                    "request_id": f"CONCURRENT-RETURN-{sequence}", "reason_code": "CUSTOMER_RETURN",
                    "physical_received_confirmed": True, "condition_confirmed": True,
                    "items": [{"item_type": "CARD", "sale_item_id": sale_item_id, "outcome": "RESTOCKED"}],
                })
                connection.commit(); outcomes.append("created")
            except ValueError as exc:
                connection.rollback(); outcomes.append(str(exc))
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(sequence,)) for sequence in (1, 2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=12)
        self.assertEqual(outcomes.count("created"), 1)
        self.assertTrue(any("already been returned" in result or "not currently held" in result for result in outcomes if result != "created"))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM post_sale_return_items WHERE entity_id=?", (card_id,)).fetchone()[0], 1)

    def test_damaged_card_and_exact_sealed_return_route_to_expected_states(self):
        card_id = self.add_singles_batch(card_count=1)[0]
        card_order = self.card_order([card_id])
        card_item = self.db.execute("SELECT id FROM sale_items WHERE order_id=?", (card_order,)).fetchone()[0]
        create_return(self.db, card_order, {
            "request_id": "DAMAGED-CARD", "reason_code": "CUSTOMER_RETURN",
            "physical_received_confirmed": True, "condition_confirmed": True,
            "items": [{"item_type": "CARD", "sale_item_id": card_item, "outcome": "DAMAGED_EXCLUDED"}],
        })
        damaged = self.db.execute("SELECT status,recycle_reason,recycled_at FROM cards WHERE id=?", (card_id,)).fetchone()
        self.assertEqual((damaged["status"], damaged["recycle_reason"]), ("HOLD", "RETURN_DAMAGED"))
        self.assertTrue(damaged["recycled_at"])

        self.db.execute(
            """INSERT INTO batches
               (id,batch_code,created_at,status,game,set_code,acquisition_type,total_cost,
                economics_mode,economics_status,product_name,final_usd_paid_cents,units_acquired)
               VALUES (2,'OP-P7B-SEALED','2026-08-14','OPEN','One Piece','OP16','Box',10,
                       'SEALED_RIP','FINALIZED','Sealed fixture',1000,2)"""
        )
        synchronize_sealed_units(self.db, 2)
        sealed = create_sealed_sale(self.db, {
            "batch_id": 2, "quantity": 1, "platform": "eBay", "order_number": "SEALED-RETURN",
            "sold_at": "2026-08-14", "merchandise_total": "8.00", "shipping_collected": "0",
            "marketplace_fees": "1.00", "actual_postage": "2.00", "marketplace_tax": "0",
            "request_id": "SEALED-SALE-P7B",
        }, "2026-08-14")
        sealed_item = self.db.execute("SELECT id,sealed_unit_id FROM sealed_sale_items WHERE order_id=?", (sealed["id"],)).fetchone()
        create_return(self.db, sealed["id"], {
            "request_id": "SEALED-RETURN-1", "reason_code": "CUSTOMER_RETURN",
            "physical_received_confirmed": True, "condition_confirmed": True,
            "items": [{"item_type": "SEALED_UNIT", "sale_item_id": sealed_item["id"], "outcome": "RESTOCKED"}],
        })
        unit = self.db.execute("SELECT status,current_order_id FROM sealed_units WHERE id=?", (sealed_item["sealed_unit_id"],)).fetchone()
        self.assertEqual((unit["status"], unit["current_order_id"]), ("REMAINING", None))

    def test_cross_batch_refund_reuses_stable_order_attribution_exactly_once(self):
        first = self.add_singles_batch(1, 1, "SHARED-P7B")[0]
        second = self.add_singles_batch(2, 1, "SHARED-P7B")[0]
        order_id = self.card_order([first, second], merchandise=1000, shipping=0, fees=0, postage=0)
        create_refund(self.db, order_id, {
            "request_id": "CROSS-REFUND", "reason_code": "CUSTOMER_REQUEST",
            "merchandise_amount": "2.00", "shipping_amount": "0",
        })
        first_report = batch_economics_payload(self.db, 1)
        second_report = batch_economics_payload(self.db, 2)
        group = acquisition_group_economics_payload(self.db, "SHARED-P7B")
        self.assertEqual(first_report["realized"]["net_proceeds_cents"], 400)
        self.assertEqual(second_report["realized"]["net_proceeds_cents"], 400)
        self.assertEqual(group["realized"]["net_proceeds_cents"], 800)
        self.assertEqual(group["realized"]["unique_order_count"], 1)


class Phase7BUiAndPackagingTest(unittest.TestCase):
    def test_runtime_package_api_and_frontend_contract(self):
        root = Path(__file__).parents[1]
        dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
        app_source = (root / "app.py").read_text(encoding="utf-8")
        javascript = (root / "static" / "app.js").read_text(encoding="utf-8")
        index = (root / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn("COPY dex_post_sale.py ./", dockerfile)
        self.assertIn('RUN python -c "import dex_post_sale"', dockerfile)
        for route in ("refunds", "full-refund", "returns", "chargebacks", "fee-credits", "postage-refunds", "corrections", "post-sale-events"):
            self.assertIn(route, app_source)
        for label in ("Original recorded facts", "Effective Realized Economics", "Partial refund", "Customer return", "Chargeback", "Marketplace fee credit", "Postage refund", "Sale-level correction"):
            self.assertIn(label, javascript)
        self.assertIn("v2.2-test-inbound-phase6-intake-bridge", index)
        self.assertNotIn("sale.fees_effective_cents + sale.postage_effective_cents", javascript)
