# DEX v2.2-test Inbound 2.0 Phase 2 UX Revision Checkpoint

Scope: focused three-screen Guided Manual Acquisition UX only. The accepted original Phase 2 package and immutable v2.1 Phase 7C package remain preserved restore points. Phase 3 UPC/catalog, documents/extraction, SAM, downstream batch projection, production deployment, and production data are not authorized.

## Runtime behavior

- Runtime remains `v2.2-test`; economics calculation version remains `acquisition-rip-v3` because no Phase 3–7C economics formula changed.
- New Acquisition is the primary Inbound action. Advanced / Legacy New Batch remains available.
- The resumable wizard has three screens: What did you acquire?, Product & Purchase Details, and Review Acquisition.
- Draft facts and progress autosave without confirming cost, allocation, reconciliation, or readiness.
- One line receives 100% of final landed cost only during explicit acquisition confirmation, using audited method `SINGLE_LINE_100_PERCENT`.
- Multiple lines require explicit allocation method/cost confirmation and exact reconciliation to final USD.
- Missing cost remains Unknown. Explicit `$0.00` requires its reason and special confirmation.
- Confirmation stops at `READY_FOR_INTAKE`; it creates no batch, card, sealed unit, basis, UPC mapping, document, extraction, SAM result, rip, sale, or portfolio fact.

## Schema and migration

Migration `0008_v22_phase2_ux_revision`:

- adds draft-safe `acquisitions.payment_method` with supported human choices;
- maps persisted `SOURCE`/`ECONOMICS` progress to `PRODUCTS`;
- maps persisted `RECONCILIATION` progress to `REVIEW`;
- leaves acquisition state, financial confirmation, line allocations, batches, inventory, and economics unchanged.

The migration runs within the established SQLite migration savepoint and ledger behavior. Re-running is a no-op.

## API and contract changes

- Existing acquisition create/autosave accepts validated `payment_method`.
- Acquisition readiness requires source, merchant, purchase date, and payment method.
- Acquisition detail returns `automatic_single_line_allocation_preview` from the backend.
- Confirmation atomically records the single-line allocation event and authoritative acquisition event only after all validation gates pass.
- Foundation contract reports the three primary wizard steps, legacy persisted steps, payment methods, and unchanged Phase 2 boundaries.

## Verification

- 102 Python tests passed.
- Direct three-screen JavaScript contract test passed.
- JavaScript syntax check passed.
- Migration compatibility preserves legacy Phase 7C rows and existing v2.2 drafts; old progress resumes on its corresponding new screen.
- Exact-cent single-line preview/confirmation is backend-generated and tested with `$10.00 / 3 = $3.34 / $3.33 / $3.33` semantics.
- All existing Phase 1–7C tests remain green.

## Known limitations

- No UPC/product catalog, receipt upload/storage/extraction, SAM change, or downstream projection.
- Receipt camera/upload controls are intentionally disabled placeholders.
- Multiple-line landed costs are manual; no suggested allocation engine is included.
- Product choices remain the current DEX TCG set.
- Autosave occurs on field change/blur and on navigation; it never confirms authoritative facts.
- Production deployment remains fully operator-controlled.

## Rollback

1. Stop only the failed disposable/new runtime; do not alter production without a separate operator-approved deployment step.
2. Restore the preserved original Phase 2 application checkpoint with its matching pre-revision database copy.
3. Do not manually delete migration-ledger rows or drop the payment column.
4. If revised-Phase-2 drafts matter, retain a copy before rollback because restoring the earlier database copy discards later draft edits.

## Git upload manifest

Upload:

- root Python source modules, including `app.py`, `dex_inbound.py`, and `dex_migrations.py`;
- `static/`;
- `tests/`;
- approved tracked `scripts/` files;
- `README.md`, operating model, roadmap, patch plan, patch notes, migration notes, this checkpoint document, and prior checkpoint documents;
- `VERSION`, `requirements.txt`, and unchanged deployment descriptors.

Do not upload:

- databases or SQLite sidecars;
- `storage/`, scanner inboxes, source databases, inventory/card images, or generated output;
- disposable QA data;
- caches, `__pycache__`, `.pytest_cache`, logs, secrets, credentials, keys, `.env`, or machine-specific files.

## Disposable operator QA focus

Create a one-line Domestic Sealed Product acquisition. Verify the three screens, required payment method, hidden International fields, disabled receipt actions, exact component/final reconciliation, automatic 100% line allocation disclosure, and Ready for Intake result with no downstream batch. Then create a multi-line acquisition and verify explicit line allocations remain required and reconcile exactly.
