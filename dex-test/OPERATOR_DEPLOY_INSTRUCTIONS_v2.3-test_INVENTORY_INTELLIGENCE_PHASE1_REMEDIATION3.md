# Operator Deployment Instructions — Remediation 3

Release candidate: `DEX v2.3-test Inventory Intelligence Phase 1 Remediation 3`

Immutable image tag: `192.168.2.92:5000/apps/dex:v2.3-test-inventory-intelligence-phase1-remediation3`

Do not deploy unless `DEPLOY_VERIFICATION.md` reports `ACCEPT`.

1. Open `DEX_v2.3-test_INVENTORY_INTELLIGENCE_PHASE1_REMEDIATION3_DEPLOY`.
2. Select everything **inside** it and upload those contents directly into the GitHub `dex-test` root. Do not upload the outer DEPLOY folder.
3. Record the resulting GitHub commit SHA.
4. Obtain that exact commit in a disposable checkout/download and compare it with `DEPLOY_SHA256SUMS.txt`.
5. Require zero missing or mismatched files. At minimum verify `app.py`, `Dockerfile`, `static/index.html`, `static/app.js`, and `static/styles.css`.
6. Do not trigger Jenkins if any file differs.
7. In Jenkins, select **Build Now** only after the GitHub comparison passes.
8. Record the resulting immutable image digest when available.
9. In Portainer, update only the approved test service image to the immutable Remediation 3 tag and select **Update Stack**.
10. Verify `/api/health` and the visible sidebar both report `v2.3-test`.
11. Verify deployed hashes for `/app/app.py`, `/app/static/index.html`, `/app/static/app.js`, and `/app/static/styles.css` against the accepted ledger.

A backend/frontend version mismatch is a deployment-integrity failure. Do not assume browser cache without hash evidence.
