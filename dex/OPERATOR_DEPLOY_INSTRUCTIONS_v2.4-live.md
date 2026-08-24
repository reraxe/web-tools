# Operator Deployment Instructions — v2.4-live

Status: package instructions only. Deployment requires a separate operator cutover action.

## Git/Jenkins

1. Open the final `DEX_v2.4-live_DEPLOY` folder, select everything inside it, and upload those contents directly into the GitHub `dex-test` root. Do not upload the outer DEPLOY folder.
2. Before Jenkins, compare the committed `app.py`, `static/index.html`, `static/app.js`, `static/styles.css`, `Dockerfile`, and every upload-manifest entry against `DEPLOY_SHA256SUMS.txt`. Require zero differences.
3. Run the established Jenkins build without bypassing Dockerfile checks. Tag/push the immutable result as `192.168.2.92:5000/apps/dex:v2.4-live`; record the registry digest. Do not overwrite accepted TEST tags.

## Portainer one-time LIVE storage

1. Leave the existing TEST container and storage untouched.
2. Create empty writable volumes `dex-live-data` and `dex-live-scanner-inbox`.
3. Use `dex-live-source-database` containing approved One Piece references, or mount the verified reference-only source volume read-only. Never point `/data` or `/scanner-inbox` at TEST storage.
4. Create a separate LIVE service/container on the existing `proxy` network with internal port `8080`, a distinct service/container name, and a distinct proxy route. Do not assume a host port mapping.
5. Mount `dex-live-data:/data` RW, `dex-live-scanner-inbox:/scanner-inbox` RW, and the approved reference source at `/source-database` (read-only where possible).
6. Set `DEX_DATA_DIR=/data`, `DEX_INBOUND_DIR=/scanner-inbox`, `DEX_SOURCE_DB_DIR=/source-database`, `DEX_ONE_PIECE_REFERENCE_DIR=/source-database`, `DEX_SEED_DEMO=0`, `DEX_WATCH_INBOUND=1`, `DEX_SCAN_INTERVAL=5`, and the established timezone/capacity values.
7. Deploy the immutable `v2.4-live` image by digest, then run the Day Zero checklist. Do not remove or repurpose TEST.

## Post-deploy integrity

Verify backend and visible UI both report `v2.4-live`; critical runtime hashes match the accepted DEPLOY ledger; SQLite integrity is `ok`; migrations are 0001–0019; all business/audit counts are zero before real use; One Piece references, SAM, and WOLFF are available. Treat any backend/frontend version mismatch as deployment-integrity failure, not browser cache.
