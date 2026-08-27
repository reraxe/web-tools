# Operator Deployment Instructions — SAM Multi-Evidence Operator Trial v1a

Use image tag `192.168.2.92:5000/apps/dex:v2.4-test-sam-multi-evidence-operator-trial-v1a`.

1. Record the current WOLFF/SAM Phase 2 image tag/digest and verify the pre-cutover `/data` backup.
2. Open `DEX_v2.4-test_SAM_MULTI_EVIDENCE_OPERATOR_TRIAL_v1a_DEPLOY`, select everything inside it, and upload those contents directly into the GitHub `dex-test` root. Do not upload the outer DEPLOY folder.
3. Commit. Record the resulting GitHub commit SHA.
4. Verify that exact committed tree against the accepted `DEPLOY_SHA256SUMS.txt`; require zero missing or mismatched files, including `app.py`, `Dockerfile`, `static/index.html`, `static/app.js`, and `static/styles.css`.
5. Do not trigger Jenkins if verification fails. An API/sidebar or backend/frontend hash mismatch is a deployment-integrity failure, not a browser-cache assumption.
6. Run the existing Jenkins build and confirm the new immutable image is pushed.
7. In Portainer, change only the DEX image tag and update the existing stack.
8. Verify `/api/health` and the sidebar show `v2.4-test-sam-multi-evidence-operator-trial-v1a`; Inventory, SAM, and WOLFF open; and one unseen scan remains suggestion-only until the operator confirms/corrects it.
9. Compare deployed hashes for `/app/app.py`, `/app/static/index.html`, `/app/static/app.js`, and `/app/static/styles.css` with the accepted DEPLOY ledger.

Rollback by restoring the exact recorded pre-cutover image tag/digest while leaving storage untouched. Never delete migration rows or audited recognition history.
