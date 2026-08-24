# Operator Deployment Instructions — SAM Multi-Evidence Operator Trial v1a

Image tag: `192.168.2.92:5000/apps/dex:v2.4-test-sam-multi-evidence-operator-trial-v1a`

1. Record the current WOLFF/SAM Phase 2 image tag/digest and verify the timestamped pre-cutover `/data` backup.
2. Open `DEX_v2.4-test_SAM_MULTI_EVIDENCE_OPERATOR_TRIAL_v1a_DEPLOY`.
3. Select everything **inside** it and upload those contents directly into the GitHub `dex-test` root. Do not upload the outer DEPLOY folder.
4. Commit and record the full GitHub commit SHA.
5. Verify that exact committed `dex-test` tree against the accepted `DEPLOY_SHA256SUMS.txt`. Require zero missing/mismatched files, including `app.py`, `Dockerfile`, `static/index.html`, `static/app.js`, and `static/styles.css`.
6. If any file differs, stop and correct the upload. Do not start Jenkins.
7. Run the existing Jenkins build and confirm the build, receipt smoke, frozen-component assertion, and registry push succeed under the new immutable tag.
8. In Portainer, update only the DEX image tag and update the existing stack. Keep mounts, environment, network, proxy, ports, and storage unchanged.
9. Verify `/api/health` is HTTP 200 and both API and sidebar show `v2.4-test-sam-multi-evidence-operator-trial-v1a`.
10. Verify Inventory, SAM, and WOLFF open. Process one unseen scan, confirm the result is suggestion-only, make one operator decision, and reopen it to verify the audit record persisted.
11. Compare deployed `/app/app.py`, `/app/static/index.html`, `/app/static/app.js`, and `/app/static/styles.css` hashes with the accepted DEPLOY ledger.

If startup fails, restore the exact prior image tag/digest first without deleting or restoring storage.
