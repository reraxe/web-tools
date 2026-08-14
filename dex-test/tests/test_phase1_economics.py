import json
import unittest
from pathlib import Path

from dex_economics import (
    ACQUISITION_MODES,
    CALCULATION_VERSION,
    ORDER_TYPES,
    RECYCLE_REASON_CODES,
    allocate_cents,
    allocate_weighted_cents,
)


class ExactCentAllocationTest(unittest.TestCase):
    def test_ten_dollars_across_three_stable_card_ids(self):
        allocations = allocate_cents(1000, [3, 1, 2])
        self.assertEqual(
            [(item.stable_id, item.cents) for item in allocations],
            [(1, 334), (2, 333), (3, 333)],
        )
        self.assertEqual(sum(item.cents for item in allocations), 1000)

    def test_input_and_ui_order_cannot_change_remainder_assignment(self):
        forward = allocate_cents(1001, ["OP-B-003", "OP-B-001", "OP-B-002"])
        reverse = allocate_cents(1001, ["OP-B-002", "OP-B-003", "OP-B-001"])
        expected = [("OP-B-001", 334), ("OP-B-002", 334), ("OP-B-003", 333)]
        self.assertEqual([(item.stable_id, item.cents) for item in forward], expected)
        self.assertEqual([(item.stable_id, item.cents) for item in reverse], expected)

    def test_zero_total_reconciles_and_nonzero_requires_recipients(self):
        self.assertEqual(allocate_cents(0, []), ())
        with self.assertRaises(ValueError):
            allocate_cents(1, [])

    def test_invalid_or_duplicate_identifiers_are_rejected(self):
        with self.assertRaises(ValueError):
            allocate_cents(100, [1, 1])
        with self.assertRaises(TypeError):
            allocate_cents(100, [True])
        with self.assertRaises(TypeError):
            allocate_cents(100, [""])

    def test_negative_or_non_integer_money_is_rejected(self):
        with self.assertRaises(ValueError):
            allocate_cents(-1, [1])
        with self.assertRaises(TypeError):
            allocate_cents(10.0, [1])

    def test_weighted_order_allocation_is_exact_stable_and_signed(self):
        allocations = allocate_weighted_cents(100, [(30, 1), (10, 1), (20, 1)])
        self.assertEqual(
            [(item.stable_id, item.cents) for item in allocations],
            [(10, 34), (20, 33), (30, 33)],
        )
        negative = allocate_weighted_cents(-5, [(2, 3), (1, 2)])
        self.assertEqual(sum(item.cents for item in negative), -5)


class ApprovedRuleFixtureTest(unittest.TestCase):
    def test_fixture_covers_approved_phase_scenarios(self):
        fixture_path = Path(__file__).parent / "fixtures" / "phase1_economics_scenarios.json"
        scenarios = json.loads(fixture_path.read_text(encoding="utf-8"))
        ids = {scenario["id"] for scenario in scenarios}
        self.assertEqual(len(ids), len(scenarios))
        self.assertTrue({"full_box_rip", "partial_rip", "legacy_batch", "receipt_group"} <= ids)
        self.assertTrue({"known_quantity_bulk", "unknown_quantity_bulk"} <= ids)
        self.assertTrue({"sealed_only_sale", "card_only_sale", "rejected_mixed_order"} <= ids)
        self.assertTrue(CALCULATION_VERSION)
        self.assertEqual(set(ACQUISITION_MODES), {
            "SEALED_RIP", "SINGLES_KNOWN_COST", "SINGLES_LUMP_SUM",
        })
        self.assertEqual(set(ORDER_TYPES), {"CARD", "SEALED"})
        self.assertIn("DUPLICATE_ENTRY_ERROR", RECYCLE_REASON_CODES)
        self.assertIn("MISSING_LOST", RECYCLE_REASON_CODES)


if __name__ == "__main__":
    unittest.main()
