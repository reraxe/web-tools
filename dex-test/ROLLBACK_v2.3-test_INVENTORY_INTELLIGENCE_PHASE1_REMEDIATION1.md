# Rollback — DEX v2.3-test Inventory Intelligence Phase 1 Remediation 1

Immediate known-good application rollback: `DEX_v2.2-test_RC3_HF3_ZERO_ENTRY`.

Restore the prior immutable HF3 application image/package through the normal Jenkins and Portainer workflow. Preserve storage. Do not delete databases or manually remove migration records. Migration 0016 is additive and may remain unused when HF3 application code is restored.
