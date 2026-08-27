# Operator Deployment Instructions — DEX v2.5.1-live

Use image tag `192.168.2.92:5000/apps/dex:v2.5.1-live`.

1. Confirm the current LIVE image/digest and a readable pre-cutover `/data` backup.
2. Open `DEX_v2.5.1-live_DEPLOY`, select everything inside it, and upload those contents directly into the GitHub `/dex/` root. Do not upload the outer DEPLOY folder.
3. Commit. Record the resulting GitHub commit SHA.
4. Verify that exact committed tree against the accepted `DEPLOY_SHA256SUMS.txt`; require zero missing or mismatched files, including `app.py`, `Dockerfile`, `static/index.html`, `static/app.js`, and `static/styles.css`.
5. Do not trigger Jenkins if verification fails. A backend/frontend version or hash mismatch is a deployment-integrity failure, not a browser-cache assumption.
6. Run the normal LIVE Jenkins build and confirm the immutable image is pushed.
7. In Portainer, change only the DEX image tag and update the existing stack. Preserve all LIVE mounts and storage.
8. Verify `/api/health` and the visible sidebar both show `v2.5.1-live`, then verify existing inventory and the SAM OP13-055 review path.
9. Compare deployed critical-file hashes with the accepted DEPLOY ledger.

Rollback by restoring `192.168.2.92:5000/apps/dex:v2.5-live` while leaving storage untouched.
