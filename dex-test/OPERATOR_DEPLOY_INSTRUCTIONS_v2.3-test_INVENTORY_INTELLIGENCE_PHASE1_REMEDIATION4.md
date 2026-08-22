# Operator Deployment Instructions — Remediation 4

No deployment has been performed by JARVIS.

Immutable image tag: `192.168.2.92:5000/apps/dex:v2.3-test-inventory-intelligence-phase1-remediation4`.

1. Preserve the currently running image/tag as the Remediation 3 rollback point.
2. Open `DEX_v2.3-test_INVENTORY_INTELLIGENCE_PHASE1_REMEDIATION4_DEPLOY`, select everything **inside** it, and upload those contents directly into the GitHub `dex-test` root. Do not upload the outer DEPLOY folder.
3. Before Jenkins, compare GitHub SHA-256 values with `DEPLOY_SHA256SUMS.txt`. At minimum verify `app.py`, `Dockerfile`, `static/index.html`, `static/app.js`, and `static/styles.css`. Stop if any differ.
4. Commit the complete root replacement. Trigger the normal Jenkins/Docker build only after the hash check passes.
5. Build and push the exact immutable Remediation 4 image tag above; do not overwrite the Remediation 3 rollback tag. Record the resulting digest.
6. After deployment, verify `/api/health` reports `v2.3-test`, the sidebar reports `v2.3-test`, the five critical deployed-file hashes match, existing inventory and Inbound data load, and receipt review shows current versus historical assertions correctly.
7. If startup or verification fails, redeploy the preserved Remediation 3 image. Do not delete or restore production storage.
