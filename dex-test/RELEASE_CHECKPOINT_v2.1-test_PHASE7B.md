# Dex v2.1-test Phase 7B Git-ready Checkpoint

Checkpoint scope: immutable post-sale financial events and exact confirmed return restoration for card and sealed orders. Phase 7C portfolio Operational Economics is not included.

Known-good restore point: preserve `DEX_v2.1-test_Phase7A_GitHub_Checkpoint` unchanged. This Phase 7B package is a new additive checkpoint.

## Runtime and Financial Behavior

- `VERSION` remains `v2.1-test`; economics reports identify the new rules as `acquisition-rip-v2`.
- `dex_post_sale.py` owns immutable post-sale events, unique request de-duplication, backend effective financial facts, exact return restoration, and linked inverse events.
- Original sale orders, item rows, merchandise revenue, shipping collected, marketplace fees, postage, and exact sold identities remain visible and are not rewritten by post-sale events.
- Partial/full refunds and chargebacks reduce effective proceeds without restoring inventory.
- Marketplace fee credits and actual postage refunds reduce the corresponding effective expense without rewriting the original expense.
- Reviewed sale corrections store signed component deltas. Effective net proceeds and realized P/L are derived from original facts plus the append-only ledger; the browser only formats backend values.
- Physical returns are separate from refunds. Inventory changes only after receipt and condition confirmation, and the exact original card or sealed identity can be restored at most once.
- Sellable returns become `IN_STOCK` or `REMAINING`; damaged returns route to Damaged/Excluded. A return changes active sold basis but does not infer a money refund.

## Schema and Migration

Registered migration `0005_phase7b_post_sale_events` creates:

1. `post_sale_events`
2. `post_sale_event_entries`
3. `post_sale_return_items`

It also creates lookup and one-reversal indexes. The migration transactionally rebuilds `sale_items` with preserved columns, IDs, and rows, replacing one-lifetime `UNIQUE(card_id)` with `UNIQUE(order_id, card_id)` so a physically returned card can later be sold again. It performs no refund, return, correction, basis, status, or money backfill.

## Event Types

- `PARTIAL_REFUND`
- `FULL_REFUND`
- `CUSTOMER_RETURN`
- `CHARGEBACK`
- `MARKETPLACE_FEE_CREDIT`
- `POSTAGE_REFUND`
- `SALE_CORRECTION`
- `REVERSAL`

Every event has a unique immutable event ID, unique request ID, standardized reason, effective date, recorded timestamp, payload snapshot, and optional link to the event it reverses. Material manual corrections and reversals require notes.

## APIs and UI

- `GET /api/sales/{id}` returns card or sealed order details, original facts, backend effective facts, exact items, return state, history, basis, and P/L.
- `POST /api/sales/{id}/refunds`
- `POST /api/sales/{id}/full-refund`
- `POST /api/sales/{id}/returns`
- `POST /api/sales/{id}/chargebacks`
- `POST /api/sales/{id}/fee-credits`
- `POST /api/sales/{id}/postage-refunds`
- `POST /api/sales/{id}/corrections`
- `POST /api/post-sale-events/{event_id}/reverse`
- Sales exposes Details for card and sealed orders, with immutable originals, effective Realized Economics, exact identities, post-sale actions, history, and eligible reversal controls.
- Recycle Bin identifies active damaged-return records and directs restoration through the originating Sales event rather than ordinary Restore.
- Sales CSV appends event/effective-economics fields; previous columns retain their meanings. Batch/group economics use the same backend facts and original stable sale-item weights.

## Test Summary

- Full Python suite: 82 tests passed.
- JavaScript syntax check: passed.
- Direct JavaScript authoritative batch-render, logical-viewport, sealed Sales details/Undo, and Phase 7B Sales event/detail regressions: passed.
- Python compile/import checks: passed for `app.py`, all runtime modules, and the seed helper.
- Migration coverage confirms one-time execution, transactional rollback, exact preservation of legacy sale-item IDs/values, and the compatible resale constraint.
- Phase 7B coverage confirms partial/full refunds, chargebacks, fee/postage credits, signed corrections, immutable originals, request de-duplication, linked inverses, exact card/sealed returns, damaged Excluded routing, concurrent at-most-once restoration, stable cross-batch attribution, HTTP/UI contracts, and backend P/L.
- Fresh disposable startup and `/api/health` passed as `v2.1-test`; direct batch-detail rendering passed against the same local fixture.

## Known Limitations and Technical Debt

- Phase 7C portfolio Operational Economics is absent.
- A sellable return restores the existing card condition or sealed identity; exchanges, replacement shipments, richer return grading, payment-provider synchronization, and marketplace API import remain future work.
- Chargeback input represents its signed net economic impact; automated processor fee decomposition is not included.
- Reversal-of-reversal is intentionally unsupported. A return reversal refuses to overwrite an identity whose state changed after restoration.
- Card orders retain their legacy equal item revenue split. Phase 7B reuses that stable historical attribution; it does not invent new per-card sale prices.
- Unopened sealed market/listed values remain Unknown; Receipt/Acquisition Groups remain informational and never allocate shared costs automatically.
- `app.py` and `static/app.js` remain large; unrelated refactoring was deliberately avoided.
- The private-network runtime still has no authentication and must not be exposed publicly.

## Deployment Warnings

- Production remains operator-controlled. Development and validation used only disposable local storage; no server credentials, live database, scanner folder, or real inventory were accessed.
- Startup against a Phase 7A database applies migration `0005`; first validate against a timestamped disposable copy.
- Verify the exact Compose image/tag and storage mount before an operator-run deployment. No Compose, Jenkins, port, volume, or production configuration changed in Phase 7B.
- `scripts/preprod_phase2_gate.sh` is not a Phase 7B validator and will reject the expected newer schema.
- Deploying Phase 7B does not authorize Phase 7C.

## Rollback

If Phase 7B startup or validation fails:

1. Stop only the failed/new Phase 7B runtime.
2. Restore the preserved Phase 7A application checkpoint.
3. Restore the matching timestamped pre-Phase-7B storage copy; do not pair Phase 7A code with a database containing Phase 7B events.
4. Do not delete, rewrite, manually reverse, or downgrade the migrated database in place.

## Exact Upload Manifest

Upload these files/folders from the packaged checkpoint:

- `app.py`
- `dex_acquisition.py`
- `dex_batch_economics.py`
- `dex_corrections.py`
- `dex_economics.py`
- `dex_legacy_economics.py`
- `dex_migrations.py`
- `dex_post_sale.py`
- `dex_rip.py`
- `dex_sealed.py`
- `Dockerfile`
- `requirements.txt`
- `VERSION`
- `README.md`
- `DEX_CURRENT_STATE.md`
- `DEX_OPERATING_MODEL.md`
- `MIGRATION_NOTES_v2.1-test.md`
- `PATCH_NOTES_v2.1-test.md`
- `PATCH_PLAN_ACQUISITION_RIP_BATCH.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE2.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE3.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE4.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE5.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE6.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE7A.md`
- `RELEASE_CHECKPOINT_v2.1-test_PHASE7B.md`
- `WEEKLY_ROADMAP.md`
- `WHATS_NEW_HUB_PLAN.md`
- `scripts/backup.py`
- `scripts/preprod_phase2_gate.sh`
- `scripts/seed_phase7a_demo.py`
- `scripts/seed_phase7b_demo.py`
- `static/app.js`
- `static/favicon.svg`
- `static/index.html`
- `static/styles.css`
- `static/vendor/LUCIDE_LICENSE.txt`
- `static/vendor/lucide.min.js`
- `tests/test_app.py`
- `tests/test_phase1_economics.py`
- `tests/test_phase1_migrations.py`
- `tests/test_phase2_legacy_economics.py`
- `tests/test_phase3_acquisition.py`
- `tests/test_phase4_batch_detail_render.cjs`
- `tests/test_phase4_rip.py`
- `tests/test_phase4_viewport_context.cjs`
- `tests/test_phase5_sales_details.cjs`
- `tests/test_phase5_sealed.py`
- `tests/test_phase6_batch_economics.py`
- `tests/test_phase7a_corrections.py`
- `tests/test_phase7b_post_sale.py`
- `tests/test_phase7b_sales_events.cjs`
- `tests/fixtures/phase1_economics_scenarios.json`

## Exact Exclusion Manifest

Do **not** upload:

- `.git/`, `.agents/`, `.codex/`, IDE settings, or machine-specific metadata
- `__pycache__/`, `*.pyc`, `.pytest_cache/`, coverage output, test logs, or temporary files
- `data/`, `storage/`, `storage-v2.0-test/`, `storage-v2.1-test/`, `*.db`, `*.sqlite`, SQLite journal/WAL/SHM files, or database backups
- inventory/card images, generated labels, generated CSV exports, screenshots, browser downloads, or `outputs/`
- `scanner-inbox/`, inbound scan folders, source-database contents, or real inventory data
- `.env`, credentials, passwords, private keys, tokens, cookies, or secrets
- disposable Phase 7A/7B storage/database folders
- the checkpoint-package directory nested inside the repository

## Disposable Operator Validation

1. Create new disposable storage: `python scripts/seed_phase7b_demo.py --output <new-empty-path>`.
2. Point `DEX_DATA_DIR`, `DEX_DB_PATH`, `DEX_IMAGE_DIR`, `DEX_INBOUND_DIR`, and `DEX_SOURCE_DB_DIR` at that path; set `DEX_WATCH_INBOUND=0`, choose a loopback-only non-production port, and run `python app.py`.
3. Open Sales → card order `P7B-CARD-DEMO` → Details. Confirm original `$40.00` merchandise, `$5.00` shipping, `$6.00` fees, `$7.00` postage, `$32.00` net, and exact cards `OP-B20260814-001`/`002` remain visible.
4. Add a `$5.00` merchandise and `$1.00` shipping partial refund. Confirm effective net becomes `$26.00`, the original facts remain unchanged, and repeating the same request ID through the API does not duplicate the event.
5. Add a customer return for exact card `OP-B20260814-001`, confirm physical receipt and condition, and choose Sellable. Confirm only that card becomes `IN_STOCK`, sold basis decreases by its exact basis, money does not change, and the event remains visible.
6. Reverse that return. Confirm a linked inverse remains visible and the exact card returns to `SOLD`; unsafe reversal is refused if the restored card was changed or resold first.
7. Open sealed order `P7B-SEALED-DEMO`. Confirm exact sealed unit `OP-B20260814-01-UNIT-0002`, test a confirmed sellable or damaged return, and verify only that identity becomes `REMAINING` or `ADJUSTED`.
8. Exercise chargeback, marketplace fee credit, actual postage refund, and sale correction on disposable orders. Confirm each updates only the backend effective facts and its linked reversal restores the prior effective result.
9. Open Inbound → `OP-B20260814-01`. Confirm batch/group realized values use the effective facts once, remaining basis/value reflects returned inventory, and original sale allocation is not duplicated.
10. Confirm normal inventory, intake, rip, sealed sale, Phase 7A correction history, Recycle Bin, exports, and eligible pre-event Undo workflows remain usable.
