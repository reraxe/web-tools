from pathlib import Path

from dex_inbound import acquisition_payload, autosave_acquisition, confirm_acquisition
from dex_receipts import classify_receipt_line
from tests.test_v22_phase5_receipts import ReceiptFixture, receipt_pdf


FIXTURES = Path(__file__).parent / "fixtures"
FANTASY_BAY = (FIXTURES / "fantasy_bay_synthetic.txt").read_text(encoding="utf-8")


class SingleProductReceiptAllocationSafetyTests(ReceiptFixture):
    def test_fantasy_bay_unreconciled_math_cannot_assign_final_paid_automatically(self):
        result = self.add_line(self.acquisition(), "OP deck", quantity=1)
        result, document = self.attach(result, receipt_pdf(FANTASY_BAY.splitlines()))
        result, _ = self.extract(result, document)

        self.assertEqual(result["acquisition"]["merchant_name"], "Fantasy Bay")
        self.assertEqual(result["acquisition"]["final_usd_paid_cents"], 1653)
        self.assertEqual(result["receipt_intelligence"]["receipt_math"]["status"], "UNRECONCILED")
        eligibility = result["single_product_allocation_eligibility"]
        self.assertFalse(eligibility["eligible"])
        self.assertEqual(eligibility["status"], "BLOCKED")
        self.assertEqual(eligibility["authority_source"], "RECEIPT_INTELLIGENCE")
        self.assertIn("RECEIPT_MATH_UNRECONCILED", eligibility["reason_codes"])
        self.assertIn("UNRESOLVED_AMOUNT_BEARING_RECEIPT_LINE", eligibility["reason_codes"])
        self.assertIsNone(result["automatic_single_line_allocation_preview"])
        self.assertIn(
            "SINGLE_PRODUCT_ALLOCATION_BLOCKED",
            {warning["code"] for warning in result["readiness"]["warnings"]},
        )

        acquisition = result["acquisition"]
        with self.assertRaisesRegex(
            ValueError,
            "Automatic allocation is not ready. Resolve receipt financial discrepancies first.",
        ):
            confirm_acquisition(self.db, acquisition["id"], {
                "request_id": "CONFIRM-FANTASY-BAY-BLOCKED",
                "expected_revision": acquisition["revision"],
                "confirm_authoritative_financial_facts": True,
                "confirm_reconciliation": True,
            })

        stored = self.db.execute(
            "SELECT assigned_landed_cost_cents,allocation_status FROM acquisition_lines WHERE acquisition_id=?",
            (acquisition["id"],),
        ).fetchone()
        self.assertIsNone(stored["assigned_landed_cost_cents"])
        self.assertEqual(stored["allocation_status"], "UNALLOCATED")
        self.assertEqual(
            self.db.execute(
                "SELECT COUNT(*) FROM acquisition_events WHERE acquisition_id=? AND event_type='ALLOCATION_CONFIRMED'",
                (acquisition["id"],),
            ).fetchone()[0],
            0,
        )

    def test_exact_reconciled_single_product_receipt_retains_existing_automatic_path(self):
        result = self.add_line(self.acquisition(), "OP deck", quantity=1)
        exact = receipt_pdf([
            "Merchant: Fantasy Bay",
            "Date: 2026-08-20",
            "Credit / Debit Card",
            "ITEM | OP deck | QTY 1 | UNIT 16.00 | TOTAL 16.00",
            "Subtotal: 16.00",
            "Tax: 0.53",
            "Total: 16.53",
        ])
        result, document = self.attach(result, exact, request="DOC-EXACT-SINGLE")
        result, _ = self.extract(result, document, request="EXTRACT-EXACT-SINGLE")

        self.assertEqual(result["receipt_intelligence"]["receipt_math"]["status"], "RECONCILED_EXACT")
        eligibility = result["single_product_allocation_eligibility"]
        self.assertTrue(eligibility["eligible"])
        self.assertEqual(eligibility["authority_source"], "RECONCILED_RECEIPT")
        self.assertEqual(result["automatic_single_line_allocation_preview"]["assigned_landed_cost_cents"], 1653)

        acquisition = result["acquisition"]
        confirmed = confirm_acquisition(self.db, acquisition["id"], {
            "request_id": "CONFIRM-EXACT-SINGLE",
            "expected_revision": acquisition["revision"],
            "confirm_authoritative_financial_facts": True,
            "confirm_reconciliation": True,
        })
        self.assertEqual(confirmed["lines"][0]["assigned_landed_cost_cents"], 1653)
        self.assertEqual(confirmed["lines"][0]["allocation_method"], "SINGLE_LINE_100_PERCENT")

    def test_manual_single_product_without_receipt_retains_existing_automatic_path(self):
        result = self.add_line(self.acquisition(final=1653, merchant="Manual Shop"), "OP deck", quantity=1)
        result = autosave_acquisition(self.db, result["acquisition"]["id"], {
            "request_id": "MANUAL-SINGLE-FACTS",
            "expected_revision": result["acquisition"]["revision"],
            "purchased_on": "2026-08-20",
            "purchase_subtotal_cents": 1653,
        })
        self.assertTrue(result["single_product_allocation_eligibility"]["eligible"])
        self.assertEqual(
            result["single_product_allocation_eligibility"]["authority_source"],
            "MANUAL_PURCHASE_FACTS",
        )
        self.assertEqual(result["automatic_single_line_allocation_preview"]["assigned_landed_cost_cents"], 1653)

    def test_mixed_purchase_policy_required_still_blocks_single_product_allocation(self):
        result = self.add_line(self.acquisition(), "OP deck", quantity=1)
        mixed = receipt_pdf([
            "Merchant: Mixed Shop",
            "Date: 2026-08-20",
            "Credit / Debit Card",
            "ITEM | OP deck | QTY 1 | UNIT 16.00 | TOTAL 16.00",
            "ITEM | Birthday Gift | QTY 1 | UNIT 4.00 | TOTAL 4.00",
            "Subtotal: 20.00",
            "Tax: 1.00",
            "Total: 21.00",
        ])
        result, document = self.attach(result, mixed, request="DOC-MIXED-SINGLE")
        result, _ = self.extract(result, document, request="EXTRACT-MIXED-SINGLE")
        unmatched = next(
            item for item in result["receipt_intelligence"]["receipt_lines"]
            if item["description"] == "Birthday Gift"
        )
        policy = classify_receipt_line(self.db, unmatched["id"], {
            "request_id": "CLASSIFY-MIXED-SINGLE",
            "expected_revision": result["acquisition"]["revision"],
            "classification": "PERSONAL_NONBUSINESS",
            "notes": "Not business inventory",
        })
        self.assertEqual(policy["allocation_policy"]["status"], "POLICY_REQUIRED")
        refreshed = acquisition_payload(self.db, result["acquisition"]["id"])
        eligibility = refreshed["single_product_allocation_eligibility"]
        self.assertFalse(eligibility["eligible"])
        self.assertIn("MIXED_PURCHASE_ALLOCATION_POLICY_REQUIRED", eligibility["reason_codes"])
        self.assertIsNone(refreshed["automatic_single_line_allocation_preview"])

    def test_read_only_payload_rechecks_receipt_state_without_persisting_basis(self):
        result = self.add_line(self.acquisition(), "OP deck", quantity=1)
        result, document = self.attach(result, receipt_pdf(FANTASY_BAY.splitlines()), request="DOC-READ-ONLY")
        result, _ = self.extract(result, document, request="EXTRACT-READ-ONLY")
        before = self.db.total_changes
        refreshed = acquisition_payload(self.db, result["acquisition"]["id"])
        self.assertFalse(refreshed["single_product_allocation_eligibility"]["eligible"])
        self.assertEqual(self.db.total_changes, before)


if __name__ == "__main__":
    import unittest

    unittest.main()
