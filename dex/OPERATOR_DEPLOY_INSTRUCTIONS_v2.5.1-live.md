# Operator Deployment Instructions — DEX v2.5.1-live

Target image: `192.168.2.92:5000/apps/dex:v2.5.1-live`

1. Open `DEX_v2.5.1-live_DEPLOY` and upload everything **inside** it directly into the GitHub `/dex/` root. Do not upload the outer DEPLOY folder.
2. Commit the complete replacement and record the full GitHub commit SHA.
3. Verify that exact commit against the accepted `DEPLOY_SHA256SUMS.txt`. Stop unless every ledger file is present and matching, especially `app.py`, `Dockerfile`, `static/index.html`, `static/app.js`, and `static/styles.css`.
4. Confirm a current LIVE `/data` backup exists. Do not reset or replace LIVE storage.
5. Run the normal LIVE Jenkins build for the immutable `v2.5.1-live` image.
6. Confirm the registry contains `192.168.2.92:5000/apps/dex:v2.5.1-live` and record its digest.
7. In Portainer, change only the DEX image to the new immutable tag and update the stack.
8. Verify `/api/health` and the visible sidebar both report `v2.5.1-live`.
9. Verify existing inventory loads and compare deployed critical-file hashes with the accepted DEPLOY ledger.

If startup or verification fails, restore the prior `v2.5-live` image. Preserve LIVE storage.

