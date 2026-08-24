# DEPLOYMENT-INTEGRITY-001 — Partial or Stale GitHub Build Context

Status: process remediation documented; no runtime change and no automatic deployment.

## Incident

During the DEX v2.3-test Inventory Intelligence Phase 1 Remediation 1 deployment, `/api/health` reported `v2.3-test` while the visible sidebar reported `v2.2-test`. Browser source and GitHub both contained an older `static/index.html`; the accepted DEPLOY package contained the correct dynamic runtime-version implementation. Replacing GitHub `static/index.html` exposed `Checking version...`; replacing GitHub `static/app.js` with the accepted DEPLOY copy completed the correction. After rebuild and redeployment, backend and sidebar both reported `v2.3-test`.

## Evidence-based conclusion

Evidence supports an incomplete or stale GitHub upload/commit of frontend files. It does not establish a GitHub platform defect, a Git defect, or a browser-cache-only failure. The accepted DEPLOY package was not shown to be defective.

## Required prevention gate

Before Jenkins builds any future accepted release, the operator must record the GitHub commit SHA, obtain that exact commit in a disposable checkout/download, and verify it against the accepted DEPLOY `DEPLOY_SHA256SUMS.txt`. Verification must report zero missing or mismatched release files. At minimum it must cover:

- `app.py`
- `static/index.html`
- `static/app.js`
- `static/styles.css`
- `Dockerfile`

Jenkins must not run when the gate fails.

After deployment, the operator must compare `/api/health` with the visible sidebar, record the immutable image tag/digest where available, and verify deployed hashes for `app.py` plus the three static runtime files. `Dockerfile` is verified in the GitHub/build context and may not exist in `/app`. Any backend/frontend version mismatch is a deployment-integrity failure.
