# Operator Deployment Instructions — RC3 Hotfix 1

Deployment has not been performed.

1. Create and verify a timestamped backup of the live DEX storage.
2. Open `DEX_v2.2-test_RC3_HF1_DEPLOY`.
3. Copy its contents into the GitHub `dex-test` root.
4. Build the unique image tag `192.168.2.92:5000/apps/dex:v2.2-test-rc3-hf1` through the normal Jenkins workflow.
5. Confirm the build and registry push succeed.
6. In Portainer, update only the DEX image tag and update the stack.
7. Hard-refresh DEX and verify `/api/health`, runtime `v2.2-test`, migration 0015, existing inventory, and the preserved Mom and Pop Shop draft.

If startup fails, return the application to RC3-r4. Do not delete or edit production storage. Use the matching pre-0015 backup only if a database rollback is explicitly required.
