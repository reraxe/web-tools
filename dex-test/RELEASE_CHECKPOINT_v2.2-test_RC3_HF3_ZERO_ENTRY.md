# DEX v2.2-test RC3 HF3 — Zero-Entry Receipt Intelligence v1

Release status: **operator-trial candidate; not automatically deployed**.

## Scope

HF3 preserves the complete RC3 HF2 application and adds local receipt-image OCR, structured receipt parsing, exact receipt arithmetic, catalog-assisted product preparation, and a receipt-first review experience. Original receipt artifacts remain private and immutable; derived OCR images are temporary; raw OCR text is not stored or exposed.

The canonical Mom and Pop specimen extracts four product lines, the printed discount, card fee, subtotal, tax, and final paid without manual dollar entry. Receipt arithmetic is `RECONCILED_EXACT`, and the old `$136.16 / -$1.99` double-counting artifact is not produced.

## Accounting safety

- All-inventory receipts may use existing `receipt-landed-allocation-v1` and reach acquisition confirmation.
- Once an item is classified noninventory, the acquisition changes to `POLICY_REQUIRED`.
- No excluded amount is inferred and mixed-purchase confirmation remains blocked.
- Shared components remain separate pending policy approval.
- HF2 manual fallback and text-layer PDF handling remain available.

## Runtime and migration

- Runtime identity: `v2.2-test`
- Release identifier: `v2.2-test-rc3-hf3`
- Image tag: `192.168.2.92:5000/apps/dex:v2.2-test-rc3-hf3`
- Migrations: 0001–0015; no 0016
- Rollback: RC3 HF2

## Verification gate

Packaging requires the full Python suite, JavaScript syntax, all frontend regression suites, runtime import checks, isolated `/api/health`, migration ordering, empty-startup fact checks, SHA-256 workspace/package equality, and prohibited/private-artifact scans.

Production deployment and mixed-purchase accounting-policy approval are outside this release package.
