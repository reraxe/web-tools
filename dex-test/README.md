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
- `v2.2-test` adds Inbound 2.0. Phase 7 now connects One Piece Scan & Identify intake to conservative SAM recognition and human review while preserving every Phase 1–6 acquisition, catalog, document, receipt, routing, and **Advanced / Legacy New Batch** workflow.
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
- `dex_receipts.py`: Inbound 2.0 Phase 5 provider-neutral receipt extraction, candidate/provenance review, receipt-line matching, and deterministic allocation suggestions.
- `dex_batch_economics.py`: Phase 6 read-only authoritative batch/group rollups, stable order attribution, valuation coverage/freshness, reconciliation, and export rows.
- `dex_corrections.py`: Phase 7A append-only acquisition/basis corrections, reason-aware card/sealed dispositions, operational-loss entries, durable tombstones, and linked inverse reversals.
- `dex_post_sale.py`: Phase 7B immutable refunds, returns, chargebacks, fee/postage credits, sale corrections, effective financial facts, and exact inventory restoration.
- `dex_portfolio_economics.py`: Phase 7C read-only Finalized Economics portfolio rollup, exact order/item de-duplication, coverage/freshness, reconciliation, and export rows.
- `dex_inbound.py`: v2.2-test Inbound 2.0 draft acquisition identity, autosave, product lines, reconciliation gates, and append-only lifecycle events.
- `dex_intake_bridge.py`: v2.2-test Phase 6 request-safe acquisition-line routing, homogeneous batch projection, exact basis reconciliation, and downstream navigation facts.
- `dex_documents.py`: provider-neutral private source-document storage, validation, SHA-256 verification, retry/tombstone behavior, and metadata services.
- `dex_catalog.py`: v2.2-test commercial-product catalog, barcode normalization/validation, scan aggregation, learned mappings, and append-only mapping corrections.
- `dex_sam.py`: v2.2-test Phase 7 provider-neutral One Piece metadata cache, incremental local reference index, conservative recognition, review queues, idempotency, and durable evidence/history.
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

Inbound 2.0 creates an immediate immutable Draft Acquisition ID and autosaves non-authoritative facts and wizard position. Its three screens capture product choice, combined product/purchase details, and a human review. Pack and sealed lines can scan UPC-A, EAN-13, or GTIN-14 identifiers; unknown codes are never guessed. Phase 4 allows multiple private receipt/source artifacts from camera or file upload. DEX stores artifacts outside SQLite, records SHA-256 and metadata, and serves them through application routes rather than public provider links.

Phase 5 can privately extract a text layer from PDFs and propose merchant/date/order, transaction components, final paid, and receipt lines. High-confidence values may populate empty draft fields visibly; manual, accepted, confirmed, and authoritative facts are never silently overwritten. Images remain attachable and viewable, but image OCR is provider-ready rather than operational. The Review screen keeps candidate details collapsible, preserves Unknown values, exposes conflicts/classifications/matches, and can propose exact-cent multi-line landed cost using direct receipt merchandise plus shared components proportional to merchandise value. Final acquisition confirmation remains the sole authority gate. Extraction creates no batch, card, sealed unit, rip, sale, SAM fact, or portfolio result.

Collapsible sections retain the operator's expanded/collapsed choice during the working session across searches, autosaves, mutations, and result refreshes. Needs Attention can force the affected section open. Incomplete acquisitions with no protected downstream or confirmed draft allocation may be moved to Recycle Bin and restored; confirmed unlinked acquisitions may be canceled. DEX retains their facts and audit history and provides no permanent acquisition purge.

Phase 6 adds **Downstream Intake** after acquisition confirmation. Each confirmed product line projects into one existing-style homogeneous batch only when the operator previews and confirms a route. Pack/Sealed quantities may be split between Keep Sealed, Rip/Open, and Decide Later; Single Cards may be sent to Scan & Identify or left undecided. Undecided exact sealed units remain pending and cannot be sold. Rip routes create a draft rip but never activate scanner intake implicitly. Singles use the existing card intake and allocation workflow, with basis pending until that workflow is finalized. `READY_FOR_INTAKE` becomes `INTAKE_IN_PROGRESS` after a partial route and `INTAKE_COMPLETE` only after all quantities reconcile.

Phase 7 upgrades **SAM** for One Piece only. Physical scans are checked for quality and card-number evidence, narrowed against cached OPTCG metadata and a local image index, compared with watermark-tolerant visual fingerprints, and assigned `AUTO_MATCHED`, `NEEDS_REVIEW`, or `UNIDENTIFIED`. Pass 2 adds bounded, local-only Tesseract reading of the lower-right printed card number. Pass 3 stages those same twelve bounded recipes: two agreeing primary reads exit early, while unreadable or disagreeing evidence expands into the complete fallback. Multiple deterministic crop/preprocessing attempts must agree before OCR becomes evidence; OCR/visual conflicts, missing references, scan-quality warnings, and same-number variant ambiguity block automatic authority. If Tesseract is absent or cannot read a valid identifier, SAM falls back to the unchanged visual path. Only conservative automatic matches and explicit operator confirmations/corrections become trusted identity. The review surface keeps the scanned card beside SAM's best reference, shows concise card-number agreement and optional OCR path/timing diagnostics, alternates, and evidence, supports local **Find Match**, and preserves the original suggestion after correction. Recognition never assigns or changes acquisition cost, basis, sales economics, or portfolio totals.

Future Inbound/economics work follows the approved [Accounting-by-Default UX directive](DEX_ACCOUNTING_BY_DEFAULT.md): operators provide source facts, backend services perform deterministic accounting, visible routine results create no repetitive confirmation task, and ambiguous or exceptional reality becomes Needs Attention. The future Attention Center remains a design contract, not an implemented feature.

Phase 3 adds a separate **Acquisition Cost Facts** panel and editor. A batch may record an acquisition mode, one homogeneous product and quantity, final USD paid, itemized cost components, optional original-currency reference values, invoice reference, and Receipt/Acquisition Group reference. Final USD paid is authoritative. Linked receipt groups are informational and never allocate shared shipping, tax, fees, or discounts automatically.

Phase 4 adds **Rip Sessions & Cost Allocation**. Create a rip without activating it, explicitly select **Start intake**, scan/add its cards, then review equal or manual allocation and any unscanned bulk. Finalization requires all intended cards to be accounted for and an exact `$0.00` reconciliation. Finalized basis is locked; later changes append an audited correction instead of rewriting the original event. Batch completion and label printing remain independent.

Phase 5 adds exact **Sealed Unit Inventory** beneath trustworthy sealed acquisition batches. Each unit has a stable internal ID, stable sequence, deterministic landed basis, and one of four states: remaining, opened, sold, or adjusted. Creating a rip claims exact remaining units. The Outbound page provides separate Card Sale and Sealed-Product Sale workflows; mixed orders are rejected. Sealed orders store exact unit IDs, merchandise revenue, shipping collected, marketplace fees, actual postage, separately recorded marketplace tax, sold basis, net proceeds, and realized P/L. Sales provides an explicit **Details** view for sealed orders, including exact consumed unit IDs and Undo eligibility. Eligible Undo restores the exact units atomically while retaining the canceled order and event history.

Phase 6 adds a backend-calculated **Batch Economics** interface for authoritative economics batches. Its collapsible sections keep realized recovery/P&L separate from unrealized market/listed value, show valuation coverage and freshness, retain rip and sale drill-down history, reconcile cost and sealed quantities, and expose informational Receipt/Acquisition Group rollups without allocating shared charges. Unknown values remain unknown and make affected positions visibly incomplete. Batch economics, inventory, and sales CSVs include the calculation version and append new fields without changing prior column meanings.

Phase 7A adds **Corrections & Dispositions** to finalized or economically locked batches. Acquisition-cost changes, card/bulk basis transfers, duplicate/entry corrections, sealed quantity corrections, damage, loss, and disposal are immutable events layered over preserved source facts. Physical loss moves basis to a separately labeled operational-loss line; DEX makes no tax conclusion. Disposed cards retain durable tombstones and cannot be hard-purged. Restoration uses a linked inverse event, leaving the original event visible.

Phase 7B adds append-only post-sale events to every card or sealed order detail. Partial/full refunds, chargebacks, marketplace fee credits, actual postage refunds, and reviewed sale corrections change effective proceeds without rewriting the original order. Customer returns are separate physical events: DEX requires receipt and condition confirmation, restores the exact card or sealed identity at most once, and routes damaged returns to Excluded. Linked inverse events preserve both the original event and its reversal. Backend facts remain the only source for realized recovery and P/L.

Phase 7C adds **Operational Economics** as a read-only portfolio view. It includes Finalized Economics batches only and keeps legacy estimates and unfinished authoritative batches visibly separate. The backend derives acquisition cost, effective realized proceeds, active sold basis, realized P/L, operational loss, remaining known market/listed value, uncapped recovery, and current/projected positions from Phase 6–7B facts. Cross-batch orders use their original stable item attribution once; canceled orders and reversed event deltas are excluded by effective state. Coverage and freshness remain explicit, and unopened sealed value stays Unknown without an authoritative value fact. The portfolio CSV serializes this same payload.

The database is the source of truth. A complete inventory CSV can be downloaded at any time for reporting or an additional portable backup.

Card identification remains review-assisted. Phase 7 may automatically trust only strong multi-source One Piece matches; ambiguity and poor scans remain in review queues without blocking intake. Marketplace adapters and completed-sale collection stay separate from this release.

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

For Inbound 2.0 Phase 4 operator QA, use `python scripts/seed_v22_phase4_documents_demo.py --output <new-empty-path>`. It refuses existing paths and creates a disposable incomplete acquisition with two private source artifacts. Launch DEX with `DEX_DATA_DIR`, `DEX_DB_PATH`, and `DEX_DOCUMENT_DIR` pointed at that directory, then resume **Phase 4 Receipt QA Shop** in Inbound.

For Phase 5 operator QA, use `python scripts/seed_v22_phase5_receipt_demo.py --output <new-empty-path>`. It refuses existing paths and creates five disposable acquisitions: clean single-line, exact multi-line, manual conflict, incomplete/Unknown, and retryable image-extraction failure. Point all DEX data/document paths at that disposable directory; never use real inventory storage.

For Phase 6 operator QA, use `python scripts/seed_v22_phase6_intake_bridge_demo.py --output <new-empty-path>`. It refuses existing paths and creates four disposable acquisitions covering a `$330.00` three-box split, a partial sealed line plus completed Pack Product line, acquired-singles scanning, and idempotent retry. Point every DEX data path at that disposable directory; never use real inventory storage.

For Phase 7 SAM operator QA, use `python scripts/seed_v22_phase7_sam_demo.py --output <new-empty-path>`. It creates disposable DEX storage plus an external disposable One Piece reference library and seeds five physical cards: two automatic matches (including SAMPLE-watermark tolerance and provider-missing fallback), two review cases (variant ambiguity and an intentionally wrong top suggestion), and one unidentified poor scan. Launch with `DEX_DATA_DIR` and `DEX_DB_PATH` pointed at the created storage and `DEX_ONE_PIECE_REFERENCE_DIR` pointed at its reported reference directory.

SAM card-number OCR requires a local Tesseract 5 executable with English data. The Docker image installs `tesseract-ocr` and `tesseract-ocr-eng`. Native development can set `DEX_TESSERACT_CMD` to the executable path; `DEX_SAM_OCR_ENABLED=0` disables OCR explicitly. No physical image or derived crop leaves the machine. OCR is optional at runtime: missing/unavailable OCR is recorded as such and visual recognition continues. See [`SAM_REAL_WORLD_VALIDATION_OP16_OCR_PASS2_2026-08-15.md`](SAM_REAL_WORLD_VALIDATION_OP16_OCR_PASS2_2026-08-15.md) for the original OCR baseline and [`SAM_REAL_WORLD_VALIDATION_OP16_OCR_PASS3_2026-08-15.md`](SAM_REAL_WORLD_VALIDATION_OP16_OCR_PASS3_2026-08-15.md) for the unchanged five-scan staged-latency validation.

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

When upgrading an older Dex database, Dex keeps the existing SAM and Phase 3–7C compatibility behavior. v2.2-test adds migrations `0006` through `0014`. Migration `0014_v22_phase7_sam_recognition` adds empty metadata-cache, reference-index, recognition, candidate, and decision ledgers plus nullable card recognition fields. It does not backfill or alter historical identities, batches, inventory, or economics. Always test against a disposable Phase 7C database copy before an operator-approved deployment; see [`MIGRATION_NOTES_v2.2-test.md`](MIGRATION_NOTES_v2.2-test.md).

### SAM source database

Put One Piece reference images under the directory configured by `DEX_ONE_PIECE_REFERENCE_DIR` (it defaults to `DEX_SOURCE_DB_DIR`). Filenames such as `OP16-067.png`, `EB01-001.jpg`, or `PRB02-018.png` provide strong card-number evidence. Originals remain unchanged and outside SQLite; DEX stores only metadata, hashes, provenance, and derived visual fingerprints.

After adding or replacing files, open SAM and run **Index references**. Indexing is incremental: unchanged SHA-256 files are skipped and changed files are reindexed. OPTCG structured metadata refresh is optional; recognition and Find Match continue with cached/local evidence during provider outages. DEX never sends physical scans or local reference images to OPTCG.

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
| `DEX_ONE_PIECE_REFERENCE_DIR` | value of `DEX_SOURCE_DB_DIR` | Phase 7 read-only One Piece reference-image root |
| `DEX_SAM_OCR_ENABLED` | `1` | Set to `0` to disable local card-number OCR while retaining visual SAM |
| `DEX_TESSERACT_CMD` | detected from `PATH` | Optional explicit path to the local Tesseract executable |
| `DEX_OPTCG_API_BASE` | `https://optcgapi.com` | Structured One Piece metadata provider base URL; no images are transmitted |
| `DEX_OPTCG_TIMEOUT` | `8` | Metadata provider request timeout in seconds |
| `DEX_WATCH_INBOUND` | `1` | Enables automatic folder intake |
| `DEX_SCAN_INTERVAL` | `5` | Folder check interval in seconds |
| `DEX_SEED_DEMO` | `0` | Adds sample records to an empty database |
| `DEX_TIMEZONE` | `America/New_York` | Business dates used for SKUs and exports |
| `DEX_TCG_CAPACITY` | `500` | Initial TCGplayer listing capacity |

## Tests

```bash
python -m unittest discover -s tests -v
```

The 175-test Python suite covers all prior behavior plus transactional Phase 7 migration rollback, provider normalization/failure fallback, metadata provenance, incremental and duplicate-aware indexing, conservative confidence/variant handling, SAMPLE/rotation/crop tolerance, strict OCR normalization, bounded deterministic OCR consensus, staged early exit and full disagreement escalation, unreadable/unavailable OCR fallback, OCR/visual conflict and missing-reference blocking, variant protection, review decisions/history, retry protection, queue counts, provenance/economics boundaries, and a 5,000-reference performance case. Thirteen frontend contract/regression files cover the SAM review/correction success and rejection paths plus every prior guided-wizard, receipt/catalog/document, intake, batch, Sales, viewport, and backend-only economics path; the visual browser suite also renders desktop and mobile without console errors.

The immutable v2.1 Phase 7C restore point and accepted v2.2 phase checkpoints remain preserved separately. The current consolidated handoff is [`RELEASE_CHECKPOINT_v2.2-test_RC2_POST_SAM.md`](RELEASE_CHECKPOINT_v2.2-test_RC2_POST_SAM.md). RC2 is a post-SAM hardening candidate only; production approval remains blocked on the documented Pass 4, physical barcode-scanner, deployment-host Docker-build, and broader operator stress gates.
# RC3 Operator Trial checkpoint

This source package is the **DEX v2.2-test RC3 — Operator Trial** release candidate. DEX means **Digital Encyclopedia Xchange**. Its recognition subsystem is **SAM — Search And Match**. The reserved future subsystem names are **JANA — Judgment, Analytics & Navigation Assistant** and **STRIX — Storage, Transfer, Repository & Information Xchange**.

Production deployment is **not approved**. RC3 preserves the authoritative v2.2-test application through Inbound 2.0 and SAM human review. The isolated research modules under `research/` are shadow-only: they do not replace SAM, grant recognition authority, route geometry automatically, or use TCGplayer metadata as physical-card evidence.

The One Piece reference images are external and are not included. Set `DEX_ONE_PIECE_REFERENCE_DIR` to the operator-controlled reference-library directory at runtime. Do not commit that machine-local path or the library itself.
