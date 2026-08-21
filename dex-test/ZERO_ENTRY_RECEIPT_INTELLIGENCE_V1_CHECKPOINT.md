# DEX Zero-Entry Receipt Intelligence v1 — Development Checkpoint

Status: **Implementation complete; operator review required. Not deployed and not packaged as a production release.**

Baseline: immutable DEX v2.2-test RC3 HF2 full checkpoint.

## Outcome

The normal acquisition entry path is now receipt-first:

1. Start a new acquisition.
2. Photograph or upload a JPG, JPEG, PNG, or text-layer PDF receipt.
3. DEX extracts non-authoritative receipt facts locally.
4. DEX proves the printed receipt arithmetic before proposing allocation.
5. Exact catalog matches prepare draft acquisition lines.
6. The operator answers only unresolved business-purpose questions.
7. Existing acquisition confirmation remains the authority boundary.

Advanced/manual purchase facts remain available as the HF2 fallback.

## Architecture and authority boundary

- `dex_receipt_ocr.py` is a private local Tesseract adapter. Originals are immutable. Derived normalized images use a temporary directory and are removed before return. No external service receives receipt data.
- `dex_receipt_parser.py` produces structured candidates, line items, provenance, component roles, and an explicit receipt-math result. It never invents a missing value.
- `dex_receipts.py` retains the provider-neutral orchestration, append-only extraction events, catalog matching, operator classification, and deterministic proposal boundary.
- Raw OCR text is neither persisted in SQLite nor exposed through the API. Structured evidence and timing metadata use the existing receipt event ledger.
- Extraction candidates and deterministic proposals remain non-authoritative. `confirm_acquisition` remains the sole authority boundary for acquisition economics.
- Exact catalog identity or identifier matches can prepare draft product lines. Fuzzy matches remain suggestions only.
- PACK_PRODUCT exact matches use the existing strong inventory rule. A broader SEALED_PRODUCT whose purpose is not knowable remains an operator question.

No migration 0016 is required. Existing migration 0011 receipt tables, the event payload ledger, and migration 0015 mixed-purchase fields are sufficient.

## Receipt math and allocation policy

DEX first proves two printed equations where evidence permits:

- merchandise plus components included in the printed subtotal = printed subtotal
- printed subtotal plus components outside the subtotal = final paid

Components printed for visibility are not counted twice. Multiple valid interpretations produce `AMBIGUOUS`; failed arithmetic produces `UNRECONCILED`; neither may generate an automatic allocation proposal.

For already-supported all-inventory acquisitions, DEX retains `RECEIPT_VALUE_PROPORTIONAL` / `receipt-landed-allocation-v1`: each separately preserved shared component is allocated proportionally by merchandise value, with the established fractional-remainder and immutable acquisition-line-ID rule. The proposal remains non-authoritative until acquisition confirmation.

Mixed inventory/noninventory acquisitions stop at `POLICY_REQUIRED`. DEX preserves sales tax, transaction/card fees, shipping/freight, purchase-level discounts/credits, and their receipt-math roles separately, but does not assign them between inventory and noninventory until an accounting policy is approved. No net shared-delta shortcut or automatic excluded amount is used.

This policy does not classify tax deductibility, owner draws, expenses, or general-ledger treatment.

## Canonical Mom and Pop result

- Merchant: Mom and Pop Shop
- Products: OP13 packs ×4 ($30.00), Riftbound Vendetta packs ×6 ($30.00), Gear Five Luffy ×1 ($18.00), Hobbit Collector Booster ×1 ($50.00)
- Printed discount: -$1.80, classified as included in subtotal
- Printed card fee: $3.79, classified as included in subtotal
- Printed subtotal: $129.99
- Tax outside subtotal: $4.18
- Final paid: $134.17
- Receipt math: `RECONCILED_EXACT`
- Exact catalog matches: 4/4
- Operator questions: 1 — business purpose for Gear Five Luffy
- Dollar amounts typed by operator: 0
- Former $136.16 / -$1.99 artifact: not produced
- Final mixed-purchase landed-cost allocation: `POLICY_REQUIRED`

If Gear Five Luffy is classified Personal/nonbusiness or Business noninventory, DEX records that operator-provided business reality but does not invent the excluded amount or finalize inventory basis. Acquisition confirmation remains blocked pending an approved shared-component policy.

## Test and performance gate

The checkpoint includes coverage for the canonical mixed receipt, an all-inventory receipt, personal/nonbusiness classification, line-item and purchase-level discounts, explicit transaction fees, tax, quantity-prefixed products, low contrast, mild rotation, OCR failure/manual fallback, duplicate upload, existing text-layer PDF behavior, and unreconciled arithmetic.

Measured locally with Tesseract 5.5.0 on a generated low-contrast 1.5-degree receipt image:

- preprocessing: 57–63 ms
- OCR: 235–260 ms
- structured parsing: about 4 ms
- catalog matching/reconciliation: about 1 ms
- total receipt-to-review: about 306–332 ms
- OCR attempts: 1

Performance varies with image size, CPU, and whether bounded orientation retries are needed. Correctness gates remain ahead of latency.

## Known limitations and operator trial

- Handwriting and badly damaged receipts remain manual-fallback cases.
- Image PDFs without a text layer are not newly OCRed in v1; existing text-layer PDF behavior is preserved.
- Perspective cleanup is limited to safe grayscale/contrast/sharpen/rotation preparation; no aggressive geometry transform was introduced.
- Merchant layouts with more than 12 ambiguous printed components may not receive exhaustive subset analysis and will fall back safely.
- Exact product auto-preparation requires an exact normalized catalog name or identifier. Fuzzy text never establishes authority.
- Mixed-purchase allocation remains deliberately blocked until treatment of tax, card fees, shipping/freight, purchase-level discounts/credits, and exact-cent remainders is approved.
- Docker metadata intentionally retains the HF2 development baseline label because this is not yet a release artifact. Any later approved release must receive a fresh immutable tag and package.

Recommended trial scope: use disposable data to test (1) the real Mom and Pop receipt photo through the expected `POLICY_REQUIRED` stop, (2) one clean all-inventory receipt using established v1 allocation, (3) one low-contrast or mildly rotated phone photo, (4) one receipt with an unknown catalog item, and (5) one OCR failure followed by HF2 manual entry.

## Rollback

Discard this isolated directory and return to `DEX_v2.2-test_RC3_HF2_FULL_CHECKPOINT`. No production data or configuration was modified, and no schema migration exists to reverse.
