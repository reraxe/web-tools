# Operator Deployment Instructions — DEX v2.4-test

Candidate: `DEX-v2.4-test-WOLFF-SAM-Phase2-development-baseline-20260822`.

Immutable image tag: `192.168.2.92:5000/apps/dex:v2.4-test-wolff-sam-phase2-20260822`.

1. Record the currently running image tag and digest and verify a current data/storage backup.
2. Open `DEX_v2.4-test_WOLFF_SAM_PHASE2_20260822_DEPLOY`.
3. Select everything inside it and upload those contents directly into the GitHub `dex-test` root. Do not upload the outer DEPLOY folder.
4. Record the resulting GitHub commit SHA.
5. Obtain that exact commit in a disposable checkout or download.
6. Compare it with the accepted package using `DEPLOY_SHA256SUMS.txt`. Require zero missing or mismatched files. At minimum verify `app.py`, `static/index.html`, `static/app.js`, `static/styles.css`, and `Dockerfile`.
7. **Do not trigger Jenkins if any file is missing or different.** Correct the upload and repeat the comparison.
8. In Jenkins, select **Build Now**.
9. Require every Dockerfile import check, Tesseract check, complete receipt-orchestration smoke, and health smoke to pass.
10. Confirm the immutable registry tag above exists and record its digest. The checked-in Jenkinsfile does not itself show a registry push, so stop if the normal workflow did not publish the exact tag.
11. In Portainer, change only the DEX service image to the immutable tag and update the stack. Keep existing ports, volumes, container name, environment, and storage unchanged.
12. Verify `/api/health` returns HTTP 200 and `v2.4-test`; verify the visible sidebar also reports `v2.4-test`.
13. Compare deployed hashes for `/app/app.py`, `/app/static/index.html`, `/app/static/app.js`, and `/app/static/styles.css` with the accepted ledger.
14. Verify existing inventory and SQLite integrity, then record the build commit, image digest, health result, deployed hashes, and backup reference.

`Dockerfile` is a pre-build GitHub/build-context verification item and may not exist in `/app`. A backend/frontend version mismatch is a **deployment-integrity failure**, not a browser-cache assumption.

Rollback first by restoring the exact pre-cutover image tag/digest while leaving storage untouched. Restore storage only for a verified data-level problem after separate operator approval; preserve the current storage first and never manually delete migrations or authoritative records.

No production deployment was performed while preparing this package.
