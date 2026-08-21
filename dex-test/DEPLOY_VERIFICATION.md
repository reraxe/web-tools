# DEX v2.3-test Inventory Intelligence Phase 1 Remediation 1 — DEPLOY Verification

Status: ACCEPTED root-shaped development deploy candidate. Deployment was not performed.

- `app.py`, `Dockerfile`, `requirements.txt`, `VERSION`, every `dex_*.py` runtime sibling, `static/`, and `tests/` are directly at the expected DEPLOY root.
- There is no nested DEPLOY folder.
- Packaged runtime/source files match the frozen Remediation 1 workspace byte-for-byte; mismatch count: 0.
- Python regression from this DEPLOY root: 208/208 passed in 26.388 seconds.
- Frontend regressions: 19/19 passed; JavaScript syntax passed.
- Runtime imports and isolated startup passed.
- `/api/health`: HTTP 200; runtime `v2.3-test`.
- Fresh SQLite migration: 0001–0016; integrity `ok`; no migration 0017.
- Empty startup created zero acquisitions, batches, cards, sealed units, and sales.
- Package privacy, secret, credential, database, receipt-image, OCR-scratch, cache, and private-path checks passed with zero prohibited artifacts.

Suggested immutable image tag: `192.168.2.92:5000/apps/dex:v2.3-test-inventory-intelligence-phase1-remediation1`.

Open `DEX_v2.3-test_INVENTORY_INTELLIGENCE_PHASE1_REMEDIATION1_DEPLOY`, select everything inside it, and upload those contents directly into the GitHub `dex-test` root. Do not upload the outer DEPLOY folder.
