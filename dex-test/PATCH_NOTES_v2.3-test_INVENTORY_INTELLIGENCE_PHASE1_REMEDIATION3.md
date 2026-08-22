# DEX v2.3-test Inventory Intelligence Phase 1 Remediation 3

Status: implementation and verification candidate; not packaged and not approved for deployment.

## Fix

- Adds a backend-owned eligibility decision for automatic one-product allocation.
- Blocks the automatic 100% preview and confirmation mutation when receipt arithmetic is not exactly reconciled, amount-bearing receipt semantics remain unresolved, financial evidence conflicts, or mixed-purchase allocation is `POLICY_REQUIRED`.
- Replaces the unsafe browser promise with a visible warning: **Automatic allocation is not ready. Resolve receipt financial discrepancies first.**
- Keeps valid reconciled one-product receipts, explicit manual fallback, and no-receipt manual acquisitions on their established automatic path.

## Receipt upload UX follow-up

- Keeps the separate camera, multi-file upload, and failed-upload retry inputs, but marks them as hidden implementation controls instead of exposing native file choosers beside the styled actions.
- Routes the keyboard-operable **Take Photo** and **Upload** buttons through the established attachment and extraction workflow.
- Clears picker state before opening and immediately after selection so cancellation is inert and later selections—including the same filename—cannot be lost to stale native-input state.
- Preserves supported file types, attachment de-duplication, extraction, View, removal/tombstone history, SHA-256 verification, and provenance behavior.

## Preserved boundaries

`receipt-landed-allocation-v1`, mixed-purchase `POLICY_REQUIRED`, tax/fee treatment, exact-cent formulas, acquisition authority, SAM, Challenger, inventory authority, marketplace behavior, and existing receipt semantic classifications are unchanged. The migration ledger remains 0001–0016; no migration 0017 is added.
