# Operator deployment — DEX v2.4-test WOLFF + SAM Phase 2

Use image tag:

`192.168.2.92:5000/apps/dex:v2.4-test-wolff-sam-phase2-20260822`

## Before Jenkins

1. Record the currently running image tag and digest. This is the immediate rollback image.
2. Verify the current DEX data/storage backup and record its timestamp and integrity result. Stop if the backup is missing or unverified.
3. Open `DEX_v2.4-test_WOLFF_SAM_PHASE2_20260822_DEPLOY`.
4. Select everything **inside** it and upload those contents directly into the GitHub `dex-test` root. Do not upload the outer DEPLOY folder.
5. Record the GitHub commit SHA.
6. Download that exact commit to a disposable location and compare it with `DEPLOY_SHA256SUMS.txt`.
7. Require zero missing or mismatched files, especially `app.py`, `Dockerfile`, `static/index.html`, `static/app.js`, and `static/styles.css`. Stop if any file differs.

## Build and cutover

8. In Jenkins, select **Build Now**.
9. Require the Dockerfile's import checks, Tesseract check, complete receipt-orchestration smoke, and health smoke to pass.
10. Confirm the immutable registry tag above exists and record its digest. The checked-in Jenkinsfile alone does not show a registry push; stop if the normal deployment workflow did not publish this exact tag.
11. In Portainer, change only the DEX service image to the immutable tag above.
12. Select **Update Stack**. Keep the existing ports, volumes, container name, and environment unchanged.

## After startup

13. Verify `/api/health` returns HTTP 200 and `v2.4-test`.
14. Verify the visible sidebar also reports `v2.4-test`.
15. Verify existing inventory, acquisitions, source documents, SAM review, and WOLFF Economics load normally.
16. Compare deployed `/app/app.py`, `/app/static/index.html`, `/app/static/app.js`, and `/app/static/styles.css` with the accepted DEPLOY ledger.
17. Verify the live database reports SQLite integrity `ok`, then record the image digest, health result, deployed hashes, and backup reference.

## Rollback

1. If startup or health fails, change Portainer back to the exact pre-cutover image tag/digest and update the stack. Do not delete or restore storage merely because startup failed.
2. Recheck `/api/health` and the UI version.
3. Restore the pre-cutover storage backup only for a verified data-level problem, after separate operator approval. Move the current storage aside first so it remains recoverable. Do not manually delete migrations or authoritative records.
