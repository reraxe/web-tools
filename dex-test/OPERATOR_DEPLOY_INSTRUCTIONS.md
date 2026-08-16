# Operator Deployment Instructions — RC3 Hotfix 2

Deployment has not been performed.

1. Verify the current HF1 storage backup and create a fresh timestamped backup.
2. Open `DEX_v2.2-test_RC3_HF2_DEPLOY`.
3. Select everything **inside** it and upload those contents directly into the GitHub `dex-test` root. Do not upload the outer DEPLOY folder.
4. Build the unique image tag `192.168.2.92:5000/apps/dex:v2.2-test-rc3-hf2` through the normal Jenkins workflow.
5. Confirm the build and registry push succeed.
6. In Portainer, update only the DEX image tag and update the stack.
7. Hard-refresh DEX and verify `/api/health`, runtime `v2.2-test`, migrations through 0015, existing inventory, and the preserved Mom and Pop Shop draft.

If startup fails, return the application image to `v2.2-test-rc3-hf1`. HF2 adds no schema migration, so an application-only rollback to HF1 is the preferred first action. Do not delete or edit production storage. RC3-r4 plus its matching pre-0015 backup remains the older rollback boundary.
