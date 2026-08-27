# DEX v2.5-test Development Checkpoint

Build identifier: `DEX-v2.5-test-tcgplayer-inventory-bootstrap-v1-20260824`  
Source baseline: accepted `DEX_v2.4-test_SAM_MULTI_EVIDENCE_OPERATOR_TRIAL_v1a_WORKTREE`  
Baseline DEPLOY ledger SHA-256: `dbdfc93b05221f79a8bd60a5a8d0537b742e114cda14fb9fb49c6efe89089de1`

This is a preserved isolated TEST worktree, not an immutable FULL/DEPLOY package and not a deployment authorization. The source v2.4 worktree remains unchanged.

## Scope

Migration 0020, immutable private CSV ingestion, quantity pools and events, marketplace observations, physical reconciliation, guarded Staged Inventory CSV generation, API/UI foundation, tests, migration notes, and official-contract research.

## Safety boundary

DEX owns physical truth. TCGplayer owns observed channel state. A source snapshot can bootstrap only once and only after explicit confirmation. Later snapshots do not mutate owned quantity. The operator remains responsible for reviewing and uploading generated CSVs through TCGplayer's Staged Inventory workflow.

## Private material

Real CSV exports are retained only under ignored `private-fixtures/` for local validation. They are excluded from source-control/release scope together with databases, images, receipts, scanner folders, caches, logs, secrets, and machine-specific configuration.

Aggregate validation of the latest private snapshot: source SHA-256 `ab4721cb6875a9faaacd4003a318ff3dacf3eb6cd55dd60a649cb50829440e56`; 3,358 source rows; 15,477 copies; 2,952 positive-quantity rows; 406 zero-quantity rows. One Piece produced 1,272 deterministic auto-import rows, 0 review rows, and 32 do-not-import rows lacking safe structured identity. Preview plus bootstrap completed against a disposable database in 851.39 ms with SQLite integrity `ok`.

## Verification

- Python: 338/338 passed.
- Frontend regression contracts: 28/28 passed against a disposable v2.5 server.
- JavaScript and Python syntax/import checks: passed.
- Runtime: `/api/health` returned `200` and `v2.5-test`.
- Empty startup: 0 TCGplayer pools, 0 TCGplayer owned copies, no export available.
- Private two-snapshot sequence: opening bootstrap followed by reconciliation, integrity `ok`.
- Frozen v2.4 baseline: source worktree and accepted deployment ledger preserved; no deletions from the candidate relative to baseline.

## Deployment status

`NOT PERFORMED` / `NOT APPROVED`
