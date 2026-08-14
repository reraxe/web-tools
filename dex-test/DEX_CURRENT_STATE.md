# Dex Current State

Baseline date: 2026-08-14  
Documented implementation baseline: `v2.0-test`  
Active development lane: `v2.1-test` Acquisition and Rip Batch Economics; Phase 3 acquisition facts complete

This document is the handoff baseline for future Dex development. It describes the observed implementation; plans and patch notes may describe broader intent.

## Architecture

Dex is a private, single-user TCG inventory system organized as a compact monolith:

- `app.py`: threaded Python HTTP server, JSON API, SQLite access and startup migrations, scanner-folder watcher, image storage, SAM matching, QR generation, CSV exports, and recycle maintenance.
- `dex_migrations.py`: versioned transactional migrations and `schema_migrations` ledger.
- `dex_acquisition.py`: Phase 3 acquisition validation, exact-cent facts, authoritative USD reconciliation, and informational receipt-group payloads.
- `dex_legacy_economics.py`: query-only Phase 2 estimated economics for legacy batches.
- `static/index.html`, `static/app.js`, and `static/styles.css`: vanilla-JavaScript single-page operator interface.
- SQLite: source of truth for batches, physical cards, source cards, sales, settings, processed scans, and activity history.
- Persistent folders: inventory database/images, scanner inbox, and SAM source database are separately mounted by Docker Compose.
- Deployment: version-isolated `v2.0-test` container, port, storage, scanner inbox, and source folder. Jenkins builds an image and health-checks `/api/health`.

Each physical card receives an immutable SKU. Card identity, physical SKU, grouped listing identity, and drawer location are separate concepts.

## Confirmed Working Workflows

The eight automated API/integration tests pass and confirm the core paths below.

- Create and edit inbound batches for supported games and acquisition types.
- Add one card or bulk-import cards with unique physical SKUs.
- Pair explicit `_front`/`_back` files and sequential scanner files in front-first or back-first order.
- Reopen completed batches and add cards without reusing existing SKUs.
- Complete batches and queue labels only after completion; requeue and mark labels printed.
- Review grouped inventory, edit card details and pricing, search sold cards by order number, and export inventory/sales CSVs.
- Complete multi-card eBay or TCGplayer sales and retain protected financial history.
- Move cards or batches to the Recycle Bin, restore them, purge eligible unsold cards, and undo supported recent actions.
- Configure timezone, TCGplayer capacity, and recycle retention settings.
- Index local One Piece reference images and optional CSV metadata for SAM.
- Match by known card number or front-image fingerprint; run SAM for one card, selected cards, or a batch.
- Upgrade a legacy v1.x database with SAM columns before creating the related index.
- Open any existing batch to view a strictly read-only **Estimated Economics** preview with valuation coverage, warnings, separate recycled value, and estimated historical sale attribution. No permanent cost basis is assigned.
- Create or edit Phase 3 acquisition facts for one homogeneous product batch: acquisition mode, product identity, units acquired, final USD paid, cost breakdown, optional foreign-currency reference, invoice, and receipt group.
- Link multiple product-specific batches from one transaction without merging their inventory or automatically distributing shared charges. The batch view reports group coverage and total explicitly assigned USD cost.
- Reject unacknowledged cost-component differences, preserve unknown cost as unknown, mirror authoritative final USD paid to legacy `total_cost`, audit material edits, and block ordinary rewrites after economics is finalized.

## Known v2.0-test Gaps

- `card_type` is indexed on source records but is not stored or auto-filled on physical cards.
- `match_reviewed` is set automatically for confident matches; there is no separate operator approval state or action.
- Planned match labels differ from implemented values: the code uses `Manual`, `Card Number`, and `Image Fingerprint`; `Database` and `Visual Review` are not implemented.
- Failed or low-confidence SAM attempts are returned but not persisted with candidate, confidence, or timestamp.
- Known card numbers receive an exact `1.0` match without image corroboration.
- Recognition uses whole-image perceptual fingerprints, not OCR or artwork-aware recognition. The fixed `0.84` threshold has no representative accuracy calibration.
- SAM supports one source row per game/card number, which cannot model alternate art, parallels, languages, editions, or multiple reference images reliably.
- Source rescans upsert records but do not remove stale records whose files were deleted.
- Duplicate filenames normalizing to the same card number are resolved by traversal order. The current library contains duplicate `EB01-016` references.
- The SAM source API returns at most 400 records and has no pagination.
- Pokemon, Riftbound, live catalog synchronization, marketplace synchronization, automatic pricing, Janna, Goose, Portfolio Analytics, and DPS remain outside v2.0-test.

## Technical Debt and Risks

- No authentication or authorization: any client that can reach the service can read exports and call mutation, sale, recycle, purge, settings, SAM, and undo endpoints. The port must remain private.
- The threaded server, scanner watcher, SAM, and recycle maintenance do not use one consistent SQLite write-serialization policy.
- Requests may contain up to 250 MB of base64 JSON; concurrent imports can create high memory pressure.
- Legacy startup-time conditional `ALTER TABLE` statements still exist alongside the new Phase 1 migration framework. The framework provides a ledger and transactional rollback for registered migrations, but the legacy alterations have not yet been converted into registered migrations.
- Broad exception handlers can expose internal error and path details through API responses.
- Activity history is not a complete audit trail. SAM and several mutations are not logged or undoable; automatic purge lacks the manual purge record.
- Multi-card sale subtotal is divided evenly instead of retaining explicit item-level sale prices.
- Receipt/Acquisition Groups are reference strings rather than a separate transaction table in Phase 3. This is intentional for the approved first release, but richer shared-charge reconciliation will require an audited model later.
- Phase 3 acquisition facts are draft inputs only. There are no rip sessions, bulk reserves, permanent card cost basis, sealed-unit records, sealed sales, or finalization workflow yet.
- The Phase 2 pre-production gate script expects ledger-only schema mutation and is intentionally not valid for Phase 3's approved additive migration.
- `app.py` and `static/app.js` are large single files, increasing coupling and regression risk.
- Automated SAM coverage proves route and persistence plumbing with a trivial identical image, not real scan accuracy or false-positive behavior.
- Jenkins runs a health smoke test but not the full automated suite. The visual test is machine-specific and not part of CI.
- The checked-in SAM library contains an apparent nested project copy inside the EB01 folder, adding unrelated files and making reference-library maintenance error-prone.
- Root `index.html` coexists with the served `static/index.html`, creating ambiguity about which interface file is authoritative.
- Operational backups cover SQLite through `scripts/backup.py`; a complete recovery plan must also preserve inventory images and configuration.

## Recommended Development Order

1. **Preserve the gate:** retain the known-good Phase 2 checkpoint and test every Phase 3 migration against disposable legacy copies before an operator-authorized deployment.
2. **Phase 4 only after approval:** add explicit rip sessions, intake selection, bulk reserves, exact allocation previews, immutable finalized card basis, and append-only corrections.
3. **Continue the approved economics roadmap:** sealed units/sales in Phase 5, versioned batch reporting in Phase 6, then Phase 7A/7B/7C corrections and Operational Economics.
4. **Secure private operation:** add authentication/authorization or an enforced trusted-proxy boundary, safer error responses, request limits, and consistent write serialization.
5. **Finish and harden SAM:** improve variant modeling, source reconciliation, review semantics, representative fixtures, confidence measurement, and false-positive protection.
6. **Reduce coupling:** continue extracting dedicated economics/migration modules without reorganizing unrelated code; later separate persistence, scanner, sales, and frontend views.

## Baseline Rule

Future work should preserve physical SKUs, sale/audit history, review-first matching, recoverable deletion, stable/test data isolation, and manual fallback. Update this document whenever architecture, workflow guarantees, known gaps, or development priorities materially change.
