# Dex

Dex is a private, single-user TCG inventory system for individual physical cards. It tracks inbound batches, front/back scans, unique SKUs, 2 x 1 QR labels, grouped inventory, market-price ranges, drawer locations, and multi-card outbound orders.

Current development release: **Dex v2.1-test**

Documented implementation baseline: **Dex v2.0-test**. The v2.0-test SAM and inventory behavior remains the preserved baseline while v2.1-test Acquisition and Rip Batch Economics is developed in gated phases.

## Release policy

- Stable releases are preserved and are never overwritten by development work.
- `v1.1-test` consolidates the first quality-of-life work planned through the former v1.4 roadmap.
- `v1.1a-test` added inventory safety and intake corrections discovered during live 29-card batch testing.
- `v1.1b-test` added batch-first intake, bulk batch-card selection, bottom batch completion, unified set entry, and order-number search for sold cards.
- `v1.2-stable` promotes the tested v1.1b workflow with the final searchable color picker for cleaner drawer labels.
- `v2.0-test` starts SAM, the local source-database matcher for One Piece scan recognition.
- `v2.1-test` adds Acquisition and Rip Batch Economics without overwriting the v2.0-test baseline or stable inventory data.
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

Phase 3 adds a separate **Acquisition Cost Facts** panel and editor. A batch may record an acquisition mode, one homogeneous product and quantity, final USD paid, itemized cost components, optional original-currency reference values, invoice reference, and Receipt/Acquisition Group reference. Final USD paid is authoritative. Linked receipt groups are informational and never allocate shared shipping, tax, fees, or discounts automatically. Phase 3 does not create rip sessions, permanent card basis, sealed sales, or economics finalization.

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

When upgrading an older Dex database, Dex keeps the existing SAM compatibility behavior and applies the registered Phase 3 acquisition-fact migration once. Always test the release against a disposable legacy database copy before an operator-approved production upgrade; see [`MIGRATION_NOTES_v2.1-test.md`](MIGRATION_NOTES_v2.1-test.md).

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

The 35-test Phase 3 suite covers batch creation, bulk SKU assignment, reopening, images, grouped inventory, settings, exports, pricing, TCGplayer capacity, undo, outbound sale completion, Recycle Bin behavior, SAM source matching, transactional migrations, deterministic cent allocation, read-only legacy economics, acquisition validation, authoritative USD reconciliation, receipt groups, audit history, CSV compatibility, finalized-edit protection, runtime packaging, and disposable legacy migration compatibility.

The preserved Phase 2 restore point remains documented in [`RELEASE_CHECKPOINT_v2.1-test_PHASE2.md`](RELEASE_CHECKPOINT_v2.1-test_PHASE2.md). For the Phase 3 upload manifest, deployment warnings, rollback procedure, and validation steps, see [`RELEASE_CHECKPOINT_v2.1-test_PHASE3.md`](RELEASE_CHECKPOINT_v2.1-test_PHASE3.md). Migration behavior is documented in [`MIGRATION_NOTES_v2.1-test.md`](MIGRATION_NOTES_v2.1-test.md).
