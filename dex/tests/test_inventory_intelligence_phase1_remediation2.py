import json
import unittest
from pathlib import Path

from dex_receipt_parser import PARSER_VERSION, parse_receipt_pages
from dex_receipt_semantics import (
    ENGINE_VERSION,
    RULES_VERSION,
    classify_receipt_pages,
    classify_source_line,
    semantic_line_payload,
)
from tests.test_inventory_intelligence_phase1 import GOLDEN_TEXT
from tests.test_inventory_intelligence_phase1_remediation1 import (
    CLEAN_SPECIALTY,
    IRREGULAR_VENDOR,
    LARGE_RETAILER,
)


FIXTURES = Path(__file__).parent / "fixtures"
FANTASY_BAY = (FIXTURES / "fantasy_bay_synthetic.txt").read_text(encoding="utf-8")
ECOMMERCE = (FIXTURES / "synthetic_ecommerce_receipt.txt").read_text(encoding="utf-8")


class ReceiptSemanticRemediation2Tests(unittest.TestCase):
    def classify(self, text, index=1):
        return classify_source_line(
            text,
            source_line_index=index,
            source_page=1,
            source_location=f"line {index}",
            parser_version=PARSER_VERSION,
        )

    @staticmethod
    def eligible(result):
        row = dict(result)
        row["evidence"] = json.dumps(row["evidence"])
        return semantic_line_payload(row)["product_match_eligible"]

    def test_rules_and_parser_versions_identify_remediation2(self):
        self.assertIn("remediation2", ENGINE_VERSION)
        self.assertIn("remediation2", RULES_VERSION)
        self.assertIn("remediation2", PARSER_VERSION)

    def test_corrupted_tax_like_amount_fails_closed_before_matching(self):
        cases = (
            "UEZ (3.3125%5)} $0.53",
            "S4L3S T4X 3.3% $0.53",
            "CITY ? (2.00%) 0.40",
        )
        for text in cases:
            with self.subTest(text=text):
                result = self.classify(text)
                self.assertIn(result["semantic_class"], {"TAX", "UNKNOWN"})
                self.assertNotEqual(result["semantic_class"], "MERCHANDISE")
                self.assertFalse(self.eligible(result))
        fantasy = self.classify(cases[0])
        self.assertEqual(fantasy["semantic_class"], "UNKNOWN")
        self.assertEqual(fantasy["confidence_state"], "UNRESOLVED")
        self.assertIn("PERCENT_AMOUNT_FINANCIAL_UNKNOWN", fantasy["evidence"]["codes"])

    def test_explicit_and_ocr_near_tax_labels_remain_tax(self):
        for text in (
            "TAX $0.53", "SALES TAX $0.53", "STATE TAX $0.53",
            "LOCAL TAX $0.53", "CITY TAX $0.53", "NJ TAX $0.53",
            "TX $0.53", "VAT $0.53", "T4X $0.53", "TAK $0.53",
        ):
            with self.subTest(text=text):
                result = self.classify(text)
                self.assertEqual(result["semantic_class"], "TAX")
                self.assertFalse(self.eligible(result))

    def test_payment_identity_and_support_metadata_never_match(self):
        expected = {
            "@ MasterCard 0000 (Contactless)": "TENDER_PAYMENT_METHOD",
            "Visa ending 1234": "TENDER_PAYMENT_METHOD",
            "Debit **** 1234": "TENDER_PAYMENT_METHOD",
            "AMEX 1005": "TENDER_PAYMENT_METHOD",
            "Discover": "TENDER_PAYMENT_METHOD",
            "Apple Pay": "TENDER_PAYMENT_METHOD",
            "Google Pay": "TENDER_PAYMENT_METHOD",
            "Contactless": "TENDER_PAYMENT_METHOD",
            "Card ending 1234": "TENDER_PAYMENT_METHOD",
            "Auth code: 000000": "STRUCTURAL",
            "AID: A0000000000000": "STRUCTURAL",
            "No CVM": "STRUCTURAL",
        }
        for text, semantic_class in expected.items():
            with self.subTest(text=text):
                result = self.classify(text)
                self.assertEqual(result["semantic_class"], semantic_class)
                self.assertFalse(self.eligible(result))
                self.assertFalse(result["operator_confirmation_required"])

    def test_policy_words_require_transaction_context_for_discount(self):
        nonfinancial = (
            "for store credit within two weeks of the purchase date.",
            "store credit only",
            "credit card accepted",
            "credit policy",
            "return for credit",
            "refund policy applies",
            "returns and exchanges within 14 days",
            "discount policy available online",
        )
        for text in nonfinancial:
            with self.subTest(text=text):
                result = self.classify(text, index=18)
                self.assertNotEqual(result["semantic_class"], "DISCOUNT_CREDIT")
                self.assertFalse(self.eligible(result))
        for text in (
            "Store Credit -$5.00", "Credit Applied -5.00", "Promo Credit -2.00",
            "Discount -1.80", "Coupon -3.00",
        ):
            with self.subTest(text=text):
                self.assertEqual(self.classify(text)["semantic_class"], "DISCOUNT_CREDIT")

    def test_fantasy_bay_golden_family_is_safe_and_ranked(self):
        parsed = parse_receipt_pages([(1, FANTASY_BAY)])
        lines = {item["normalized_text"]: item for item in parsed["semantic_lines"]}
        expected = {
            "OP deck $16.00": "MERCHANDISE",
            "Purchase Subtotal $16.00": "SUBTOTAL",
            "Total $16.53": "TOTAL",
            "@ MasterCard 0000 (Contactless)": "TENDER_PAYMENT_METHOD",
            "Auth code: 000000": "STRUCTURAL",
            "AID: A0000000000000": "STRUCTURAL",
            "No CVM": "STRUCTURAL",
            "for store credit within two weeks of the purchase date.": "INFORMATIONAL_FOOTER",
        }
        for text, semantic_class in expected.items():
            self.assertEqual(lines[text]["semantic_class"], semantic_class)
        self.assertEqual(lines["UEZ (3.3125%5)} $0.53"]["semantic_class"], "UNKNOWN")
        self.assertEqual(parsed["receipt_math"]["status"], "UNRECONCILED")
        self.assertEqual(parsed["receipt_math"]["difference_cents"], 53)
        self.assertEqual([item["description"] for item in parsed["lines"]], ["OP deck"])
        self.assertEqual(len(parsed["semantic_lines"]), 24)

        candidate = next(item for item in parsed["candidates"] if item["field_name"] == "merchant_name")
        self.assertEqual(candidate["normalized_value"], "Fantasy Bay")
        self.assertEqual(candidate["source_location"], "line 2")
        ranking = parsed["merchant_candidate_ranking"]
        self.assertEqual(next(item for item in ranking if item["eligible"])["value"], "Fantasy Bay")
        garbage = next(item for item in ranking if item["source_line_index"] == 1)
        self.assertFalse(garbage["eligible"])
        self.assertIn("LOW_TEXT_QUALITY", garbage["evidence_codes"])
        address = next(item for item in ranking if item["source_line_index"] == 3)
        self.assertFalse(address["eligible"])
        self.assertIn("ADDRESS_LINE", address["evidence_codes"])

    def test_garbage_header_is_not_proposed_when_no_plausible_merchant_exists(self):
        parsed = parse_receipt_pages([(1, "| } /\\ ~~ 88\nTotal $1.00")])
        self.assertFalse(any(item["field_name"] == "merchant_name" for item in parsed["candidates"]))

    def test_review_noise_drops_without_hiding_financial_uncertainty(self):
        parsed = parse_receipt_pages([(1, FANTASY_BAY)])
        review = [item for item in parsed["semantic_lines"] if item["operator_confirmation_required"]]
        self.assertLessEqual(len(review), 3)
        self.assertIn("UEZ (3.3125%5)} $0.53", {item["normalized_text"] for item in review})
        self.assertTrue(all(
            item["semantic_class"] not in {"MERCHANDISE", "TAX", "TOTAL", "SUBTOTAL", "TENDER_PAYMENT_METHOD"}
            or item["confidence_state"] in {"UNRESOLVED", "CONFLICTING"}
            for item in review
        ))

    def test_only_true_fantasy_bay_merchandise_is_product_match_eligible(self):
        parsed = parse_receipt_pages([(1, FANTASY_BAY)])
        eligible = {
            item["normalized_text"] for item in parsed["semantic_lines"]
            if self.eligible(item)
        }
        self.assertEqual(eligible, {"OP deck $16.00"})
        blocked_fragments = (
            "UEZ", "MasterCard", "Auth code", "AID", "No CVM", "store credit",
            "Broadway", "BAYONNE", "Subtotal", "Total",
        )
        self.assertFalse(any(
            fragment.lower() in line.lower()
            for fragment in blocked_fragments
            for line in eligible
        ))

    def test_mom_and_pop_and_prior_blockers_remain_unchanged(self):
        parsed = parse_receipt_pages([(1, GOLDEN_TEXT)])
        self.assertEqual(parsed["receipt_math"]["status"], "RECONCILED_EXACT")
        self.assertEqual(parsed["receipt_math"]["merchandise_total_cents"], 12800)
        self.assertEqual(parsed["receipt_math"]["printed_subtotal_cents"], 12999)
        self.assertEqual(parsed["receipt_math"]["final_paid_cents"], 13417)
        for text in ("VISA PAYMENT 21.60", "CHANGE 0.00", "AMT DUE 11.91", "cash paid 12.00"):
            result = self.classify(text)
            self.assertNotEqual(result["semantic_class"], "MERCHANDISE")
            self.assertFalse(self.eligible(result))

    def test_all_generalization_families_preserve_safe_matching(self):
        families = {
            "clean_specialty": CLEAN_SPECIALTY,
            "large_retailer": LARGE_RETAILER,
            "irregular_vendor": IRREGULAR_VENDOR,
            "mom_and_pop": GOLDEN_TEXT,
            "fantasy_bay": FANTASY_BAY,
            "ecommerce": ECOMMERCE,
        }
        for family, source in families.items():
            with self.subTest(family=family):
                parsed = parse_receipt_pages([(1, source)])
                false_merchandise = {
                    item["normalized_text"] for item in parsed["semantic_lines"]
                    if item["semantic_class"] == "MERCHANDISE"
                    and any(token in item["normalized_text"].lower() for token in (
                        "payment", "change", "amt due", "cash paid", "subtotal", "total",
                        "tax", "shipping", "auth", "aid", "cvm", "store credit",
                    ))
                }
                self.assertEqual(false_merchandise, set())
        ecommerce = parse_receipt_pages([(1, ECOMMERCE)])
        self.assertEqual(ecommerce["receipt_math"]["status"], "RECONCILED_EXACT")
        self.assertEqual(ecommerce["receipt_math"]["final_paid_cents"], 2332)
        self.assertEqual(
            [item["description"] for item in ecommerce["lines"]],
            ["One Piece starter deck"],
        )


if __name__ == "__main__":
    unittest.main()
