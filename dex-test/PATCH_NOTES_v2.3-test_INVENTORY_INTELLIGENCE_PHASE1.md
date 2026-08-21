# DEX v2.3-test — Inventory Intelligence Phase 1

Development checkpoint only. Production deployment is not approved or performed.

## Added

- Deterministic receipt-line semantic taxonomy: Merchandise, Discount/Credit, Fee/Surcharge, Tax, Shipping, Subtotal, Total, Tender/Payment Method, Payment Summary, Informational Footer, Structural, and Unknown.
- Explicit suggestion states: High Confidence Suggestion, Unresolved, Conflicting, and Operator Confirmed.
- Additive migration 0016 for immutable semantic assertions and append-only decision events.
- Minimal receipt-review UI showing source text, signed amount, class, confidence, provenance, and matching eligibility, with Confirm, Change, and Mark Unresolved actions.
- Merchandise-only product-matching eligibility for newly processed receipts. Legacy extraction jobs without semantic assertions retain HF3 behavior.
- Synthetic Mom and Pop golden regression; no private receipt image or raw private fixture is included.

## Unchanged safety boundaries

- Semantic class is not business purpose, inventory truth, or accounting authority.
- Existing all-inventory receipt allocation remains `receipt-landed-allocation-v1`.
- Mixed inventory/noninventory remains `POLICY_REQUIRED`; no exclusion or shared-cost allocation is inferred.
- Economics, SAM, Challenger, catalog authority, and production configuration are unchanged.
