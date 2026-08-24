# v2.4-live Disposable Validation Report

Date: 2026-08-24  
Build identifier: `DEX-v2.4-live-promotion-20260824`  
Production deployment: not performed

## Regression

- Python: 326/326 passed.
- Audited SAM focused integration: 23/23 passed within the Python suite.
- Frontend: 28/28 passed against the required disposable Phase 4/6 renderer fixture.
- JavaScript syntax: passed.

## Clean Day Zero startup

A new isolated database and separate writable scanner folder were used with demo seeding disabled. Results:

- `/api/health`: HTTP 200, `v2.4-live`.
- Migrations: 0001–0019, ordered.
- SQLite integrity: `ok`.
- Foreign-key violations: 0.
- Inventory/cards/sealed units: 0.
- Acquisitions: 0.
- Batches: 0.
- Receipts/documents: 0.
- Sales: 0.
- SAM operational jobs/results/decisions/truth/deltas: 0.
- WOLFF operational history: 0.
- SAM frozen component status: available.
- WOLFF calculation service: available (`jarvis-simplified-economics-v1`).
- Frozen One Piece family catalog: 2,838 families, descriptive/non-authoritative.

## Disposable audited-SAM flow

A generated synthetic source scan with a new SHA-256 distinct from its generated reference was processed through the unchanged frozen worker. It produced a five-candidate suggestion for `OP16-034` while leaving card identity and exact printing empty. Explicit confirmation wrote family identity while preserving the original result hash. A separate generated case was explicitly corrected from original suggestion `OP16-034` to operator-selected `OP16-035`; the original suggestion/hash remained immutable and exact printing remained empty.

No private scan, benchmark truth, external reference asset, database, or generated validation output is included in the release package.

## Recognizer parity

All 25 frozen component hashes and accepted fingerprint `dd899b6f73891252395ae9b8d09b43906ad15c656f0a0c739bd15a916c012493` match. Recognizer changes: none. Accepted frozen evidence remains top family 34/40, candidate inclusion 35/40, and false-authority increase 0.

## Docker boundary

The Dockerfile retains Tesseract installation/runtime checks, all runtime modules, frozen component import/hash checks, and the existing complete receipt-orchestration smoke. Docker is unavailable on this packaging workstation; the actual Docker build remains the required Jenkins-host pre-deployment gate.
