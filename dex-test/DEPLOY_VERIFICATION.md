# DEX v2.3-test Inventory Intelligence Phase 1 Remediation 3 — DEPLOY Verification

Status: **ACCEPT**. Root-shaped deployment candidate verified. No upload or deployment was performed.

This directory is the root-shaped GitHub upload payload. `app.py`, `Dockerfile`, `requirements.txt`, every required `dex_*.py` runtime sibling, `static/`, and `tests/` are directly at this root. There is no nested DEPLOY directory.

All source/runtime files were copied from the frozen Remediation 3 worktree and match it byte-for-byte. The worktree was frozen at 230 files; SHA-256 of its frozen ledger is `a2ba941d8f3ab362531c76a83ffc0a03f16cec57280f6ea04e059a681a9f110a`.

Acceptance evidence run from this DEPLOY root:

- Python regression: 224/224 passed.
- Frontend regression: 22/22 passed; JavaScript syntax passed.
- Explicit Fantasy Bay, valid reconciled single-product, manual single-product, mixed-purchase `POLICY_REQUIRED`, read-only allocation, and Mom and Pop tests: 6/6 passed.
- Fantasy Bay retained `OP deck $16.00` as merchandise, left the corrupted `$0.53` unresolved, remained `UNRECONCILED`, exposed no automatic allocation, rejected confirmation, and wrote zero basis/allocation events.
- The valid reconciled `$16.00 + $0.53 tax = $16.53` case retained the established 100% one-product allocation path.
- Receipt upload UX exposed only **Take Photo** and **Upload**; selection immediately used the established upload/extraction path; cancellation, repeated selection, de-duplication, camera, View, and Remove passed.
- Runtime sibling imports passed. `/api/health` returned HTTP 200 with `v2.3-test`.
- SQLite contained ordered migrations 0001–0016, no 0017, and integrity `ok`.
- `DEPLOY_SHA256SUMS.txt` verified with zero mismatches. It excludes itself and this verification document to avoid self-reference.
- Privacy/prohibited-artifact, credential, machine-path, cache, database, and nested-package scans returned zero findings.
- Remediation 2 → Remediation 3: 9 explained modified files, 6 explained additive files, and 0 removals; no unexplained drift.

Suggested immutable image tag: `192.168.2.92:5000/apps/dex:v2.3-test-inventory-intelligence-phase1-remediation3`.

This package is accepted for the operator-controlled deployment workflow. Deployment remains a separate operator action.
