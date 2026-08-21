# Rollback — DEX v2.3-test Inventory Intelligence Phase 1 Remediation 2

Immediate known-good rollback: `DEX_v2.3-test_INVENTORY_INTELLIGENCE_PHASE1_REMEDIATION1_DEPLOY`.

If the candidate fails startup or operator validation, restore the prior immutable Remediation 1 application image/package through the normal operator-controlled Jenkins and Portainer workflow. Preserve storage. Do not delete databases, restore storage, or manually remove migration ledger records. Migration 0016 is additive and remains compatible with the Remediation 1 application.

If the issue is a GitHub build-context mismatch, stop before Jenkins, correct the GitHub root to match the accepted package ledger, and repeat the provenance gate. Do not treat it as a browser-cache issue until backend/UI version and deployed critical-file hashes agree.

