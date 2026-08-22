# Remediation 4 DEPLOY Verification

Result: **ACCEPT**

This folder is root-shaped: `app.py`, `Dockerfile`, runtime modules, `static/`, migrations, tests, and required documentation are directly at its root. It contains no nested DEPLOY package.

Final acceptance was run from this folder:

- 229/229 Python tests passed.
- 23/23 frontend tests passed; JavaScript syntax passed.
- Runtime imports passed.
- Isolated `/api/health` returned HTTP 200 and `v2.3-test`.
- Migrations 0001–0016 were present and ordered; no 0017; SQLite integrity was `ok`.
- Fantasy Bay active-state, one-review-item, merchant freshness, superseded-history isolation, Remediation 3 allocation safety, valid single-product allocation, and Mom and Pop `POLICY_REQUIRED` gates passed.
- Remediation 3 → 4 diff contained seven explained paths and no unexplained drift.
- Prohibited/private-artifact, secret, machine-path, and package-integrity scans passed.

Use `DEPLOY_SHA256SUMS.txt` to verify the upload and deployed runtime. No deployment was performed during packaging.

Known metadata note: the frozen Dockerfile's OCI version label still names Remediation 3. This was preserved under the exact-freeze instruction. The operator must use the new immutable Remediation 4 image tag recorded in `OPERATOR_DEPLOY_INSTRUCTIONS.md`; runtime identity remains `v2.3-test`.
