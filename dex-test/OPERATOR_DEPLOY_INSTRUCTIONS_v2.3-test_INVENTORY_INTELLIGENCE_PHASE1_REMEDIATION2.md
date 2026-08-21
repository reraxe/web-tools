# Operator Deployment Instructions — v2.3-test Inventory Intelligence Phase 1 Remediation 2

1. Open `DEX_v2.3-test_INVENTORY_INTELLIGENCE_PHASE1_REMEDIATION2_DEPLOY`, select everything inside it, and upload those contents directly into the GitHub `dex-test` root. Do not upload the outer DEPLOY folder.
2. Before Jenkins, compare GitHub SHA-256 values to `DEPLOY_SHA256SUMS.txt` for `app.py`, `static/index.html`, `static/app.js`, `static/styles.css`, and `Dockerfile`. Record the resulting GitHub commit SHA. Do not trigger Jenkins if any file differs.
3. Use the normal operator-controlled build with image tag `192.168.2.92:5000/apps/dex:v2.3-test-inventory-intelligence-phase1-remediation2`. This package does not authorize a deployment by itself.
4. After deployment, verify `/api/health` returns HTTP 200 and `v2.3-test`; verify the visible sidebar/runtime version also says `v2.3-test`; then compare the same five deployed `/app` hashes to this DEPLOY ledger.
5. Treat any backend/frontend version or hash mismatch as a deployment-integrity failure. Stop and preserve the evidence; do not assume browser caching.
6. If startup or validation fails, roll back application code to the immutable Remediation 1 package. Preserve storage and the migration ledger.

