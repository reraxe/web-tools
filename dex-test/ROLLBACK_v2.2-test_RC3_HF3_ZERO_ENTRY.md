# Rollback — DEX v2.2-test RC3 HF3 Zero-Entry

Immediate rollback image: `192.168.2.92:5000/apps/dex:v2.2-test-rc3-hf2`.

HF3 adds no migration. If startup or operator validation fails:

1. Change only the DEX image tag back to HF2 in Portainer.
2. Update the stack.
3. Hard-refresh DEX and verify `/api/health` and existing inventory.

Preserve the database and storage. Do not delete, restore, or manually edit production data solely because application startup fails.
