# DEX v2.2-test RC3 HF3 — Zero-Entry Receipt Intelligence v1

Status: operator-trial release candidate; no automatic deployment.

## Added

- Private local JPG/JPEG/PNG receipt OCR through Tesseract.
- Existing text-layer PDF extraction retained.
- Structured merchant, date, payment, product, quantity, component, subtotal, tax, and final-paid extraction with provenance.
- Exact receipt-arithmetic analysis that distinguishes included components from amounts outside the printed subtotal.
- Exact catalog matching and draft acquisition-line preparation; fuzzy matches remain suggestions.
- Receipt-first acquisition review and minimal business-purpose questions.
- Low-contrast and mild-rotation preprocessing using disposable derived images; originals remain immutable.

## Accounting boundary

- All-inventory receipts retain `RECEIPT_VALUE_PROPORTIONAL` / `receipt-landed-allocation-v1` unchanged where valid.
- Mixed inventory/noninventory receipts stop at `POLICY_REQUIRED`.
- DEX does not infer `excluded_noninventory_cents`, collapse shared components into a net allocation assumption, or automatically confirm a mixed purchase.
- Sales tax, transaction/card fees, shipping/freight, purchase-level discounts/credits, and exact-cent remainder treatment remain separately preserved pending policy approval.
- Acquisition confirmation remains the authoritative boundary.

## Compatibility

- HF2 manual fallback remains available.
- No migration 0016; migrations remain 0001–0015.
- No SAM, JANA, economics, inventory-identity, deployment-workflow, port, volume, or production-storage changes.
- Runtime family remains `v2.2-test`; immutable image tag is `192.168.2.92:5000/apps/dex:v2.2-test-rc3-hf3`.

HF2 is the immediate rollback release.
