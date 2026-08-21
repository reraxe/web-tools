# Operator Deployment Instructions — RC3 HF3 Zero-Entry

Deployment has not been performed.

1. Verify the current HF2 storage backup and create a fresh timestamped backup.
2. Open `DEX_v2.2-test_RC3_HF3_ZERO_ENTRY_DEPLOY`.
3. Select everything **inside** it and upload those contents directly into the GitHub `dex-test` root. Do not upload the outer DEPLOY folder.
4. Build the unique image tag `192.168.2.92:5000/apps/dex:v2.2-test-rc3-hf3` through the normal Jenkins workflow.
5. Confirm the build and registry push succeed.
6. In Portainer, update only the DEX image tag and update the stack.
7. Hard-refresh DEX and verify `/api/health`, runtime `v2.2-test`, migrations through 0015, existing inventory, local receipt-image extraction, all-inventory confirmation, and the mixed-purchase `POLICY_REQUIRED` boundary.

If startup fails, return the application image to `v2.2-test-rc3-hf2`. HF3 adds no schema migration, so application-only rollback is the preferred first action. Do not delete or edit production storage.
