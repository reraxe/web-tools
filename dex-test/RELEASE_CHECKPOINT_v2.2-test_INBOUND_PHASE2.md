# DEX v2.2-test Inbound 2.0 Phase 2 Git-ready Checkpoint

Scope: Guided Manual Acquisition Wizard only. The accepted Phase 1 Git-ready checkpoint remains the known-good v2.2 restore point. Phase 3 UPC/catalog, production deployment, and server-side actions are not authorized.

## Runtime and behavior

- Runtime version remains `v2.2-test`; economics calculation version remains `acquisition-rip-v3`.
- New Acquisition is the primary inbound entry. Advanced / Legacy New Batch remains accessible and retains its Phase 3–7C behavior.
- A draft receives an immutable acquisition ID/code immediately.
- Draft product/source/economics/reconciliation facts and wizard position autosave without becoming authoritative.
- Missing final cost is Unknown / Setup incomplete. Intentional `$0.00` requires `EXPLICIT_ZERO_COST`.
- Ready confirmation requires complete product facts, confirmed independent line costs, exact line-total-to-final-USD reconciliation, and explicit authoritative/reconciliation confirmations.
- Material differences use `$5 OR 2%`; 50%+ adds a severe confirmation gate.
- Ready means `READY_FOR_INTAKE` only. No batches, cards, basis, sealed units, UPC data, documents, extraction, or SAM facts are created.

## Schema and migration

Migration `0007_v22_phase2_manual_acquisition_wizard` adds only:

- `acquisitions.wizard_step TEXT NOT NULL DEFAULT 'ACQUIRE'`
- allowed steps: `ACQUIRE`, `PRODUCTS`, `SOURCE`, `ECONOMICS`, `RECONCILIATION`, `REVIEW`

It runs in the existing migration savepoint with its ledger marker. A failure rolls back both the column change and marker where SQLite permits. It does not update legacy inventory/economics rows.

## API additions/changes

- Existing `PATCH /api/acquisitions/{id}` accepts validated `wizard_step` progress.
- `POST /api/acquisition-lines/{id}/cancel` removes a draft line from active setup while retaining its row and lifecycle event.
- Acquisition detail adds backend-generated readiness warnings and deterministic per-unit cost information.
- The foundation contract identifies Phase 2 screens and boundaries.

## Verification

- 101 Python tests passed: all 94 accepted Phase 1 checkpoint tests plus seven Phase 2 migration/service tests.
- JavaScript syntax passed.
- Direct Phase 2 browser-contract test passed for branching, autosave serialization, resume/focus semantics, logical viewport hooks, incomplete recovery, multiple lines, discrepancy escalation, and explicit zero.
- Migration compatibility preserves Phase 7C rows and Phase 1 draft facts; repeat migration is a no-op.

## Known limitations

- No UPC/product catalog, document upload, extraction, SAM integration, or downstream projection.
- Manual line allocations must be entered and confirmed by the operator; Phase 2 does not suggest or automatically spread multi-line cost.
- Saving source/economics fields occurs on field change and on Next; the screen displays a concise saved status rather than a revision history UI.
- Supported TCG choices remain the current DEX set: Pokemon, One Piece, and Riftbound.
- Existing Docker/Compose/Jenkins production configuration is intentionally unchanged and remains operator-controlled.

## Rollback

1. Stop only the failed disposable/new v2.2 runtime; do not stop or alter production without operator approval.
2. Restore the preserved Phase 1 application checkpoint with its matching pre-Phase-2 database copy.
3. Do not manually drop `wizard_step` or delete migration-ledger records.
4. If Phase 2 drafts were created or edited, rolling back the database copy discards those draft changes; preserve/export any required operator evidence first.

## Git upload manifest

Upload the checkpoint contents: root Python modules, `static/`, `tests/`, approved scripts, documentation/patch/migration notes, `VERSION`, `requirements.txt`, and the existing deployment descriptors. Phase 2 does not alter deployment configuration.

Do not upload: databases or SQLite sidecars, inventory/scanner/source-database folders, images or generated output, caches, `__pycache__`, secrets, credentials, logs, machine-specific files, or disposable QA storage.

## Operator QA focus

Use only the supplied disposable database. Create a two-line Domestic acquisition (Pack Product plus identify-later Single Cards), save/exit and resume it, enter components/final USD, confirm both line allocations, reconcile, and confirm Ready. Verify the acquisition appears in Inbound and that no downstream batch or sealed unit is created.
