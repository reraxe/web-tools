# DEX v2.3-test Inventory Intelligence Phase 1 Remediation 4

Status: accepted packaging candidate; operator-controlled deployment only.

## Active semantic state

- Only the newest valid extraction generation for an attached receipt is active.
- Superseded extraction assertions remain immutable and inspectable as history, but cannot drive product matching, receipt math, allocation, or confirmation.
- Removing a source document moves all of its semantic assertions to history and removes them from current authority.
- Current and historical semantic counts are presented separately; the review count reflects current items requiring attention.

## Merchant freshness

- A newer active extraction may replace a stale extraction-sourced merchant suggestion.
- An operator-entered merchant remains authoritative and is never overwritten by extraction refresh.

## Preserved safety boundaries

Fantasy Bay unresolved receipt evidence remains `UNRECONCILED` and cannot create authoritative allocation. Valid reconciled one-product allocation remains available. Mixed inventory/noninventory purchases remain `POLICY_REQUIRED`. Receipt math, allocation formulas, accounting authority, SAM, economics, and inventory authority are unchanged.

The migration ledger remains 0001 through 0016. No migration 0017 is present.
