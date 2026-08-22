# Rollback — DEX v2.3-test Inventory Intelligence Phase 1 Remediation 3

Immediate rollback checkpoint: `DEX v2.3-test Inventory Intelligence Phase 1 Remediation 2`.

Rollback image tag: `192.168.2.92:5000/apps/dex:v2.3-test-inventory-intelligence-phase1-remediation2`.

Remediation 3 adds no schema migration. The ledger remains 0001–0016, so rollback is application-only:

1. Leave production/test storage unchanged.
2. In Portainer, restore the prior immutable Remediation 2 image tag.
3. Update the stack.
4. Verify `/api/health`, the visible UI version, inventory loading, and deployed hashes.

Do not delete, restore, or manually edit SQLite storage merely because application startup fails.
