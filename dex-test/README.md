# Dex

Dex is a private, single-user TCG inventory system for individual physical cards. It tracks inbound batches, front/back scans, unique SKUs, 2 x 1 QR labels, grouped inventory, market-price ranges, drawer locations, and multi-card outbound orders.

Current release: **Dex v1.1a-test**

## Release policy

- Stable releases are preserved and are never overwritten by development work.
- `v1.1-test` consolidates the first quality-of-life work planned through the former v1.4 roadmap.
- `v1.1a-test` adds inventory safety and intake corrections discovered during live 29-card batch testing.
- Automatic card recognition and catalog intelligence begin in `v2.0-test`.
- Test releases use a separate Docker tag, container, port, and storage volume so test data cannot affect stable inventory.
- After testing is approved, the same release is promoted from `v1.1a-test` to `v1.1a-stable`.
- Urgent fixes to a stable release use a patch version such as `v1.0.1-test` before promotion to `v1.0.1-stable`.

Issues found during the current pilot are tracked in [`V1.1_TEST_BACKLOG.md`](V1.1_TEST_BACKLOG.md).

## Repository layout

- `static/index.html`: browser interface.
- `static/app.js` and `static/styles.css`: frontend behavior and styling.
- `app.py`: web API, scanner-folder watcher, and SQLite access.
- `Dockerfile`: production image build.
- `Jenkinsfile`: Docker build and container smoke test.
- `compose.yaml`: persistent home-server deployment.

`index.html` is packaged inside the image, but Dex is not a static-only website. The Python service supplies the shared database, images, scanner intake, labels, and outbound records.

## MVP workflow

1. Create an inbound purchase batch for a booster box, packs, purchased singles, a trade, or existing inventory.
2. Add front/back scans in the browser, or save scanner images into that batch's watched folder.
3. Select one image pair or a complete scan batch; Dex pairs files and immediately assigns a unique SKU to every physical card.
4. Review and edit cards from the multi-card batch grid.
5. Finish the batch and print all queued 2 x 1 labels.
6. Scan sleeve QR codes into an eBay or TCGplayer outbound order.

The database is the source of truth. A complete inventory CSV can be downloaded at any time for reporting or an additional portable backup.

Card identification and completed-sale pricing are review-assisted in this MVP. The database and UI are ready for catalog and marketplace adapters; OPTCG API matching and automated completed-sale collection can be connected after access and rate limits are confirmed.

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

## Debian Docker deployment

No server-specific details are needed to build Dex. On the Debian server:

```bash
git clone <your-repository-url> dex
cd dex
mkdir -p storage scanner-inbox
docker compose up -d --build
```

Compose defaults to Debian user/group `1000:1000`. If the server account uses different IDs, put `PUID` and `PGID` in a `.env` file before starting Dex.

The included test compose file publishes Dex at `http://SERVER-IP:8082` and uses separate test storage. Keep the port blocked from the public internet. Earlier releases remain untouched on their existing ports and storage.

The persistent folders are:

- `storage/`: SQLite database, original card images, and backups.
- `scanner-inbox/`: scanner drop folders created for open batches.

The SQLite database is stored at `storage/dex.db` on the host through the `/data` container volume. Rebuilding or replacing the image does not remove inventory data.

### Test with a copy of v1.1 data

Stop the `v1.1-test` container or create a consistent SQLite backup before copying its data. Copy the complete `storage-v1.1-test` directory to `storage-v1.1a-test`, then start this compose file. Dex adds the new columns automatically while preserving cards, SKUs, images, batches, and sales. The test remains isolated on port `8082`.

## Jenkins image build

Point a Pipeline job at this GitHub repository. Jenkins reads `Jenkinsfile`, builds the image, starts a temporary container, checks `/api/health`, and tags successful `main` builds as `dex:latest`.

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
| `DEX_WATCH_INBOUND` | `1` | Enables automatic folder intake |
| `DEX_SCAN_INTERVAL` | `5` | Folder check interval in seconds |
| `DEX_SEED_DEMO` | `0` | Adds sample records to an empty database |
| `DEX_TIMEZONE` | `America/New_York` | Business dates used for SKUs and exports |
| `DEX_TCG_CAPACITY` | `500` | Initial TCGplayer listing capacity |

## Tests

```bash
python -m unittest discover -s tests -v
```

The automated test covers batch creation, bulk SKU assignment, reopening, images, grouped inventory, settings, exports, pricing, TCGplayer capacity, undo, and outbound sale completion.
