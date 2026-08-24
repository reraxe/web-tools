import json
import sqlite3
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import app
from dex_jarvis_economics import (
    aggregate_economics_payload,
    capture_sale_input_evidence,
    card_economics_payload,
    sale_economics_payload,
)
from dex_migrations import DEFAULT_MIGRATIONS, MigrationError, apply_migrations
from dex_sam_identity import evaluate_printing_candidates, record_assertion
from tests.test_phase5_sealed import base_schema


def printing_candidate(
    printing_id, *, score=.90, required=("ARTWORK_MATCH",), artwork="PRESENT",
    extra=(), quality=1.0, warnings=(), shadow=False, incompatible=(),
):
    observations = [{
        "evidence_type": "ARTWORK_MATCH", "state": artwork,
        "confidence": score, "source_kind": "SYSTEM_VISUAL",
        "explanation": "Whole-card artwork comparison.",
    }]
    observations.extend(extra)
    return {
        "family_id": 10, "commercial_printing_id": printing_id,
        "printing_uuid": f"PRINT-{printing_id}", "variant_label": f"Variant {printing_id}",
        "artwork_identity": f"Artwork {printing_id}", "visual_score": score,
        "evidence_requirements": {"required_markers": list(required),
                                  "incompatible_markers": list(incompatible)},
        "reference_ids": [1000 + printing_id], "reference_quality_score": quality,
        "quality_warnings": list(warnings), "evidence_observations": observations,
        "challenger_shadow": shadow,
    }


class JarvisSimplifiedEconomicsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.db_path = root / "jarvis.db"
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

    def seed_cards(self, *, count=1, total=1000, finalized=True, market=None, batch_id=None):
        batch_id = batch_id or int(self.db.execute("SELECT COALESCE(MAX(id),0)+1 FROM batches").fetchone()[0])
        mode = "SINGLES_LUMP_SUM"
        economics_status = "FINALIZED" if finalized else "DRAFT"
        final_cost = total if finalized else None
        self.db.execute(
            """INSERT INTO batches
               (id,batch_code,created_at,status,game,set_code,acquisition_type,total_cost,
                economics_mode,economics_status,product_name,final_usd_paid_cents,units_acquired)
               VALUES (?,?,'2026-08-22','OPEN','One Piece','OP16','Singles',?, ?,?,
                       'JARVIS fixture',?,0)""",
            (batch_id, f"JARVIS-{batch_id:03d}", total / 100 if total is not None else 0,
             mode, economics_status, final_cost),
        )
        rip_id = None
        if finalized:
            rip_id = self.db.execute(
                """INSERT INTO rip_sessions
                   (rip_code,batch_id,status,units_opened,allocation_method,bulk_mode,
                    consumed_cost_cents,scanned_basis_cents,bulk_basis_cents,total_allocated_cents,
                    difference_cents,cards_accounted_confirmed,created_at,finalized_at)
                   VALUES (?,?,'FINALIZED',0,'EQUAL','NONE',?,?,0,?,0,1,'2026-08-22','2026-08-22')""",
                (f"RIP-J-{batch_id}", batch_id, total, total, total),
            ).lastrowid
            self.db.execute(
                """INSERT INTO rip_economic_events
                   (event_id,request_id,rip_session_id,event_type,effective_at,recorded_at,
                    reason_code,notes,payload)
                   VALUES (?,?,?,'FINALIZATION','2026-08-22','2026-08-22','INITIAL','fixture','{}')""",
                (f"J-EVENT-{batch_id}", f"J-EVENT-REQ-{batch_id}", rip_id),
            )
        card_ids = []
        base, remainder = divmod(total or 0, count)
        for sequence in range(1, count + 1):
            card_id = self.db.execute(
                """INSERT INTO cards
                   (sku,batch_id,created_at,updated_at,name,status,rip_session_id,
                    market_average,market_updated_at)
                   VALUES (?,?,'2026-08-22','2026-08-22',?,'IN_STOCK',?,?,?)""",
                (f"JARVIS-{batch_id:03d}-{sequence:03d}", batch_id, f"Card {sequence}",
                 rip_id, market, "2026-08-22T12:00:00+00:00" if market is not None else None),
            ).lastrowid
            card_ids.append(card_id)
            if finalized:
                self.db.execute(
                    """INSERT INTO rip_basis_events
                       (event_id,rip_session_id,target_type,card_id,amount_delta_cents,created_at)
                       VALUES (?,?,'CARD',?,?,'2026-08-22')""",
                    (f"J-EVENT-{batch_id}", rip_id, card_id,
                     base + (1 if sequence <= remainder else 0)),
                )
        self.db.commit()
        return card_ids

    def sale(self, card_ids, *, merchandise=2000, shipping=200, fees=300, postage=400,
             presence=None):
        order_id = self.db.execute(
            """INSERT INTO sale_orders
               (platform,order_number,sold_at,subtotal,shipping_collected,platform_fees,
                postage_cost,order_type,merchandise_total_cents,shipping_collected_cents,
                marketplace_fees_cents,actual_postage_cents)
               VALUES ('eBay',?,'2026-08-22',?,?,?,?,'CARD',?,?,?,?)""",
            (f"ORDER-{uuid.uuid4().hex[:8]}", merchandise / 100, shipping / 100,
             fees / 100, postage / 100, merchandise, shipping, fees, postage),
        ).lastrowid
        for card_id in card_ids:
            self.db.execute(
                "INSERT INTO sale_items (order_id,card_id,sale_price) VALUES (?,?,?)",
                (order_id, card_id, merchandise / 100 / len(card_ids)),
            )
            self.db.execute("UPDATE cards SET status='SOLD' WHERE id=?", (card_id,))
        if presence is not None:
            capture_sale_input_evidence(self.db, order_id, presence, order_type="CARD")
        self.db.commit()
        return order_id

    def test_known_cost_unsold_and_market_value_are_derived_with_provenance(self):
        self.seed_cards(total=1000, market=15.25)
        report = card_economics_payload(self.db, "JARVIS-001-001")
        self.assertEqual(report["economics_status"], "COMPLETE")
        self.assertEqual(report["allocated_acquisition_cost"]["value_cents"], 1000)
        self.assertEqual(report["current_market_reference_value"]["value_cents"], 1525)
        self.assertEqual(report["unrealized_gain_loss"]["value_cents"], 525)
        self.assertEqual(report["unrealized_roi"]["percent"], 52.5)
        self.assertEqual(report["current_market_reference_value"]["freshness"]["state"], "CURRENT")
        self.assertIn("rip_basis_events", report["allocated_acquisition_cost"]["source_field"])

    def test_missing_cost_and_missing_market_never_become_zero(self):
        self.seed_cards(total=1000, finalized=False)
        report = card_economics_payload(self.db, "JARVIS-001-001")
        self.assertEqual(report["economics_status"], "UNRESOLVED")
        self.assertIsNone(report["allocated_acquisition_cost"]["value_cents"])
        self.assertIsNone(report["current_market_reference_value"]["value_cents"])
        self.assertIsNone(report["unrealized_gain_loss"]["value_cents"])

    def test_market_value_without_timestamp_says_freshness_unknown(self):
        self.seed_cards(total=1000, market=10.00)
        self.db.execute("UPDATE cards SET market_updated_at=NULL WHERE sku='JARVIS-001-001'")
        self.db.commit()
        report = card_economics_payload(self.db, "JARVIS-001-001")
        self.assertEqual(report["current_market_reference_value"]["value_cents"], 1000)
        self.assertEqual(report["current_market_reference_value"]["freshness"]["label"], "Freshness Unknown")

    def test_explicit_zero_cost_is_known_but_roi_is_unresolved(self):
        self.seed_cards(total=0, market=10.00)
        report = card_economics_payload(self.db, "JARVIS-001-001")
        self.assertEqual(report["allocated_acquisition_cost"]["value_cents"], 0)
        self.assertEqual(report["unrealized_gain_loss"]["value_cents"], 1000)
        self.assertIsNone(report["unrealized_roi"]["percent"])
        self.assertEqual(report["unrealized_roi"]["reason"], "ZERO_COST_BASIS")

    def test_legacy_estimate_is_labeled_and_reconciles_deterministic_cents(self):
        self.db.execute(
            """INSERT INTO batches
               (id,batch_code,created_at,status,game,set_code,acquisition_type,total_cost,
                economics_mode,economics_status,product_name,units_acquired)
               VALUES (1,'LEGACY-J','2026-08-22','OPEN','One Piece','OP16','Singles',10,
                       'LEGACY','ESTIMATED','Legacy lot',0)"""
        )
        for sequence in range(1, 4):
            self.db.execute(
                """INSERT INTO cards
                   (id,sku,batch_id,created_at,updated_at,name,status)
                   VALUES (?,?,1,'2026-08-22','2026-08-22','Legacy','IN_STOCK')""",
                (sequence, f"LEGACY-{sequence}"),
            )
        self.db.commit()
        values = [card_economics_payload(self.db, f"LEGACY-{i}")["allocated_acquisition_cost"] for i in range(1, 4)]
        self.assertEqual([item["value_cents"] for item in values], [334, 333, 333])
        self.assertTrue(all(item["state"] == "ESTIMATED" for item in values))

    def test_complete_sale_uses_recorded_inputs_and_exact_multi_item_basis(self):
        cards = self.seed_cards(count=2, total=1000)
        order_id = self.sale(cards, presence={
            "subtotal": "20.00", "shipping_collected": "2.00",
            "platform_fees": "3.00", "postage_cost": "4.00",
        })
        report = sale_economics_payload(self.db, order_id)
        self.assertEqual(report["economics_status"], "COMPLETE")
        self.assertEqual(report["order"]["quantity_sold"], 2)
        self.assertEqual(report["gross_sale_proceeds"]["value_cents"], 2200)
        self.assertEqual(report["net_proceeds"]["value_cents"], 1500)
        self.assertEqual(report["cost_basis_of_goods_sold"]["value_cents"], 1000)
        self.assertEqual(report["realized_profit_loss"]["value_cents"], 500)
        self.assertEqual(report["realized_roi"]["percent"], 50)

    def test_missing_fee_or_postage_blocks_net_profit_and_roi(self):
        cards = self.seed_cards(count=2, total=1000)
        order_id = self.sale(cards[:1], merchandise=1000, shipping=0, fees=0, postage=0,
                             presence={"subtotal": "10.00", "shipping_collected": "0.00"})
        report = sale_economics_payload(self.db, order_id)
        self.assertEqual(report["economics_status"], "PARTIAL")
        self.assertIsNone(report["marketplace_fees"]["value_cents"])
        self.assertIsNone(report["actual_shipping_cost"]["value_cents"])
        self.assertIsNone(report["net_proceeds"]["value_cents"])
        self.assertIsNone(report["realized_profit_loss"]["value_cents"])
        self.assertIn("MARKETPLACE_FEES_UNKNOWN", report["warnings"])

    def test_partial_quantity_sale_keeps_remaining_basis_and_value_separate(self):
        cards = self.seed_cards(count=3, total=1000, market=5.00)
        order_id = self.sale(cards[:1], merchandise=800, shipping=0, fees=0, postage=0,
                             presence={"subtotal": "8", "shipping_collected": "0",
                                       "platform_fees": "0", "postage_cost": "0"})
        sold = sale_economics_payload(self.db, order_id)
        remaining = aggregate_economics_payload(self.db)
        self.assertEqual(sold["cost_basis_of_goods_sold"]["value_cents"], 334)
        self.assertEqual(remaining["remaining_inventory"]["item_count"], 2)
        self.assertEqual(remaining["remaining_inventory"]["total_remaining_cost_basis_cents"], 666)
        self.assertEqual(remaining["remaining_inventory"]["total_current_inventory_value_cents"], 1000)

    def test_unresolved_and_estimated_items_are_excluded_from_precise_aggregates(self):
        self.seed_cards(total=500, market=8.00, batch_id=1)
        self.seed_cards(total=900, finalized=False, market=9.00, batch_id=2)
        report = aggregate_economics_payload(self.db)
        self.assertEqual(report["remaining_inventory"]["item_count"], 2)
        self.assertEqual(report["remaining_inventory"]["total_remaining_cost_basis_cents"], 500)
        self.assertEqual(report["remaining_inventory"]["paired_authoritative_count"], 1)
        self.assertIn("exclude unresolved", " ".join(report["warnings"]).lower())

    def test_market_change_never_changes_acquisition_or_allocated_basis(self):
        self.seed_cards(total=777, market=10.00)
        before = card_economics_payload(self.db, "JARVIS-001-001")
        self.db.execute("UPDATE cards SET market_average=99.99 WHERE sku='JARVIS-001-001'")
        self.db.commit()
        after = card_economics_payload(self.db, "JARVIS-001-001")
        self.assertEqual(before["acquisition_cost"], after["acquisition_cost"])
        self.assertEqual(before["allocated_acquisition_cost"], after["allocated_acquisition_cost"])
        self.assertNotEqual(before["current_market_reference_value"], after["current_market_reference_value"])

    def test_large_aggregate_is_fast_and_does_not_store_totals(self):
        self.seed_cards(count=1200, total=120000, market=1.50)
        started = time.perf_counter()
        report = aggregate_economics_payload(self.db)
        elapsed = time.perf_counter() - started
        self.assertEqual(report["remaining_inventory"]["paired_authoritative_count"], 1200)
        self.assertLess(elapsed, 2.0)
        tables = {row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn("jarvis_calculated_totals", tables)
        print(f"JARVIS simplified economics performance: 1,200 cards in {elapsed * 1000:.2f} ms")


class SamPhase2AdversarialTests(unittest.TestCase):
    def identity_db(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        base_schema(db)
        apply_migrations(db)
        db.execute("INSERT INTO batches (id,batch_code) VALUES (1,'SAM-AUTH')")
        db.execute("INSERT INTO cards (id,sku,batch_id) VALUES (1,'SAM-AUTH-1',1)")
        family_id = db.execute(
            """INSERT INTO sam_card_families
               (family_uuid,game,family_key,card_number,normalized_set_code,canonical_name,
                normalized_name,created_at,updated_at)
               VALUES ('FAMILY-AUTH','One Piece','ONE PIECE:OP16-034','OP16-034','OP16',
                       'Luffy','LUFFY','2026-08-22','2026-08-22')"""
        ).lastrowid
        printing_ids = []
        for sequence in (1, 2):
            printing_ids.append(db.execute(
                """INSERT INTO sam_commercial_printings
                   (printing_uuid,family_id,printing_key,variant_label,artwork_identity,language,
                    evidence_requirements,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,'{}','2026-08-22','2026-08-22')""",
                (f"PRINT-AUTH-{sequence}", family_id, f"PRINTING-{sequence}", f"Variant {sequence}",
                 f"Artwork {sequence}", "English"),
            ).lastrowid)
        return db, family_id, printing_ids

    def test_single_printing_clear_artwork_is_suggestion_only(self):
        result = evaluate_printing_candidates([printing_candidate(1)], 10)
        self.assertEqual(result["certainty"], "HIGH_CONFIDENCE_SUGGESTION")
        self.assertFalse(result["authority_granted"])

    def test_multiple_printings_unresolved_without_positive_proof(self):
        candidates = [
            printing_candidate(1, artwork="UNRESOLVED"),
            printing_candidate(2, artwork="UNRESOLVED"),
            printing_candidate(3, artwork="UNRESOLVED"),
        ]
        result = evaluate_printing_candidates(candidates, 10)
        self.assertEqual(result["certainty"], "UNRESOLVED")
        self.assertEqual(result["unresolved_reason"], "SAME_FAMILY_PRINTING_COLLISION")

    def test_unique_marker_presence_can_suggest_special_printing(self):
        marker = {"evidence_type": "SP_MARKER", "state": "PRESENT", "confidence": .98,
                  "source_kind": "SYSTEM_VISUAL", "explanation": "SP marker visible."}
        result = evaluate_printing_candidates([
            printing_candidate(1, required=("ARTWORK_MATCH",), incompatible=("SP_MARKER",)),
            printing_candidate(2, required=("ARTWORK_MATCH", "SP_MARKER"), extra=(marker,)),
        ], 10, {"SP_MARKER": "PRESENT"})
        self.assertEqual(result["certainty"], "HIGH_CONFIDENCE_SUGGESTION")
        self.assertEqual(result["candidate"]["printing_id"], 2)
        self.assertFalse(result["authority_granted"])

    def test_missing_required_marker_excludes_special_printing(self):
        absent = {"evidence_type": "SP_MARKER", "state": "ABSENT_CONFIDENT", "confidence": .96,
                  "source_kind": "SYSTEM_VISUAL", "explanation": "Marker confidently absent."}
        result = evaluate_printing_candidates([
            printing_candidate(1, required=("ARTWORK_MATCH", "SP_MARKER"), extra=(absent,)),
        ], 10)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["unresolved_reason"], "REQUIRED_PRINTING_MARKER_ABSENT")

    def test_unresolved_marker_neither_confirms_nor_excludes(self):
        unresolved = {"evidence_type": "WINNER_STAMP", "state": "UNRESOLVED", "confidence": None,
                      "source_kind": "SYSTEM_OCR", "explanation": "Glare covers stamp region."}
        result = evaluate_printing_candidates([
            printing_candidate(1, required=("ARTWORK_MATCH", "WINNER_STAMP"), extra=(unresolved,)),
        ], 10)
        self.assertEqual(result["certainty"], "UNRESOLVED")
        self.assertIsNotNone(result["candidate"])

    def test_two_competing_present_printings_are_conflicting(self):
        result = evaluate_printing_candidates([printing_candidate(1), printing_candidate(2)], 10)
        self.assertEqual(result["certainty"], "CONFLICTING")
        self.assertEqual(result["unresolved_reason"], "CONFLICTING_POSITIVE_PRINTING_EVIDENCE")

    def test_contradictory_evidence_blocks_suggestion(self):
        contradiction = {"evidence_type": "ARTWORK_MATCH", "state": "ABSENT_CONFIDENT", "confidence": .99,
                         "source_kind": "SYSTEM_VISUAL", "explanation": "Second region disagrees."}
        result = evaluate_printing_candidates([
            printing_candidate(1, extra=(contradiction,)),
        ], 10)
        self.assertEqual(result["certainty"], "CONFLICTING")
        self.assertIsNone(result["candidate"])

    def test_artwork_match_does_not_prove_treatment(self):
        result = evaluate_printing_candidates([
            printing_candidate(1, required=("ARTWORK_MATCH", "FOIL_TREATMENT")),
        ], 10)
        self.assertEqual(result["certainty"], "UNRESOLVED")
        self.assertFalse(result["competing_printings"][0]["positive_evidence_complete"])

    def test_treatment_presence_cannot_override_artwork_conflict(self):
        treatment = {"evidence_type": "FOIL_TREATMENT", "state": "PRESENT", "confidence": .98,
                     "source_kind": "SYSTEM_VISUAL", "explanation": "Foil treatment agrees."}
        result = evaluate_printing_candidates([
            printing_candidate(1, score=.12, artwork="ABSENT_CONFIDENT",
                               required=("ARTWORK_MATCH", "FOIL_TREATMENT"), extra=(treatment,)),
        ], 10)
        self.assertIsNone(result["candidate"])
        self.assertFalse(result["authority_granted"])

    def test_poor_reference_quality_reduces_confidence_but_not_authority_boundary(self):
        result = evaluate_printing_candidates([
            printing_candidate(1, score=.99, quality=.60, warnings=("LOW_RESOLUTION_REFERENCE",)),
        ], 10)
        self.assertLess(result["confidence"], .60)
        self.assertFalse(result["authority_granted"])

    def test_challenger_alternate_is_shadow_evidence_only(self):
        result = evaluate_printing_candidates([
            printing_candidate(1, artwork="UNRESOLVED"),
            printing_candidate(2, shadow=True),
        ], 10)
        self.assertTrue(any(item["challenger_shadow"] for item in result["competing_printings"]))
        self.assertFalse(result["authority_granted"])

    def test_ninety_nine_percent_system_confidence_never_grants_printing_authority(self):
        result = evaluate_printing_candidates([printing_candidate(1, score=.999)], 10)
        self.assertGreater(result["confidence"], .99)
        self.assertFalse(result["authority_granted"])

    def test_no_family_has_no_printing_candidate(self):
        result = evaluate_printing_candidates([printing_candidate(1)], None)
        self.assertEqual(result["certainty"], "UNRESOLVED")
        self.assertEqual(result["competing_printings"], [])

    def test_negative_artwork_evidence_can_leave_no_viable_printing(self):
        result = evaluate_printing_candidates([
            printing_candidate(1, artwork="ABSENT_CONFIDENT", score=.10),
            printing_candidate(2, artwork="ABSENT_CONFIDENT", score=.15),
        ], 10)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["unresolved_reason"], "REQUIRED_PRINTING_MARKER_ABSENT")

    def test_mixed_present_and_unresolved_printings_remain_non_authoritative(self):
        result = evaluate_printing_candidates([
            printing_candidate(1), printing_candidate(2, artwork="UNRESOLVED"),
        ], 10)
        self.assertEqual(result["certainty"], "HIGH_CONFIDENCE_SUGGESTION")
        self.assertFalse(result["authority_granted"])

    def test_invalid_marker_state_fails_closed(self):
        with self.assertRaises(ValueError):
            evaluate_printing_candidates([
                printing_candidate(1, artwork="MAYBE"),
            ], 10)

    def test_system_assertion_cannot_grant_printing_authority(self):
        db, _, _ = self.identity_db()
        with self.assertRaises(ValueError):
            record_assertion(
                db, card_id=1, field_scope="PRINTING", printing_id=None,
                certainty="AUTHORITATIVE", confidence=.999, authority_granted=True,
                actor="SYSTEM", reason_code="SYSTEM_ATTEMPT",
            )
        db.close()

    def test_operator_printing_confirmation_succeeds(self):
        db, family_id, printing_ids = self.identity_db()
        assertion_id = record_assertion(
            db, card_id=1, field_scope="PRINTING", family_id=family_id,
            printing_id=printing_ids[0], proposed_value="Variant 1",
            certainty="OPERATOR_CONFIRMED", confidence=.91, authority_granted=True,
            actor="OPERATOR", reason_code="OPERATOR_PRINTING_CONFIRMED",
        )
        row = db.execute("SELECT * FROM sam_identity_assertions WHERE id=?", (assertion_id,)).fetchone()
        self.assertEqual((row["actor"], row["authority_granted"]), ("OPERATOR", 1))
        db.close()

    def test_operator_correction_preserves_append_only_printing_history(self):
        db, family_id, printing_ids = self.identity_db()
        first = record_assertion(
            db, card_id=1, field_scope="PRINTING", family_id=family_id,
            printing_id=printing_ids[0], proposed_value="Variant 1",
            certainty="OPERATOR_CONFIRMED", authority_granted=True,
            actor="OPERATOR", reason_code="OPERATOR_PRINTING_CONFIRMED",
        )
        second = record_assertion(
            db, card_id=1, field_scope="PRINTING", family_id=family_id,
            printing_id=printing_ids[1], proposed_value="Variant 2",
            certainty="OPERATOR_CONFIRMED", authority_granted=True,
            actor="OPERATOR", reason_code="OPERATOR_PRINTING_CORRECTED",
            supersedes_assertion_id=first,
        )
        rows = db.execute(
            "SELECT id,printing_id,supersedes_assertion_id FROM sam_identity_assertions ORDER BY id"
        ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[-1]["supersedes_assertion_id"], first)
        self.assertNotEqual(rows[0]["printing_id"], rows[1]["printing_id"])
        self.assertGreater(second, first)
        db.close()

    def test_family_can_be_authoritative_while_printing_remains_unresolved(self):
        db, family_id, _ = self.identity_db()
        record_assertion(
            db, card_id=1, field_scope="FAMILY", family_id=family_id,
            proposed_value="OP16-034", certainty="AUTHORITATIVE",
            confidence=.96, authority_granted=True, actor="SYSTEM",
            reason_code="FAMILY_IDENTITY_APPLIED",
        )
        family = db.execute(
            "SELECT authority_granted FROM sam_identity_assertions WHERE field_scope='FAMILY'"
        ).fetchone()
        printing = db.execute(
            "SELECT 1 FROM sam_identity_assertions WHERE field_scope='PRINTING' AND authority_granted=1"
        ).fetchone()
        self.assertEqual(family["authority_granted"], 1)
        self.assertIsNone(printing)
        db.close()


class V24MigrationBoundaryTests(unittest.TestCase):
    def test_0018_is_additive_no_backfill_and_transactional(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        base_schema(db)
        apply_migrations(db, DEFAULT_MIGRATIONS[:-1])
        db.execute("INSERT INTO batches (id,batch_code) VALUES (1,'LEGACY-0018')")
        db.execute("INSERT INTO cards (id,sku,batch_id) VALUES (1,'LEGACY-0018-CARD',1)")
        db.execute("INSERT INTO sale_orders (id,platform,sold_at) VALUES (1,'eBay','2026-08-22')")
        before = tuple(db.execute("SELECT id,platform,sold_at FROM sale_orders").fetchone())
        self.assertEqual(apply_migrations(db, DEFAULT_MIGRATIONS[-1:]),
                         ("0018_v24_jarvis_economics_sam_phase2",))
        self.assertEqual(tuple(db.execute("SELECT id,platform,sold_at FROM sale_orders").fetchone()), before)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM jarvis_sale_input_evidence").fetchone()[0], 0)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM sam_printing_evidence_observations").fetchone()[0], 0)
        self.assertEqual(apply_migrations(db), ())
        self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        db.close()

    def test_0018_failure_does_not_mark_migration_complete(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        base_schema(db)
        apply_migrations(db, DEFAULT_MIGRATIONS[:-1])
        db.execute("CREATE TABLE jarvis_sale_input_evidence (id INTEGER)")
        db.commit()
        with self.assertRaises(MigrationError):
            apply_migrations(db, DEFAULT_MIGRATIONS[-1:])
        self.assertIsNone(db.execute(
            "SELECT 1 FROM schema_migrations WHERE migration_id='0018_v24_jarvis_economics_sam_phase2'"
        ).fetchone())
        self.assertIsNone(db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sam_printing_evidence_observations'"
        ).fetchone())
        db.close()

    def test_printing_observations_are_append_only(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        base_schema(db)
        apply_migrations(db)
        # The schema triggers themselves are the durable safety boundary.
        triggers = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        )}
        self.assertIn("sam_printing_observations_no_update", triggers)
        self.assertIn("sam_printing_observations_no_delete", triggers)
        db.close()


if __name__ == "__main__":
    unittest.main()
