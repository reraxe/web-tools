# DEX v2.3-test Inventory Intelligence Phase 1 Remediation 2 — DEPLOY Verification

Status: ACCEPTED root-shaped deployment candidate. No upload or deployment was performed.

This DEPLOY directory is the exact GitHub-root upload payload. It contains `app.py`, `Dockerfile`, `requirements.txt`, `VERSION`, every `dex_*.py` runtime sibling, `static/`, and `tests/` directly at its root. There is no nested DEPLOY directory.

Runtime/source files match the frozen Remediation 2 workspace byte-for-byte; the accompanying `DEPLOY_SHA256SUMS.txt` is the file-level verification ledger. The ledger deliberately excludes itself and this verification document to avoid a self-referential checksum.

Acceptance evidence from this DEPLOY root:

- Python regression: 219/219 passed.
- Frontend regression: 20/20 passed; JavaScript syntax passed.
- Runtime imports and isolated startup passed.
- `/api/health` returned HTTP 200 and runtime identity `v2.3-test`.
- Fresh SQLite migration ledger contains exactly 0001 through 0016; integrity check returned `ok`; no migration 0017 exists.
- Empty startup created zero acquisitions, batches, cards, sealed units, and sale orders.
- Package privacy, secret, credential, database, receipt-image, OCR-scratch, cache, and private-path scans found zero prohibited artifacts.

Suggested immutable image tag: `192.168.2.92:5000/apps/dex:v2.3-test-inventory-intelligence-phase1-remediation2`.

Before a Jenkins build, complete the GitHub Build-Context Provenance Gate in `OPERATOR_DEPLOY_INSTRUCTIONS.md`: compare the five critical root files in GitHub with this DEPLOY ledger, record the commit SHA, and do not build on any mismatch.

