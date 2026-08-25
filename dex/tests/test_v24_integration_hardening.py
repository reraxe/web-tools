import json
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import app
from dex_economics import allocate_cents
from dex_jarvis_economics import (
    aggregate_economics_payload,
    capture_sale_input_evidence,
    card_economics_payload,
    sale_economics_payload,
    valuation_freshness,
)
from dex_migrations import DEFAULT_MIGRATIONS, apply_migrations
from dex_sam_identity import evaluate_printing_candidates, identity_payload, record_assertion
from tests.test_phase5_sealed import base_schema


class IntegrationFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.db_path = root / "integration.db"
        self.patches = [
            patch.object(app, "DB_PATH", self.db_path),
            patch.object(app, "DATA_DIR", root),
            patch.object(app, "IMAGE_DIR", root / "images"),
            patch.object(app, "INBOUND_DIR", root / "inbound"),
            patch.object(app, "SOURCE_DB_DIR", root / "source"),
        ]
        for item in self.patches:
            item.start()
        app.init_db()
        self.db = sqlite3.connect(self.db_path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")

    def tearDown(self):
        self.db.close()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def seed_cards(self, total_cents=4000, count=4, market=12.0):
        self.db.execute(
            """INSERT INTO batches
                 (id,batch_code,created_at,status,game,set_code,acquisition_type,total_cost,
                  economics_mode,economics_status,product_name,final_usd_paid_cents,units_acquired)
               VALUES (1,'HARDEN-1','2026-08-22','OPEN','One Piece','OP16','Singles',?,
                       'SINGLES_LUMP_SUM','FINALIZED','Hardening fixture',?,0)""",
            (total_cents / 100, total_cents),
        )
        rip_id = self.db.execute(
            """INSERT INTO rip_sessions
                 (rip_code,batch_id,status,units_opened,allocation_method,bulk_mode,
                  consumed_cost_cents,scanned_basis_cents,bulk_basis_cents,total_allocated_cents,
                  difference_cents,cards_accounted_confirmed,created_at,finalized_at)
               VALUES ('RIP-HARDEN',1,'FINALIZED',0,'EQUAL','NONE',?,?,0,?,0,1,
                       '2026-08-22','2026-08-22')""",
            (total_cents, total_cents, total_cents),
        ).lastrowid
        self.db.execute(
            """INSERT INTO rip_economic_events
                 (event_id,request_id,rip_session_id,event_type,effective_at,recorded_at,
                  reason_code,notes,payload)
               VALUES ('HARDEN-EVENT','HARDEN-REQUEST',?,'FINALIZATION','2026-08-22',
                       '2026-08-22','INITIAL','fixture','{}')""",
            (rip_id,),
        )
        allocations = allocate_cents(total_cents, range(1, count + 1))
        card_ids = []
        for sequence, allocation in enumerate(allocations, 1):
            card_id = self.db.execute(
                """INSERT INTO cards
                     (sku,batch_id,created_at,updated_at,name,status,rip_session_id,
                      market_average,market_updated_at)
                   VALUES (?,1,'2026-08-22','2026-08-22',?,'IN_STOCK',?,?,?)""",
                (f"HARDEN-{sequence}", f"Hardening Card {sequence}", rip_id, market,
                 "2026-08-22T12:00:00+00:00" if market is not None else None),
            ).lastrowid
            card_ids.append(card_id)
            self.db.execute(
                """INSERT INTO rip_basis_events
                     (event_id,rip_session_id,target_type,card_id,amount_delta_cents,created_at)
                   VALUES ('HARDEN-EVENT',?,'CARD',?,?,'2026-08-22')""",
                (rip_id, card_id, allocation.cents),
            )
        self.db.commit()
        return card_ids

    def sell(self, card_ids, *, merchandise=2000, shipping=149, fees=250, postage=500,
             presence=None):
        order_id = self.db.execute(
            """INSERT INTO sale_orders
                 (platform,order_number,sold_at,subtotal,shipping_collected,platform_fees,
                  postage_cost,order_type,merchandise_total_cents,shipping_collected_cents,
                  marketplace_fees_cents,actual_postage_cents)
               VALUES ('eBay',?,'2026-08-22',?,?,?,?,'CARD',?,?,?,?)""",
            (f"HARDEN-ORDER-{time.time_ns()}", merchandise / 100, shipping / 100,
             fees / 100, postage / 100, merchandise, shipping, fees, postage),
        ).lastrowid
        for card_id in card_ids:
            self.db.execute(
                "INSERT INTO sale_items (order_id,card_id,sale_price) VALUES (?,?,?)",
                (order_id, card_id, merchandise / 100 / len(card_ids)),
            )
            self.db.execute("UPDATE cards SET status='SOLD' WHERE id=?", (card_id,))
        capture_sale_input_evidence(
            self.db, order_id,
            presence if presence is not None else {
                "subtotal": str(merchandise / 100),
                "shipping_collected": str(shipping / 100),
                "platform_fees": str(fees / 100),
                "postage_cost": str(postage / 100),
            },
            order_type="CARD",
        )
        self.db.commit()
        return order_id


class JarvisIntegrationHardeningTests(IntegrationFixture):
    def test_zero_coverage_and_authoritative_zero_remain_distinguishable(self):
        self.db.execute(
            """INSERT INTO batches
                 (id,batch_code,created_at,status,game,set_code,acquisition_type)
               VALUES (1,'HARDEN-MISSING','2026-08-22','OPEN','One Piece','OP16','Singles')"""
        )
        for sequence in range(1, 5):
            self.db.execute(
                """INSERT INTO cards (sku,batch_id,created_at,updated_at,name,status)
                   VALUES (?,1,'2026-08-22','2026-08-22',?,'IN_STOCK')""",
                (f"HARDEN-MISSING-{sequence}", f"Missing Basis {sequence}"),
            )
        self.db.commit()
        missing = aggregate_economics_payload(self.db)["remaining_inventory"]
        self.assertEqual((missing["authoritative_basis_count"], missing["item_count"]), (0, 4))

        self.db.execute("DELETE FROM cards")
        self.db.execute("DELETE FROM batches")
        self.db.commit()
        self.seed_cards(total_cents=0, count=4)
        authoritative_zero = aggregate_economics_payload(self.db)["remaining_inventory"]
        self.assertEqual(
            (authoritative_zero["authoritative_basis_count"], authoritative_zero["item_count"],
             authoritative_zero["total_remaining_cost_basis_cents"]),
            (4, 4, 0),
        )

    def test_partial_sales_reconcile_to_original_basis_without_drift(self):
        cards = self.seed_cards()
        first = self.sell(cards[:1], merchandise=1200)
        self.assertEqual(sale_economics_payload(self.db, first)["cost_basis_of_goods_sold"]["value_cents"], 1000)
        self.assertEqual(aggregate_economics_payload(self.db)["remaining_inventory"]["total_remaining_cost_basis_cents"], 3000)
        second = self.sell(cards[1:3], merchandise=2400)
        cumulative = sum(sale_economics_payload(self.db, order)["cost_basis_of_goods_sold"]["value_cents"] for order in (first, second))
        self.assertEqual(cumulative, 3000)
        self.assertEqual(aggregate_economics_payload(self.db)["remaining_inventory"]["total_remaining_cost_basis_cents"], 1000)
        third = self.sell(cards[3:], merchandise=1200)
        cumulative += sale_economics_payload(self.db, third)["cost_basis_of_goods_sold"]["value_cents"]
        remaining = aggregate_economics_payload(self.db)["remaining_inventory"]
        self.assertEqual((cumulative, remaining["item_count"], remaining["total_remaining_cost_basis_cents"]), (4000, 0, 0))

    def test_exact_cent_allocations_are_stable_and_reconcile(self):
        cases = [(1000, 3, [334, 333, 333]), (701, 4, [176, 175, 175, 175]), (1, 4, [1, 0, 0, 0])]
        for cents, count, expected in cases:
            with self.subTest(cents=cents, count=count):
                first = [item.cents for item in allocate_cents(cents, range(1, count + 1))]
                second = [item.cents for item in allocate_cents(cents, range(1, count + 1))]
                self.assertEqual(first, expected)
                self.assertEqual(second, expected)
                self.assertEqual(sum(first), cents)

    def test_buyer_shipping_is_collected_revenue_not_shipping_expense(self):
        cards = self.seed_cards(count=1, total_cents=1000)
        order_id = self.sell(cards, merchandise=2000, shipping=149, fees=250, postage=500)
        report = sale_economics_payload(self.db, order_id)
        self.assertEqual(report["gross_sale_proceeds"]["value_cents"], 2149)
        self.assertEqual(report["net_proceeds"]["value_cents"], 1399)
        self.assertEqual(report["realized_profit_loss"]["value_cents"], 399)

    def test_each_missing_sale_input_blocks_complete_status_without_becoming_zero(self):
        cards = self.seed_cards(count=4, total_cents=4000)
        for card_id, missing in zip(cards, ("subtotal", "shipping_collected", "platform_fees", "postage_cost")):
            with self.subTest(missing=missing):
                evidence = {"subtotal": "20", "shipping_collected": "0", "platform_fees": "0", "postage_cost": "0"}
                evidence.pop(missing)
                order_id = self.sell([card_id], merchandise=2000, shipping=0, fees=0, postage=0, presence=evidence)
                report = sale_economics_payload(self.db, order_id)
                self.assertEqual(report["economics_status"], "PARTIAL")
                self.assertIsNone(report[{
                    "subtotal": "gross_merchandise_proceeds",
                    "shipping_collected": "shipping_charged_to_buyer",
                    "platform_fees": "marketplace_fees",
                    "postage_cost": "actual_shipping_cost",
                }[missing]]["value_cents"])

    def test_explicit_zero_sale_values_and_zero_market_are_known(self):
        cards = self.seed_cards(count=1, total_cents=0, market=0)
        order_id = self.sell(cards, merchandise=0, shipping=0, fees=0, postage=0)
        report = sale_economics_payload(self.db, order_id)
        self.assertEqual(report["economics_status"], "COMPLETE")
        self.assertEqual(report["net_proceeds"]["value_cents"], 0)
        self.assertEqual(report["realized_profit_loss"]["value_cents"], 0)
        self.assertIsNone(report["realized_roi"]["percent"])
        self.db.execute("UPDATE cards SET status='IN_STOCK'")
        self.db.commit()
        card = card_economics_payload(self.db, "HARDEN-1")
        self.assertEqual(card["current_market_reference_value"]["value_cents"], 0)
        self.assertEqual(card["allocated_acquisition_cost"]["value_cents"], 0)
        aggregate = aggregate_economics_payload(self.db)["remaining_inventory"]
        self.assertEqual(aggregate["total_remaining_cost_basis_cents"], 0)
        self.assertEqual(aggregate["total_current_inventory_value_cents"], 0)

    def test_unsupported_packaging_remains_explicitly_unresolved_not_zero(self):
        cards = self.seed_cards(count=1, total_cents=1000)
        order_id = self.sell(cards)
        fact = sale_economics_payload(self.db, order_id)["packaging_fulfillment_cost"]
        self.assertEqual((fact["value_cents"], fact["state"], fact["required_for_status"]), (None, "UNRESOLVED", False))

    def test_market_freshness_states_do_not_change_basis_or_completion(self):
        now = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
        expected = {
            "2026-08-20T12:00:00+00:00": "CURRENT",
            "2026-08-10T12:00:00+00:00": "AGING",
            "2026-06-01T12:00:00+00:00": "STALE",
            None: "UNKNOWN",
        }
        for observed, state in expected.items():
            self.assertEqual(valuation_freshness(observed, now=now)["state"], state)
        self.seed_cards(count=1, total_cents=1000)
        self.db.execute("UPDATE cards SET market_updated_at='2020-01-01T00:00:00+00:00'")
        self.db.commit()
        report = card_economics_payload(self.db, "HARDEN-1")
        self.assertEqual(report["economics_status"], "COMPLETE")
        self.assertEqual(report["current_market_reference_value"]["freshness"]["state"], "STALE")
        self.assertEqual(report["allocated_acquisition_cost"]["value_cents"], 1000)

    def test_sam_fields_and_market_values_cannot_cross_contaminate(self):
        self.seed_cards(count=1, total_cents=1000, market=12)
        before = card_economics_payload(self.db, "HARDEN-1")
        self.db.execute(
            """INSERT INTO sam_recognition_jobs
                 (job_uuid,request_id,recognition_key,card_id,batch_id,game,status,engine_version,
                  rules_version,scan_sha256,confidence,recognition_state,submitted_at,
                  family_confidence,printing_confidence)
               VALUES ('SAM-JOB-HARDEN','SAM-REQ-HARDEN','SAM-KEY-HARDEN',1,1,'One Piece',
                       'COMPLETED','frozen-engine','frozen-rules','',.997,'NEEDS_REVIEW',
                       '2026-08-22',.999,.998)"""
        )
        self.db.commit()
        after_identity = card_economics_payload(self.db, "HARDEN-1")
        self.assertEqual(before["allocated_acquisition_cost"], after_identity["allocated_acquisition_cost"])
        self.db.execute("UPDATE cards SET market_average=999.99 WHERE sku='HARDEN-1'")
        self.db.commit()
        confidence = self.db.execute(
            "SELECT family_confidence,printing_confidence FROM sam_recognition_jobs WHERE job_uuid='SAM-JOB-HARDEN'"
        ).fetchone()
        self.assertEqual(tuple(confidence), (.999, .998))


def candidate(printing_id, *, artwork="PRESENT", required=("ARTWORK_MATCH",), extra=(), quality=1.0):
    return {
        "family_id": 1, "commercial_printing_id": printing_id,
        "printing_uuid": f"PRINT-{printing_id}", "variant_label": f"Printing {printing_id}",
        "visual_score": .92, "reference_quality_score": quality, "quality_warnings": [],
        "reference_ids": [100 + printing_id], "evidence_requirements": {"required_markers": list(required)},
        "evidence_observations": [{
            "evidence_type": "ARTWORK_MATCH", "state": artwork, "confidence": .92,
            "source_kind": "SYSTEM_VISUAL", "reference_id": 100 + printing_id,
            "explanation": "Asset-level artwork observation.",
        }, *extra],
    }


class SamIntegrationHardeningTests(unittest.TestCase):
    def test_artwork_and_marker_support_different_printings_is_conflicting(self):
        marker = {"evidence_type": "SP_MARKER", "state": "PRESENT", "confidence": .95,
                  "source_kind": "SYSTEM_VISUAL", "explanation": "SP marker visible."}
        result = evaluate_printing_candidates([
            candidate(1), candidate(2, required=("ARTWORK_MATCH", "SP_MARKER"), extra=(marker,)),
        ], 1)
        self.assertEqual(result["certainty"], "CONFLICTING")
        self.assertFalse(result["authority_granted"])

    def test_confident_absence_excludes_a_while_b_survives(self):
        absent = {"evidence_type": "SP_MARKER", "state": "ABSENT_CONFIDENT", "confidence": .96,
                  "source_kind": "SYSTEM_VISUAL", "explanation": "Marker area is clear."}
        result = evaluate_printing_candidates([
            candidate(1, required=("ARTWORK_MATCH", "SP_MARKER"), extra=(absent,)), candidate(2),
        ], 1)
        excluded = {item["printing_id"]: item["excluded_by_negative_evidence"] for item in result["competing_printings"]}
        self.assertTrue(excluded[1])
        self.assertFalse(excluded[2])
        self.assertEqual(result["candidate"]["printing_id"], 2)
        self.assertFalse(result["authority_granted"])

    def test_cropped_marker_is_unresolved_and_not_excluded(self):
        unresolved = {"evidence_type": "WINNER_MARKER", "state": "UNRESOLVED", "confidence": None,
                      "source_kind": "SYSTEM_VISUAL", "explanation": "Marker region is cropped."}
        result = evaluate_printing_candidates([
            candidate(1, required=("ARTWORK_MATCH", "WINNER_MARKER"), extra=(unresolved,))
        ], 1)
        self.assertEqual(result["certainty"], "UNRESOLVED")
        self.assertFalse(result["competing_printings"][0]["excluded_by_negative_evidence"])

    def test_same_printing_asset_disagreement_stays_one_printing_and_surfaces_conflict(self):
        first = candidate(1)
        second = candidate(1, artwork="ABSENT_CONFIDENT")
        second["reference_ids"] = [202]
        second["evidence_observations"][0]["reference_id"] = 202
        second["evidence_observations"][0]["explanation"] = "Second readable asset disagrees."
        result = evaluate_printing_candidates([first, second], 1)
        self.assertEqual(len(result["competing_printings"]), 1)
        self.assertEqual(result["certainty"], "CONFLICTING")
        explanations = {item["explanation"] for item in result["competing_printings"][0]["marker_evidence"]}
        self.assertIn("Second readable asset disagrees.", explanations)

    def test_poor_asset_cannot_fabricate_authority(self):
        result = evaluate_printing_candidates([candidate(1, quality=.4)], 1)
        self.assertLess(result["competing_printings"][0]["confidence"], .5)
        self.assertFalse(result["authority_granted"])

    def test_printing_must_belong_to_asserted_family(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        base_schema(db)
        apply_migrations(db)
        db.execute("INSERT INTO batches (id,batch_code) VALUES (1,'SAM-HARDEN')")
        db.execute("INSERT INTO cards (id,sku,batch_id) VALUES (1,'SAM-HARDEN-1',1)")
        families = []
        for number in (1, 2):
            families.append(db.execute(
                """INSERT INTO sam_card_families
                     (family_uuid,game,family_key,card_number,normalized_set_code,canonical_name,
                      normalized_name,created_at,updated_at)
                   VALUES (?, 'One Piece', ?, ?, 'OP16', 'Card', 'CARD','2026-08-22','2026-08-22')""",
                (f"FAMILY-{number}", f"ONE PIECE:OP16-00{number}", f"OP16-00{number}"),
            ).lastrowid)
        printing = db.execute(
            """INSERT INTO sam_commercial_printings
                 (printing_uuid,family_id,printing_key,variant_label,evidence_requirements,created_at,updated_at)
               VALUES ('PRINT-ONE',?,'PRINT-ONE','Base','{}','2026-08-22','2026-08-22')""",
            (families[0],),
        ).lastrowid
        with self.assertRaisesRegex(ValueError, "belong"):
            record_assertion(
                db, card_id=1, field_scope="PRINTING", family_id=families[1], printing_id=printing,
                proposed_value="Base", certainty="OPERATOR_CONFIRMED", authority_granted=True,
                actor="OPERATOR",
            )
        self.assertEqual(db.execute("SELECT COUNT(*) FROM sam_identity_assertions").fetchone()[0], 0)
        db.close()

    def test_operator_conflict_is_the_effective_read_model_without_rewriting_suggestion(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        base_schema(db)
        apply_migrations(db)
        db.execute("INSERT INTO batches (id,batch_code) VALUES (1,'SAM-CONFLICT')")
        family_id = db.execute(
            """INSERT INTO sam_card_families
                 (family_uuid,game,family_key,card_number,normalized_set_code,canonical_name,
                  normalized_name,created_at,updated_at)
               VALUES ('FAMILY-CONFLICT','One Piece','ONE PIECE:OP16-033','OP16-033','OP16',
                       'Card','CARD','2026-08-22','2026-08-22')"""
        ).lastrowid
        printing_id = db.execute(
            """INSERT INTO sam_commercial_printings
                 (printing_uuid,family_id,printing_key,variant_label,evidence_requirements,created_at,updated_at)
               VALUES ('PRINT-CONFLICT',?,'PRINT-CONFLICT','Alternate Art','{}','2026-08-22','2026-08-22')""",
            (family_id,),
        ).lastrowid
        card_id = db.execute(
            """INSERT INTO cards
                 (id,sku,batch_id,sam_family_id,sam_family_certainty,sam_printing_certainty)
               VALUES (1,'SAM-CONFLICT-1',1,?,'OPERATOR_CONFIRMED','CONFLICTING')""",
            (family_id,),
        ).lastrowid
        evidence = json.dumps({"candidate": {"printing_id": printing_id}, "authority_granted": False})
        job_id = db.execute(
            """INSERT INTO sam_recognition_jobs
                 (job_uuid,request_id,recognition_key,card_id,batch_id,game,status,engine_version,
                  rules_version,confidence,recognition_state,submitted_at,family_id,family_confidence,
                  family_certainty,printing_id,printing_confidence,printing_certainty,
                  printing_unresolved_reason,printing_evidence)
               VALUES ('SAM-JOB-CONFLICT','SAM-REQ-CONFLICT','SAM-KEY-CONFLICT',?,1,'One Piece',
                       'COMPLETED','frozen-engine','frozen-rules',.99,'NEEDS_REVIEW','2026-08-22',
                       ?,.99,'HIGH_CONFIDENCE_SUGGESTION',?,.95,'HIGH_CONFIDENCE_SUGGESTION','',?)""",
            (card_id, family_id, printing_id, evidence),
        ).lastrowid
        record_assertion(
            db, card_id=card_id, job_id=job_id, field_scope="PRINTING", family_id=family_id,
            proposed_value="", certainty="CONFLICTING", authority_granted=False, actor="OPERATOR",
            reason_code="OPERATOR_MARKED_PRINTING_CONFLICT",
        )
        payload = identity_payload(db, job_id, [{
            "family_id": family_id, "commercial_printing_id": printing_id,
            "card_number": "OP16-033", "card_name": "Card", "set_code": "OP16",
        }])
        self.assertEqual(payload["printing"]["certainty"], "CONFLICTING")
        self.assertEqual(payload["printing"]["unresolved_reason"], "OPERATOR_MARKED_PRINTING_CONFLICT")
        self.assertFalse(payload["printing"]["authoritative"])
        frozen_job = db.execute(
            "SELECT printing_certainty,printing_confidence FROM sam_recognition_jobs WHERE id=?", (job_id,)
        ).fetchone()
        self.assertEqual(tuple(frozen_job), ("HIGH_CONFIDENCE_SUGGESTION", .95))
        db.close()

    def test_legacy_variant_and_rarity_disagreement_is_visible_without_overwrite(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        base_schema(db)
        db.execute("ALTER TABLE cards ADD COLUMN variant TEXT NOT NULL DEFAULT 'Standard'")
        db.execute("ALTER TABLE cards ADD COLUMN rarity TEXT NOT NULL DEFAULT ''")
        apply_migrations(db)
        db.execute("INSERT INTO batches (id,batch_code) VALUES (1,'SAM-LEGACY')")
        family_id = db.execute(
            """INSERT INTO sam_card_families
                 (family_uuid,game,family_key,card_number,normalized_set_code,canonical_name,
                  normalized_name,created_at,updated_at)
               VALUES ('FAMILY-LEGACY','One Piece','ONE PIECE:OP16-055','OP16-055','OP16',
                       'Card','CARD','2026-08-22','2026-08-22')"""
        ).lastrowid
        printing_id = db.execute(
            """INSERT INTO sam_commercial_printings
                 (printing_uuid,family_id,printing_key,variant_label,rarity_treatment,
                  evidence_requirements,created_at,updated_at)
               VALUES ('PRINT-LEGACY',?,'PRINT-LEGACY','Alternate Art','SP','{}',
                       '2026-08-22','2026-08-22')""",
            (family_id,),
        ).lastrowid
        card_id = db.execute(
            """INSERT INTO cards (id,sku,batch_id,variant,rarity)
               VALUES (1,'SAM-LEGACY-1',1,'Standard','R')"""
        ).lastrowid
        job_id = db.execute(
            """INSERT INTO sam_recognition_jobs
                 (job_uuid,request_id,recognition_key,card_id,batch_id,game,status,engine_version,
                  rules_version,confidence,recognition_state,submitted_at,family_id,family_confidence,
                  family_certainty,printing_id,printing_confidence,printing_certainty,printing_evidence)
               VALUES ('SAM-JOB-LEGACY','SAM-REQ-LEGACY','SAM-KEY-LEGACY',?,1,'One Piece',
                       'COMPLETED','frozen-engine','frozen-rules',.99,'NEEDS_REVIEW','2026-08-22',
                       ?,.99,'HIGH_CONFIDENCE_SUGGESTION',?,.95,'HIGH_CONFIDENCE_SUGGESTION','{}')""",
            (card_id, family_id, printing_id),
        ).lastrowid
        payload = identity_payload(db, job_id, [{
            "family_id": family_id, "commercial_printing_id": printing_id,
            "card_number": "OP16-055", "card_name": "Card", "set_code": "OP16",
        }])
        conflicts = {item["field"]: item for item in payload["inventory"]["legacy_conflicts"]}
        self.assertEqual(conflicts["variant"]["state"], "CONFLICTING")
        self.assertEqual(conflicts["rarity"]["proposed_value"], "SP")
        card = db.execute("SELECT variant,rarity,sam_printing_id FROM cards WHERE id=?", (card_id,)).fetchone()
        self.assertEqual(tuple(card), ("Standard", "R", None))
        db.close()


class MigrationAndApiHardeningTests(IntegrationFixture):
    def test_upgrade_from_0017_to_0018_and_fresh_start_are_empty_and_integral(self):
        legacy = sqlite3.connect(":memory:")
        legacy.row_factory = sqlite3.Row
        base_schema(legacy)
        apply_migrations(legacy, DEFAULT_MIGRATIONS[:-2])
        self.assertEqual(legacy.execute("SELECT migration_id FROM schema_migrations ORDER BY migration_id DESC LIMIT 1").fetchone()[0], "0017_v24_sam_phase1_family_printing")
        apply_migrations(legacy, [DEFAULT_MIGRATIONS[-2]])
        self.assertEqual(legacy.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        for table in ("cards", "batches", "sale_orders", "jarvis_sale_input_evidence", "sam_printing_evidence_observations"):
            self.assertEqual(legacy.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
        legacy.close()

    def test_jarvis_api_unknown_and_malformed_identifiers_fail_as_json_404(self):
        server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.DexHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urllib.request.urlopen(base + "/api/jarvis/economics/summary", timeout=5) as response:
                summary = json.load(response)
                self.assertEqual((response.status, summary["economics_status"]), (200, "UNRESOLVED"))
                self.assertIsNone(summary["remaining_inventory"]["total_remaining_cost_basis_cents"])
                self.assertIsNone(summary["remaining_inventory"]["total_current_inventory_value_cents"])
                self.assertIsNone(summary["realized"]["total_realized_profit_loss_cents"])
            for path in (
                "/api/jarvis/economics/cards/NO-SUCH-SKU",
                "/api/jarvis/economics/cards/lower-case-is-malformed",
                "/api/jarvis/economics/sales/999999",
                "/api/jarvis/economics/sales/not-a-number",
            ):
                with self.subTest(path=path), self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(base + path, timeout=5)
                self.assertEqual(caught.exception.code, 404)
                payload = json.loads(caught.exception.read())
                self.assertIn("error", payload)
                self.assertNotIn("Traceback", payload["error"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
