# Operator Deployment Instructions — Separate Approval Required

Candidate: `DEX v2.3-test Inventory Intelligence Phase 1 Remediation 4`.

Immutable image tag: `192.168.2.92:5000/apps/dex:v2.3-test-inventory-intelligence-phase1-remediation4`.

1. Preserve the currently running Remediation 3 image/tag as the rollback point, then open the accepted `DEX_v2.3-test_INVENTORY_INTELLIGENCE_PHASE1_REMEDIATION4_DEPLOY` package.
2. Select everything inside it and upload those contents directly into the GitHub `dex-test` root. Do not upload the outer DEPLOY folder.
3. Record the resulting GitHub commit SHA.
4. Obtain that exact commit in a disposable checkout or download.
5. Compare it with the accepted DEPLOY package using the accepted `DEPLOY_SHA256SUMS.txt` ledger. Require zero missing or mismatched release files. At minimum verify `app.py`, `static/index.html`, `static/app.js`, `static/styles.css`, and `Dockerfile`.
6. **Stop. Do not trigger Jenkins if any file is missing or different.** Correct the GitHub upload and repeat the comparison.
7. Confirm the immutable image tag above.
8. Use the normal Jenkins **Build Now** action.
9. Confirm the build and registry push succeed, and record the immutable image tag and image digest where available.
10. Update the Portainer stack to the new immutable image tag.
11. Update the stack and verify `/api/health` reports `v2.3-test`.
12. Verify the visible sidebar also reports `v2.3-test`.
13. Compare deployed runtime hashes for `/app/app.py`, `/app/static/index.html`, `/app/static/app.js`, and `/app/static/styles.css` with the accepted DEPLOY ledger. Verify existing inventory and Inbound data load and receipt review shows current versus historical assertions correctly.

`Dockerfile` is a GitHub/build-context verification item and may not exist inside `/app` at runtime. A backend/frontend version mismatch is a **deployment-integrity failure**; do not initially dismiss it as browser cache.

If verification fails, redeploy the preserved Remediation 3 image. Do not delete or restore production storage.

Known metadata note: the frozen Dockerfile's OCI version label still names Remediation 3. Use the exact immutable Remediation 4 image tag above and record its digest; runtime identity remains `v2.3-test`.

No deployment was performed while creating this package.
