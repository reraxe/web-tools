# Operator Deployment Instructions — DEX v2.5-live

Status: package handoff only. Do not deploy until package acceptance is `SAFE_TO_BUILD_LIVE_JENKINS = YES` and a verified LIVE `/data` backup exists.

1. Open `DEX_v2.5-live_DEPLOY`.
2. Select everything **inside** it and upload those contents directly into the GitHub `/dex/` root. Do not upload the outer DEPLOY folder.
3. Commit the complete root replacement and record the full GitHub commit SHA.
4. Download or check out that exact commit and compare it with the accepted `DEPLOY_SHA256SUMS.txt`. Require every ledger entry present and matching, especially `app.py`, `Dockerfile`, `static/index.html`, `static/app.js`, and `static/styles.css`.
5. Stop if any file is missing or mismatched. Do not start Jenkins.
6. Confirm the target image is `192.168.2.92:5000/apps/dex:v2.5-live`.
7. Confirm the existing LIVE persistent `/data` backup and rollback image tag/digest.
8. Run the normal LIVE Jenkins build. Record the resulting registry digest.
9. Before cutover, verify the built image reports `v2.5-live` using disposable storage.
10. In Portainer, update only the LIVE image to the immutable v2.5-live tag/digest. Do not replace or reset LIVE storage or mounts.
11. Update the stack.
12. Verify `/api/health`, the visible sidebar version, migration 0020, existing inventory counts, SQLite integrity, and the deployed critical-file hashes.

