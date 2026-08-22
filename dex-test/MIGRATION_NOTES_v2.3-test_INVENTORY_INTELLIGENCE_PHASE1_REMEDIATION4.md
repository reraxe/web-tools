# Migration Notes — Remediation 4

Remediation 4 adds no database migration and makes no schema change.

- Required migration ledger: ordered migrations 0001–0016.
- Latest migration: `0016_v23_inventory_intelligence_phase1_receipt_semantics`.
- Migration 0017 must not exist.
- Startup applies only any already-approved missing migrations through 0016 using the existing transactional migration runner.
- Existing acquisition, receipt, allocation, inventory, sale, and economics facts are not backfilled or rewritten by this remediation.

Rollback is application-code rollback to the accepted Remediation 3 package/image. Do not delete, replace, or restore production storage merely because application startup fails.
