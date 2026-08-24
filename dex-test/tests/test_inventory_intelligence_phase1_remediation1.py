import json
import unittest

from dex_receipt_semantics import classify_receipt_pages, classify_source_line, semantic_line_payload


LARGE_RETAILER = """BIG BOX STORE
ITEM DESCRIPTION QTY PRICE
One Piece pack x2 10.00
Riftbound starter x1 12.00
COUPON -2.00
SUBTOTAL 20.00
STATE TAX 1.20
COUNTY TAX 0.40
TOTAL 21.60
VISA PAYMENT 21.60
CHANGE 0.00
VISIT AGAIN
"""

IRREGULAR_VENDOR = """LOCAL VENDOR BOOTH 7
OP tcg pks 3 @ 4 12.00
MYST ADJ -1.00
TX .91
AMT DUE 11.91
cash paid 12.00
smudged ?? line
"""

CLEAN_SPECIALTY = """Clean Card Shop
One Piece booster box x1 120.00
Subtotal 120.00
Sales Tax 7.20
Total 127.20
Thank you
"""


class ReceiptSemanticRemediationTests(unittest.TestCase):
    def classify(self, text):
        return classify_source_line(
            text,
            source_line_index=1,
            source_page=1,
            source_location="line 1",
            parser_version="remediation1-test",
        )

    def eligible(self, result):
        row = dict(result)
        row["evidence"] = json.dumps(row["evidence"])
        return semantic_line_payload(row)["product_match_eligible"]

    def test_acceptance_blockers_are_financial_and_never_match_eligible(self):
        expected = {
            "VISA PAYMENT 21.60": "TENDER_PAYMENT_METHOD",
            "CHANGE 0.00": "PAYMENT_SUMMARY",
            "AMT DUE 11.91": "TOTAL",
            "cash paid 12.00": "PAYMENT_SUMMARY",
        }
        for text, semantic_class in expected.items():
            with self.subTest(text=text):
                result = self.classify(text)
                self.assertEqual(result["semantic_class"], semantic_class)
                self.assertFalse(self.eligible(result))

    def test_payment_tender_due_and_change_variants_never_enter_matching(self):
        cases = (
            "Visa 21.60", "Visa Payment $21.60", "Card Paid 21.60",
            "Cash 12.00", "Cash Paid $12", "Tendered 20.00",
            "Amt Due 11.91", "Amount Due $11.91", "Balance Due 11.91",
            "Change 0.00", "Change Due $0.00", "Payment 134.17",
            "Mastercard Payment 21.60", "MC Payment 21.60",
            "Amex 21.60", "Discover 21.60", "Debit Payment 21.60",
            "Cash Tendered 20.00", "Cash Back 5.00",
        )
        for text in cases:
            with self.subTest(text=text):
                result = self.classify(text)
                self.assertNotEqual(result["semantic_class"], "MERCHANDISE")
                self.assertFalse(self.eligible(result))

    def test_ambiguous_financial_and_unreadable_ocr_fail_closed(self):
        for text in ("V1SA PYMT 21.60", "card pmt 21.60", "smudged ?? line"):
            with self.subTest(text=text):
                result = self.classify(text)
                self.assertEqual(result["semantic_class"], "UNKNOWN")
                self.assertEqual(result["confidence_state"], "UNRESOLVED")
                self.assertFalse(self.eligible(result))

    def test_tax_abbreviation_with_amount_is_tax_not_structural(self):
        result = self.classify("TX .91")
        self.assertEqual(result["semantic_class"], "TAX")
        self.assertFalse(self.eligible(result))

    def test_payment_words_inside_real_product_names_remain_merchandise(self):
        cases = (
            "Cash Grab Promo Card 5.00",
            "Visa Character Card 3.00",
            "Balance of Judgment Booster 4.99",
            "Payment Plan Starter Deck 20.00",
            "Cash Back Attack Card 2.50",
        )
        for text in cases:
            with self.subTest(text=text):
                result = self.classify(text)
                self.assertEqual(result["semantic_class"], "MERCHANDISE")
                self.assertTrue(self.eligible(result))

    def test_three_frozen_generalization_receipts_are_safe(self):
        reports = {
            "clean_specialty": classify_receipt_pages([(1, CLEAN_SPECIALTY)], parser_version="remediation1-generalization"),
            "large_retailer": classify_receipt_pages([(1, LARGE_RETAILER)], parser_version="remediation1-generalization"),
            "irregular_vendor": classify_receipt_pages([(1, IRREGULAR_VENDOR)], parser_version="remediation1-generalization"),
        }
        for family, lines in reports.items():
            with self.subTest(family=family):
                financial_false_merchandise = {
                    item["normalized_text"] for item in lines
                    if item["semantic_class"] == "MERCHANDISE"
                    and any(token in item["normalized_text"].lower() for token in ("payment", "change", "amt due", "cash paid"))
                }
                self.assertEqual(financial_false_merchandise, set())
        irregular = {item["normalized_text"]: item for item in reports["irregular_vendor"]}
        self.assertEqual(irregular["MYST ADJ -1.00"]["confidence_state"], "UNRESOLVED")
        self.assertEqual(irregular["smudged ?? line"]["confidence_state"], "UNRESOLVED")


if __name__ == "__main__":
    unittest.main()
