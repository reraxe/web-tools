# Migration Notes — Inventory Intelligence Phase 1 Remediation 3

No schema migration is added. The ordered migration ledger remains 0001–0016, ending with `0016_v23_inventory_intelligence_phase1_receipt_semantics`.

The safety decision is calculated from existing acquisition, receipt-intelligence, semantic-review, and receipt-math facts. No acquisition, receipt evidence, allocation, inventory fact, economics record, or migration marker is rewritten or backfilled merely by loading the candidate.

Rollback is application-only: stop the Remediation 3 candidate and return to the accepted Remediation 2 code/image while retaining the same compatible database. No database rollback is required.
