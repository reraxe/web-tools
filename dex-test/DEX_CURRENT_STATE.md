# Dex Current State

Baseline date: 2026-08-15  
Known-good restore baseline: `v2.1-test` Phase 7C  
Active development lane: `v2.2-test` Inbound 2.0; Phase 3 Product Catalog + UPC Intake complete

This document is the handoff baseline for future Dex development. It describes the observed implementation; plans and patch notes may describe broader intent.

## Architecture

Dex is a private, single-user TCG inventory system organized as a compact monolith:

- `app.py`: threaded Python HTTP server, JSON API, SQLite access and startup migrations, scanner-folder watcher, image storage, SAM matching, QR generation, CSV exports, and recycle maintenance.
- `dex_migrations.py`: versioned transactional migrations and `schema_migrations` ledger.
- `dex_acquisition.py`: Phase 3 acquisition validation, exact-cent facts, authoritative USD reconciliation, and informational receipt-group payloads.
- `dex_rip.py`: Phase 4 explicit rip intake, partial-unit cost, allocation previews, finalization, and append-only card/bulk basis events.
- `dex_sealed.py`: Phase 5 exact sealed-unit ledger, deterministic unit basis, rip/sale claims, sealed-order economics, quantity adjustment, and atomic sale Undo.
- `dex_batch_economics.py`: Phase 6 query-only authoritative batch/group calculations, stable sale attribution, valuation coverage/freshness, reconciliation, and export rows.
- `dex_corrections.py`: Phase 7A append-only correction/disposition ledger service, current corrected values, operational-loss treatment, durable tombstones, and linked inverse reversals.
- `dex_post_sale.py`: Phase 7B immutable sale-adjustment ledger, effective financial facts, exact return/restoration state transitions, de-duplication, and linked inverses.
- `dex_portfolio_economics.py`: Phase 7C read-only Finalized Economics portfolio totals, stable per-item order attribution, valuation coverage/freshness, reconciliation, and CSV rows.
- `dex_inbound.py`: v2.2 Draft Acquisition identity, three-screen guided wizard facts, Accounting-by-Default reconciliation, explicit confirmation, and append-only lifecycle events. It creates no downstream batch or economics facts yet.
- `dex_catalog.py`: v2.2 local commercial-product catalog, validated text identifiers, request-safe scan aggregation, learned mappings, and append-only mapping corrections.
- `dex_legacy_economics.py`: query-only Phase 2 estimated economics for legacy batches.
- `static/index.html`, `static/app.js`, and `static/styles.css`: vanilla-JavaScript single-page operator interface.
- SQLite: source of truth for batches, physical cards, source cards, sales, settings, processed scans, and activity history.
- Persistent folders: inventory database/images, scanner inbox, and SAM source database are separately mounted by Docker Compose.
- Deployment: version-isolated `v2.0-test` container, port, storage, scanner inbox, and source folder. Jenkins builds an image and health-checks `/api/health`.

Each physical card receives an immutable SKU. Card identity, physical SKU, grouped listing identity, and drawer location are separate concepts.

## Confirmed Working Workflows

The complete automated suite passes and confirms the core paths below.

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
- Create rip sessions without activating scanner intake; explicitly start/stop intake and show which rip currently receives new scanner/browser cards.
- Require confirmation before switching away from an active rip that has unprocessed scanner files.
- Preview and finalize equal or manual card allocation with known-quantity bulk or an explicit unknown-quantity reserve, requiring exact-cent reconciliation and all-cards confirmation.
- Consume partial-rip cost from deterministic authoritative landed-unit sequences, lock finalized sessions against ordinary intake, and append audited corrections without rewriting original basis events.
- Materialize stable sealed units only for batches with trustworthy authoritative USD cost and units acquired; preserve exact basis down to the cent.
- Open exact sealed units through rip creation, sell the lowest remaining stable sequences by default, or accept explicit exact unit IDs through the API.
- Complete separate multi-unit sealed-product orders with backend-calculated net proceeds, sold basis, and realized P/L; marketplace-collected tax is recorded but excluded.
- Prevent the same unit from being opened/sold twice, reject overselling and mixed card/sealed orders, retain canceled order history, and restore exact units through eligible Undo.
- Reconcile every sealed batch as acquired = opened + sold + remaining + corrected/adjusted, with reason-aware adjustment events.
- Open an authoritative batch into a collapsible economics interface whose first screen answers cost, recovered proceeds, known remaining value, and current ahead/behind position.
- Keep realized proceeds/P&L visually and mathematically separate from remaining market/listed value; show unknown prices as incomplete coverage with known or explicitly unknown freshness.
- Calculate uncapped Cost Recovery, Current Economic Position, and Projected Listed Position exclusively in the backend from source facts; the browser formats returned values only.
- Attribute cross-batch card orders once using stable historical sale-item weighting and aggregate Receipt/Acquisition Groups without duplicating order-level proceeds or allocating shared costs.
- Export versioned batch economics and append Phase 6 provenance fields to inventory/sales CSVs without changing existing column meanings.
- Correct authoritative acquisition cost without rewriting `batches.final_usd_paid_cents`; deterministically reconcile the change across stable sealed-unit IDs or an explicit singles target.
- Transfer exact basis between finalized cards and rip bulk while preserving the original allocation and a zero-sum audit trail.
- Distinguish duplicate/entry errors from physical damage, loss, and disposal. Duplicate basis is reallocated; physical basis moves to separately labeled Operational Loss.
- Preserve disposed card/sealed records as durable tombstones, block normal hard purge, and restore state/basis only through a linked inverse event while keeping the original event visible.
- Inspect card and sealed orders from Sales with original facts, backend-derived effective economics, exact sold identities, and complete append-only event history.
- Record partial/full refunds and chargebacks without restoring inventory; record fee credits and actual postage refunds separately without rewriting the original sale.
- Restore exact returned card or sealed identities only after physical receipt and condition confirmation, at most once under concurrent requests; route damaged returns to Excluded and require linked reversal for restoration.
- Preserve returned-card sale history while permitting a later new sale row for that same physical identity; current inventory and batch economics count the physical card once.
- Reuse original stable sale-item weighting when post-sale adjustments affect a cross-batch order, so batch portions and group totals reconcile without duplicate proceeds.
- Open **Operational Economics** to see Finalized Economics acquisition cost, effective recovered proceeds, active sold basis, realized P/L, operational loss, remaining known market/listed value, uncapped recovery, and current/projected positions from backend source facts only.
- Keep legacy estimates and authoritative-but-unfinalized batches separate from portfolio totals; show explicit card/sealed coverage, freshness, and incomplete states. Remaining sealed value stays Unknown without an authoritative value fact.
- Reconcile portfolio cost to batch facts and effective proceeds to stable exact sale-item attribution, counting cross-batch orders once while excluding canceled orders and neutralizing linked reversals.
- Export the same read-only `acquisition-rip-v3` portfolio payload as CSV without storing dashboard totals.
- Create an immutable Draft Acquisition ID immediately, autosave only non-authoritative facts and wizard position, and preserve every lifecycle mutation as an immutable request-safe event.
- Keep `PACK_PRODUCT` and `SEALED_PRODUCT` distinct, require every suggested line allocation to disclose its method, and prevent suggestions from becoming authoritative without explicit confirmation.
- Require exact product-line landed-cost reconciliation, `$5 OR 2%` material-discrepancy confirmation, and severe `50%+` escalation. Missing final USD stays Unknown rather than becoming `$0.00`.
- Use the focused three-screen **New Acquisition** wizard while retaining Advanced / Legacy New Batch compatibility and all Phase 3–7C batch economics.
- Scan validated UPC-A, EAN-13, and GTIN-14 identifiers for Pack/Sealed lines; known products populate visibly, repeat scans increment one line, and different products stay economically independent.
- Keep unknown identifiers unguessed, support acquisition-local identification or explicit operator-confirmed Remember Mapping, block silent collisions, and preserve reasoned mapping-correction history.
- Preserve manual Pack Product, Sealed Product, and Single Cards entry. Product recognition creates no batch, card, sealed unit, basis, document, receipt extraction, SAM match, or portfolio fact.

## Known Gaps

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
- The Phase 3 commercial-product catalog is local only; manufacturer/import synchronization and authoritative external provenance are not implemented.
- Physical keyboard-emulating barcode-scanner operator QA remains outstanding. Automated keyboard submission and browser simulation have passed, but production approval requires real-device confirmation.
- The mapping-correction dialog uses a bounded product list; a large future catalog may need search within that dialog.
- Receipt/document storage, extraction/OCR, SAM integration with acquisitions, downstream batch projection, and the global Attention Center remain later approval gates.

## Technical Debt and Risks

- No authentication or authorization: any client that can reach the service can read exports and call mutation, sale, recycle, purge, settings, SAM, and undo endpoints. The port must remain private.
- The threaded server, scanner watcher, SAM, and recycle maintenance do not use one consistent SQLite write-serialization policy.
- Requests may contain up to 250 MB of base64 JSON; concurrent imports can create high memory pressure.
- Legacy startup-time conditional `ALTER TABLE` statements still exist alongside the new Phase 1 migration framework. The framework provides a ledger and transactional rollback for registered migrations, but the legacy alterations have not yet been converted into registered migrations.
- Broad exception handlers can expose internal error and path details through API responses.
- Activity history is not a complete audit trail. SAM and several mutations are not logged or undoable; automatic purge lacks the manual purge record.
- Multi-card sale subtotal is divided evenly instead of retaining explicit item-level sale prices.
- Receipt/Acquisition Groups are reference strings rather than a separate transaction table in Phase 3. This is intentional for the approved first release, but richer shared-charge reconciliation will require an audited model later.
- Phase 4 stores one aggregate bulk reserve per rip rather than individual fake bulk-card SKUs. Resolution into later scanned cards uses audited basis transfers; richer bulk sale/disposition states remain later work.
- Phase 5 uses one stable unit record per homogeneous acquired unit. Nested box/pack/component models and mixed-product batches remain deferred.
- Sealed Sales rows retain exact consumed IDs and eligible Undo. Once immutable post-sale history exists, ordinary sealed Undo is disabled and corrections use linked events.
- The legacy Phase 5 `/adjust` API remains for backwards compatibility, but the operator UI now routes sealed corrections/dispositions through the Phase 7A immutable event workflow.
- Card orders retain the legacy equal item split; Undo now retains the canceled order/item history instead of deleting it. Explicit operator-entered per-card sale lines remain future work.
- Phase 6 has no market/listed price fact for unopened sealed units, so those units correctly produce unknown valuation coverage rather than a guessed value. Marketplace pricing remains manual.
- Phase 6 group rollups aggregate only explicitly assigned batch costs. Shared receipt shipping, tax, discounts, and fees remain informational until an audited allocation workflow exists.
- Phase 7C completes the approved v2.1-test development scope; production deployment and any post-v2.1 work remain separately operator-approved.
- A confirmed sellable return restores to `IN_STOCK`/`REMAINING`; richer condition grading, exchanges, replacement shipments, and refund-to-payment-provider integration remain outside this phase.
- Event-ledger targets use typed integer IDs without database foreign keys to every polymorphic target table; service validation and immutable event/tombstone relationships enforce target scope.
- The Phase 2 pre-production gate script expects ledger-only schema mutation and is intentionally not valid for Phase 3's approved additive migration.
- `app.py` and `static/app.js` are large single files, increasing coupling and regression risk.
- Automated SAM coverage proves route and persistence plumbing with a trivial identical image, not real scan accuracy or false-positive behavior.
- Jenkins runs a health smoke test but not the full automated suite. The visual test is machine-specific and not part of CI.
- The checked-in SAM library contains an apparent nested project copy inside the EB01 folder, adding unrelated files and making reference-library maintenance error-prone.
- Root `index.html` coexists with the served `static/index.html`, creating ambiguity about which interface file is authoritative.
- Operational backups cover SQLite through `scripts/backup.py`; a complete recovery plan must also preserve inventory images and configuration.

## Recommended Development Order

1. **Preserve the gate:** retain the immutable Phase 7C and prior v2.2 Git-ready checkpoints; test v2.2 migrations only against disposable Phase 7C copies before any operator-authorized deployment.
2. **Stop at the approved boundary:** do not begin receipt/document work or deploy to production. Physical-scanner QA and explicit production approval remain required.
3. **Keep reporting derived:** extend the backend event/source-fact model rather than storing dashboard totals or duplicating formulas in the frontend.
4. **Secure private operation:** add authentication/authorization or an enforced trusted-proxy boundary, safer error responses, request limits, and consistent write serialization when separately approved.
5. **Finish and harden SAM:** improve variant modeling, source reconciliation, review semantics, representative fixtures, confidence measurement, and false-positive protection when it returns to scope.
6. **Reduce coupling:** continue extracting dedicated economics/migration modules without reorganizing unrelated code; later separate persistence, scanner, sales, and frontend views.

## Baseline Rule

Future work should preserve physical SKUs, sale/audit history, review-first matching, recoverable deletion, stable/test data isolation, and manual fallback. Update this document whenever architecture, workflow guarantees, known gaps, or development priorities materially change.
