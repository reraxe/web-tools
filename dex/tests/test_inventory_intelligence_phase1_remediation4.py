import copy
from pathlib import Path

from dex_documents import tombstone_document
from dex_inbound import acquisition_payload, autosave_acquisition, confirm_acquisition
from dex_receipt_semantics import (
    current_semantic_lines,
    decide_semantic_line,
    semantic_allows_receipt_line,
)
from dex_receipts import LocalPdfTextReceiptExtractor, queue_extraction
from tests.test_v22_phase5_receipts import ReceiptFixture, receipt_pdf


FIXTURES = Path(__file__).parent / "fixtures"
FANTASY_BAY = (FIXTURES / "fantasy_bay_synthetic.txt").read_text(encoding="utf-8")


class VersionedFantasyBayExtractor:
    """Reproduce the two live parser generations without changing source bytes."""

    provider_name = "TEST_VERSIONED_FANTASY_BAY"

    def __init__(self, *, legacy: bool):
        self.legacy = legacy
        self.provider_version = "receipt-structured-math-v1" if legacy else "receipt-structured-math-v1-remediation2"
        self.base = LocalPdfTextReceiptExtractor()

    def extract(self, document, data):
        result = copy.deepcopy(self.base.extract(document, data))
        if not self.legacy:
            return result

        for fact in result["candidates"]:
            if fact["field_name"] == "merchant_name":
                fact["normalized_value"] = "| } 7A/V\\TASY BAV ~~"
                fact["confidence"] = 0.91
                fact["confidence_band"] = "HIGH"
                fact["source_location"] = "line 1"
        corrupt_source_index = None
        for semantic in result["semantic_lines"]:
            semantic["parser_version"] = "receipt-structured-math-v1"
            semantic["rules_version"] = "receipt-semantic-rules-v1"
            semantic["engine_version"] = "dex-receipt-semantic-v1"
            if semantic["normalized_text"] == "UEZ (3.3125%5)} $0.53":
                corrupt_source_index = semantic["source_line_index"]
                semantic.update({
                    "semantic_class": "MERCHANDISE",
                    "numeric_confidence": 0.9,
                    "confidence_state": "HIGH_CONFIDENCE_SUGGESTION",
                    "operator_confirmation_required": False,
                    "semantic_status": "PROPOSED",
                })
        corrupt = next(
            item for item in result["semantic_candidate_lines"]
            if item.get("source_line_index") == corrupt_source_index
        )
        if not any(item.get("source_line_index") == corrupt_source_index for item in result["lines"]):
            result["lines"].append(copy.deepcopy(corrupt))
        result["receipt_math"] = {
            "status": "RECONCILED_EXACT",
            "allocation_ready": True,
            "version": "receipt-structured-math-v1",
            "merchandise_total_cents": 1653,
            "printed_subtotal_cents": 1600,
            "final_paid_cents": 1653,
            "difference_cents": 0,
            "components": [],
        }
        result["parser_version"] = "receipt-structured-math-v1"
        return result


class ActiveSemanticStateTests(ReceiptFixture):
    def two_generation_fantasy_bay(self):
        result = self.add_line(self.acquisition(), "OP deck", quantity=1)
        result, document = self.attach(result, receipt_pdf(FANTASY_BAY.splitlines()))
        first = queue_extraction(self.db, document["id"], {
            "request_id": "EXTRACT-FANTASY-LEGACY",
            "expected_revision": result["acquisition"]["revision"],
            "auto_apply": True,
        }, self.store, VersionedFantasyBayExtractor(legacy=True))
        legacy_semantics = current_semantic_lines(
            self.db, acquisition_id=result["acquisition"]["id"]
        )
        legacy_corrupt = next(
            item for item in legacy_semantics
            if item["normalized_text"] == "UEZ (3.3125%5)} $0.53"
        )
        refreshed = acquisition_payload(self.db, result["acquisition"]["id"])
        self.assertEqual(refreshed["acquisition"]["merchant_name"], "| } 7A/V\\TASY BAV ~~")
        second = queue_extraction(self.db, document["id"], {
            "request_id": "EXTRACT-FANTASY-REMEDIATION2",
            "expected_revision": refreshed["acquisition"]["revision"],
            "retry_of_job_id": first["id"],
            "auto_apply": True,
        }, self.store, VersionedFantasyBayExtractor(legacy=False))
        return acquisition_payload(self.db, result["acquisition"]["id"]), document, first, second, legacy_corrupt

    def test_only_newest_generation_is_active_and_history_remains_inspectable(self):
        result, _, first, second, legacy_corrupt = self.two_generation_fantasy_bay()
        review = result["receipt_intelligence"]["semantic_review"]

        self.assertEqual(review["total_stored_assertion_count"], 48)
        self.assertEqual(review["active_assertion_count"], 24)
        self.assertEqual(review["historical_assertion_count"], 24)
        self.assertEqual(
            review["needs_confirmation_count"],
            sum(1 for item in review["lines"] if item["operator_confirmation_required"]),
        )
        self.assertTrue(all(item["job_id"] == second["id"] for item in review["lines"]))
        self.assertTrue(all(not item["active"] for item in review["history"]))
        self.assertTrue(any(item["job_id"] == first["id"] for item in review["history"]))
        old = next(item for item in review["history"] if item["id"] == legacy_corrupt["id"])
        self.assertEqual(old["inactive_reason"], "SUPERSEDED_EXTRACTION")
        self.assertEqual(old["superseded_by_job_uuid"], second["job_uuid"])
        self.assertFalse(old["product_match_eligible"])

    def test_superseded_merchandise_and_financial_semantics_cannot_drive_downstream(self):
        result, _, first, _, legacy_corrupt = self.two_generation_fantasy_bay()
        intelligence = result["receipt_intelligence"]
        old_receipt_line = self.db.execute(
            "SELECT id FROM receipt_lines WHERE job_id=? AND line_sequence=?",
            (first["id"], legacy_corrupt["source_line_index"]),
        ).fetchone()
        if old_receipt_line is None:
            old_receipt_line = self.db.execute(
                "SELECT id FROM receipt_lines WHERE job_id=? AND description LIKE 'UEZ%'",
                (first["id"],),
            ).fetchone()
        self.assertIsNotNone(old_receipt_line)
        self.assertFalse(semantic_allows_receipt_line(self.db, int(old_receipt_line["id"])))
        self.assertEqual(
            [item["description"] for item in intelligence["receipt_lines"]],
            ["OP deck"],
        )
        self.assertEqual(intelligence["receipt_math"]["status"], "UNRECONCILED")
        self.assertIsNone(intelligence["allocation_proposal"])
        self.assertFalse(result["single_product_allocation_eligibility"]["eligible"])
        with self.assertRaisesRegex(ValueError, "historical"):
            decide_semantic_line(self.db, legacy_corrupt["semantic_uuid"], {
                "request_id": "STALE-SEMANTIC-DECISION", "action": "CONFIRM",
            })

    def test_current_merchant_refreshes_but_operator_override_never_does(self):
        refreshed, _, _, _, _ = self.two_generation_fantasy_bay()
        self.assertEqual(refreshed["acquisition"]["merchant_name"], "Fantasy Bay")
        provenance = self.db.execute(
            """SELECT status,proposed_value FROM acquisition_field_provenance
                 WHERE acquisition_id=? AND field_name='merchant_name' ORDER BY id""",
            (refreshed["acquisition"]["id"],),
        ).fetchall()
        self.assertEqual([row["status"] for row in provenance], ["SUPERSEDED", "PROPOSED"])
        self.assertEqual(provenance[-1]["proposed_value"], "Fantasy Bay")

        other = self.add_line(self.acquisition("ACQ-FANTASY-OPERATOR"), "OP deck", quantity=1)
        other, document = self.attach(
            other, receipt_pdf(FANTASY_BAY.splitlines()), request="DOC-FANTASY-OPERATOR"
        )
        first = queue_extraction(self.db, document["id"], {
            "request_id": "EXTRACT-FANTASY-OPERATOR-LEGACY",
            "expected_revision": other["acquisition"]["revision"], "auto_apply": True,
        }, self.store, VersionedFantasyBayExtractor(legacy=True))
        other = acquisition_payload(self.db, other["acquisition"]["id"])
        other = autosave_acquisition(self.db, other["acquisition"]["id"], {
            "request_id": "OPERATOR-CONFIRMS-MERCHANT",
            "expected_revision": other["acquisition"]["revision"],
            "merchant_name": "Operator Confirmed Shop",
        })
        queue_extraction(self.db, document["id"], {
            "request_id": "EXTRACT-FANTASY-OPERATOR-NEW",
            "expected_revision": other["acquisition"]["revision"],
            "retry_of_job_id": first["id"], "auto_apply": True,
        }, self.store, VersionedFantasyBayExtractor(legacy=False))
        other = acquisition_payload(self.db, other["acquisition"]["id"])
        self.assertEqual(other["acquisition"]["merchant_name"], "Operator Confirmed Shop")

    def test_removed_document_semantics_are_history_only(self):
        result, document, _, _, _ = self.two_generation_fantasy_bay()
        tombstone_document(self.db, document["id"], {
            "request_id": "REMOVE-FANTASY-RECEIPT",
            "expected_revision": result["acquisition"]["revision"],
            "reason_code": "OPERATOR_REMOVED",
            "notes": "Wrong receipt attached during draft review",
        }, self.store)
        result = acquisition_payload(self.db, result["acquisition"]["id"])
        intelligence = result["receipt_intelligence"]
        review = intelligence["semantic_review"]
        self.assertEqual(intelligence["jobs"], [])
        self.assertEqual(review["active_assertion_count"], 0)
        self.assertEqual(review["historical_assertion_count"], 48)
        self.assertTrue(all(item["inactive_reason"] == "REMOVED_DOCUMENT" for item in review["history"]))
        self.assertEqual(intelligence["receipt_lines"], [])
        self.assertIsNone(intelligence["receipt_math"])

    def test_fantasy_bay_safety_and_migration_boundary_remain_unchanged(self):
        result, _, _, _, _ = self.two_generation_fantasy_bay()
        self.assertEqual(result["receipt_intelligence"]["receipt_math"]["status"], "UNRECONCILED")
        self.assertIsNone(result["automatic_single_line_allocation_preview"])
        with self.assertRaisesRegex(ValueError, "Automatic allocation is not ready"):
            confirm_acquisition(self.db, result["acquisition"]["id"], {
                "request_id": "CONFIRM-FANTASY-REMEDIATION4-BLOCKED",
                "expected_revision": result["acquisition"]["revision"],
                "confirm_authoritative_financial_facts": True,
                "confirm_reconciliation": True,
            })
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM acquisition_events WHERE acquisition_id=? AND event_type='ALLOCATION_CONFIRMED'",
            (result["acquisition"]["id"],),
        ).fetchone()[0], 0)
        migrations = [row[0] for row in self.db.execute(
            "SELECT migration_id FROM schema_migrations ORDER BY migration_id"
        ).fetchall()]
        self.assertEqual(len(migrations), 19)
        self.assertEqual(migrations[-1], "0019_v24_sam_multi_evidence_operator_trial_v1a")


if __name__ == "__main__":
    import unittest

    unittest.main()
