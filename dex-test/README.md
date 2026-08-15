# Dex

Dex is a private, single-user TCG inventory system for individual physical cards. It tracks inbound batches, front/back scans, unique SKUs, 2 x 1 QR labels, grouped inventory, market-price ranges, drawer locations, and multi-card outbound orders.

Current development release: **Dex v2.2-test**

Known-good restore baseline: **Dex v2.1-test Phase 7C**. The complete Acquisition and Rip Batch Economics checkpoint remains preserved while v2.2-test builds Inbound 2.0 in separately approved phases.

## Release policy

- Stable releases are preserved and are never overwritten by development work.
- `v1.1-test` consolidates the first quality-of-life work planned through the former v1.4 roadmap.
- `v1.1a-test` added inventory safety and intake corrections discovered during live 29-card batch testing.
- `v1.1b-test` added batch-first intake, bulk batch-card selection, bottom batch completion, unified set entry, and order-number search for sold cards.
- `v1.2-stable` promotes the tested v1.1b workflow with the final searchable color picker for cleaner drawer labels.
- `v2.0-test` starts SAM, the local source-database matcher for One Piece scan recognition.
- `v2.1-test` adds Acquisition and Rip Batch Economics without overwriting the v2.0-test baseline or stable inventory data.
- `v2.2-test` adds Inbound 2.0. Phase 3 adds a local commercial-product catalog and UPC/EAN/GTIN intake to the focused, resumable **New Acquisition** wizard while retaining **Advanced / Legacy New Batch** for compatibility.
- Test releases use a separate Docker tag, container, port, and storage volume so test data cannot affect stable inventory.
- Stable releases are the versions intended for weeklong real inventory work before the next test lane begins.
- Urgent fixes to a stable release use a patch version such as `v1.0.1-test` before promotion to `v1.0.1-stable`.
- Every release response should include patch notes plus a README/docs note that calls out any setup, workflow, folder, or operator-facing documentation changes.

Issues found during the current pilot are tracked in [`V1.1_TEST_BACKLOG.md`](V1.1_TEST_BACKLOG.md).

## Repository layout

- `static/index.html`: browser interface.
- `static/app.js` and `static/styles.css`: frontend behavior and styling.
- `app.py`: web API, scanner-folder watcher, and SQLite access.
- `dex_acquisition.py`: Phase 3 acquisition-fact validation, exact-cent normalization, and receipt-group reporting.
- `dex_rip.py`: Phase 4 rip sessions, exact allocation previews, finalization, and append-only basis corrections.
- `dex_sealed.py`: Phase 5 sealed-unit identity, exact landed basis, sealed-only outbound economics, quantity adjustments, and atomic sale Undo.
- `dex_batch_economics.py`: Phase 6 read-only authoritative batch/group rollups, stable order attribution, valuation coverage/freshness, reconciliation, and export rows.
- `dex_corrections.py`: Phase 7A append-only acquisition/basis corrections, reason-aware card/sealed dispositions, operational-loss entries, durable tombstones, and linked inverse reversals.
- `dex_post_sale.py`: Phase 7B immutable refunds, returns, chargebacks, fee/postage credits, sale corrections, effective financial facts, and exact inventory restoration.
- `dex_portfolio_economics.py`: Phase 7C read-only Finalized Economics portfolio rollup, exact order/item de-duplication, coverage/freshness, reconciliation, and export rows.
- `dex_inbound.py`: v2.2-test Inbound 2.0 draft acquisition identity, autosave, product lines, reconciliation gates, and append-only lifecycle events.
- `dex_catalog.py`: v2.2-test commercial-product catalog, barcode normalization/validation, scan aggregation, learned mappings, and append-only mapping corrections.
- `dex_migrations.py`: transactional, versioned SQLite migrations and migration ledger.
- `dex_legacy_economics.py`: read-only Phase 2 legacy economics estimates.
- `Dockerfile`: production image build.
- `Jenkinsfile`: Docker build and container smoke test.
- `compose.yaml`: persistent home-server deployment.

`index.html` is packaged inside the image, but Dex is not a static-only website. The Python service supplies the shared database, images, scanner intake, labels, and outbound records.

## MVP workflow

1. Create an inbound purchase batch for a booster box, packs, purchased singles, a trade, or existing inventory.
2. Add front/back scans in the browser, or save scanner images into that batch's watched folder.
3. Select one image pair or a complete scan batch; Dex pairs files and immediately assigns a unique SKU to every physical card.
4. Use SAM Match on selected cards or the full batch when a local One Piece source database is available.
5. Review and edit cards from the multi-card batch grid.
6. Finish the batch and print all queued 2 x 1 labels.
7. Scan sleeve QR codes into an eBay or TCGplayer outbound order.

Existing batches also show a read-only **Estimated Economics** panel in v2.1-test Phase 2. The panel is explicitly estimate-only, reports valuation coverage and freshness, and never assigns permanent cost basis or converts legacy inventory.

Inbound 2.0 creates an immediate immutable Draft Acquisition ID and autosaves non-authoritative facts and wizard position. Its three screens capture product choice, combined product/purchase details, and a human review. Pack and sealed lines can now scan UPC-A, EAN-13, or GTIN-14 identifiers: known local mappings visibly populate commercial product facts, repeat scans increment one line, and different products remain independent lines. Unknown codes are never guessed; the operator may identify them for one acquisition or remember an audited operator-confirmed mapping. On a clean one-line acquisition, the backend discloses and performs the deterministic 100% landed-cost allocation at final confirmation. Missing cost remains **Unknown / Setup incomplete**. Product recognition still creates no batch, sealed unit, basis, rip, sale, document, SAM fact, or portfolio result.

Future Inbound/economics work follows the approved [Accounting-by-Default UX directive](DEX_ACCOUNTING_BY_DEFAULT.md): operators provide source facts, backend services perform deterministic accounting, visible routine results create no repetitive confirmation task, and ambiguous or exceptional reality becomes Needs Attention. The future Attention Center remains a design contract, not an implemented feature.

Phase 3 adds a separate **Acquisition Cost Facts** panel and editor. A batch may record an acquisition mode, one homogeneous product and quantity, final USD paid, itemized cost components, optional original-currency reference values, invoice reference, and Receipt/Acquisition Group reference. Final USD paid is authoritative. Linked receipt groups are informational and never allocate shared shipping, tax, fees, or discounts automatically.

Phase 4 adds **Rip Sessions & Cost Allocation**. Create a rip without activating it, explicitly select **Start intake**, scan/add its cards, then review equal or manual allocation and any unscanned bulk. Finalization requires all intended cards to be accounted for and an exact `$0.00` reconciliation. Finalized basis is locked; later changes append an audited correction instead of rewriting the original event. Batch completion and label printing remain independent.

Phase 5 adds exact **Sealed Unit Inventory** beneath trustworthy sealed acquisition batches. Each unit has a stable internal ID, stable sequence, deterministic landed basis, and one of four states: remaining, opened, sold, or adjusted. Creating a rip claims exact remaining units. The Outbound page provides separate Card Sale and Sealed-Product Sale workflows; mixed orders are rejected. Sealed orders store exact unit IDs, merchandise revenue, shipping collected, marketplace fees, actual postage, separately recorded marketplace tax, sold basis, net proceeds, and realized P/L. Sales provides an explicit **Details** view for sealed orders, including exact consumed unit IDs and Undo eligibility. Eligible Undo restores the exact units atomically while retaining the canceled order and event history.

Phase 6 adds a backend-calculated **Batch Economics** interface for authoritative economics batches. Its collapsible sections keep realized recovery/P&L separate from unrealized market/listed value, show valuation coverage and freshness, retain rip and sale drill-down history, reconcile cost and sealed quantities, and expose informational Receipt/Acquisition Group rollups without allocating shared charges. Unknown values remain unknown and make affected positions visibly incomplete. Batch economics, inventory, and sales CSVs include the calculation version and append new fields without changing prior column meanings.

Phase 7A adds **Corrections & Dispositions** to finalized or economically locked batches. Acquisition-cost changes, card/bulk basis transfers, duplicate/entry corrections, sealed quantity corrections, damage, loss, and disposal are immutable events layered over preserved source facts. Physical loss moves basis to a separately labeled operational-loss line; DEX makes no tax conclusion. Disposed cards retain durable tombstones and cannot be hard-purged. Restoration uses a linked inverse event, leaving the original event visible.

Phase 7B adds append-only post-sale events to every card or sealed order detail. Partial/full refunds, chargebacks, marketplace fee credits, actual postage refunds, and reviewed sale corrections change effective proceeds without rewriting the original order. Customer returns are separate physical events: DEX requires receipt and condition confirmation, restores the exact card or sealed identity at most once, and routes damaged returns to Excluded. Linked inverse events preserve both the original event and its reversal. Backend facts remain the only source for realized recovery and P/L.

Phase 7C adds **Operational Economics** as a read-only portfolio view. It includes Finalized Economics batches only and keeps legacy estimates and unfinished authoritative batches visibly separate. The backend derives acquisition cost, effective realized proceeds, active sold basis, realized P/L, operational loss, remaining known market/listed value, uncapped recovery, and current/projected positions from Phase 6–7B facts. Cross-batch orders use their original stable item attribution once; canceled orders and reversed event deltas are excluded by effective state. Coverage and freshness remain explicit, and unopened sealed value stays Unknown without an authoritative value fact. The portfolio CSV serializes this same payload.

The database is the source of truth. A complete inventory CSV can be downloaded at any time for reporting or an additional portable backup.

Card identification and completed-sale pricing remain review-assisted. In `v2.0-test`, SAM can compare One Piece front scans to a local source image library and optional CSV metadata. Marketplace adapters and completed-sale collection stay separate from this release.

## Run locally

Python 3.11 or newer is enough for the app. Install the one optional QR dependency for scannable labels:

```powershell
python -m pip install -r requirements.txt
python app.py
```

Open `http://localhost:8080`.

To preview the interface with sample cards:

```powershell
$env:DEX_SEED_DEMO="1"
python app.py
```

The disposable demo includes two homogeneous sealed-product batches on `DEMO-RECEIPT-001`: six OP16 booster boxes at $660.00 and two ST27 starter decks at $86.40. Their assigned batch costs reconcile to $746.40 while remaining separate batches.

For a disposable Phase 7A scenario, create a new storage directory with `python scripts/seed_phase7a_demo.py --output <new-empty-path>`, then run Dex with its data/database paths pointed at that directory. The script refuses to overwrite an existing path and seeds `OP-B20260814-01` with one finalized rip, four card-basis records, and five remaining sealed units.

For Phase 7B operator QA, use `python scripts/seed_phase7b_demo.py --output <new-empty-path>`. It refuses existing paths and creates finalized batch `OP-B20260814-01`, card order `P7B-CARD-DEMO`, and sealed order `P7B-SEALED-DEMO` using disposable identities only.

For Phase 7C operator QA, use `python scripts/seed_phase7c_demo.py --output <new-empty-path>`. It refuses existing paths and creates finalized sealed/rip and singles batches, an informational receipt group, effective refund history, a cross-batch order, sealed sale, operational disposition, one legacy estimate, and unfinished authoritative examples. Open **Economics** after launching that disposable storage.

For Inbound 2.0 Phase 3 operator QA, use `python scripts/seed_v22_phase3_catalog_demo.py --output <new-empty-path>`. It refuses existing paths and seeds only a disposable product catalog: UPC-A `012345678905` resolves to OP16 Booster Box, EAN-13 `4006381333931` resolves to ST27 Starter Deck, and valid UPC-A `036000291452` is intentionally unknown for the learn-mapping flow.

## Debian Docker deployment

No server-specific details are needed to build Dex. On the Debian server:

```bash
git clone <your-repository-url> dex
cd dex
mkdir -p storage scanner-inbox source-database
docker compose up -d --build
```

Compose defaults to Debian user/group `1000:1000`. If the server account uses different IDs, put `PUID` and `PGID` in a `.env` file before starting Dex.

The included test compose file publishes Dex at `http://SERVER-IP:8082` and uses separate test storage. Keep the port blocked from the public internet. Earlier releases remain untouched on their existing ports and storage.

The persistent folders are:

- `storage/`: SQLite database, original card images, and backups.
- `scanner-inbox/`: scanner drop folders created for open batches.
- `source-database/`: local One Piece reference images and optional card-list CSV files for SAM.

The SQLite database is stored at `storage/dex.db` on the host through the `/data` container volume. Rebuilding or replacing the image does not remove inventory data.

When upgrading an older Dex database, Dex keeps the existing SAM and Phase 3–7C compatibility behavior. v2.2-test adds migrations `0006` through `0009`. Migration `0009_v22_phase3_product_catalog_upc` creates empty catalog/identifier/audit tables and nullable acquisition-line linkage; it guesses no historical mappings and changes no inventory or economics fact. Always test against a disposable Phase 7C database copy before an operator-approved deployment; see [`MIGRATION_NOTES_v2.2-test.md`](MIGRATION_NOTES_v2.2-test.md).

### SAM source database

Put One Piece source images under `source-database-v2.0-test`. Filenames such as `OP16-067.png`, `EB01-001.jpg`, or `PRB02-018.png` let SAM identify the card number. A CSV in the same folder can add names, rarity, color, and card type. Useful CSV columns are `card_number`, `name`, `set_code`, `set_name`, `rarity`, `color`, and `card_type`.

After adding or replacing files, open the SAM page in Dex and click **Rescan Source**. Then open an inbound batch and use **SAM Match All** or **SAM Match Selected**.

See [`SAM_SOURCE_DATABASE_PLAN.md`](SAM_SOURCE_DATABASE_PLAN.md) for the recommended server folder layout.

## Jenkins image build

Point a Pipeline job at this GitHub repository. Jenkins reads `Jenkinsfile`, builds the image, starts a temporary container, and checks `/api/health`. Image tags, branches, and live deployment remain operator-controlled; inspect the current Jenkins and Compose files before any server action.

The Jenkins agent needs Docker access. A registry push stage can be added using the server's existing Jenkins credentials and naming convention.

Share `scanner-inbox/` to the Windows scanner computer using the server's existing Samba setup. Each open batch creates a folder named after its batch code. Dex recognizes `_front` / `_back` filename pairs; otherwise it pairs sequential images in filename order.

## Phone camera access

Desktop use works over private HTTP. Mobile browsers generally require HTTPS before granting camera access. During server installation, place Dex behind the server's existing HTTPS reverse proxy and use a trusted local hostname. Until that is configured, outbound SKUs can still be typed into the phone interface.

## Backups

Back up the entire `storage/` folder using the server's normal backup system. It contains the SQLite database and card images. A scheduled database snapshot can be added once the server's backup location is known.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DEX_PORT` | `8080` | Internal app port |
| `DEX_DATA_DIR` | `./data` | Database and image storage |
| `DEX_INBOUND_DIR` | `./data/inbound` | Watched scanner folder |
| `DEX_SOURCE_DB_DIR` | `./data/source-database` | Local source images and CSV metadata for SAM |
| `DEX_WATCH_INBOUND` | `1` | Enables automatic folder intake |
| `DEX_SCAN_INTERVAL` | `5` | Folder check interval in seconds |
| `DEX_SEED_DEMO` | `0` | Adds sample records to an empty database |
| `DEX_TIMEZONE` | `America/New_York` | Business dates used for SKUs and exports |
| `DEX_TCG_CAPACITY` | `500` | Initial TCGplayer listing capacity |

## Tests

```bash
python -m unittest discover -s tests -v
```

The 117-test Python suite covers all prior behavior plus Phase 3 migration rollback, barcode validation, leading-zero preservation, scan idempotency/aggregation, unknown and learned mappings, collisions/corrections, API contracts, no downstream projection, and a 1,000-product catalog-search performance guard. Direct JavaScript regressions exercise the three-screen wizard, keyboard scanner path, unknown-product controls, mapping details, prior batch/Sales behavior, viewport preservation, and backend-only economics rendering.

The immutable v2.1 Phase 7C restore point and accepted v2.2 phase checkpoints remain preserved separately. The release-candidate handoff is [`RELEASE_CHECKPOINT_v2.2-test.md`](RELEASE_CHECKPOINT_v2.2-test.md); production approval remains blocked on physical barcode-scanner QA.
