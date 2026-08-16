# DEX v2.2-test RC2 — Post-SAM Hardening Candidate

Release status: **RELEASE CANDIDATE — PRODUCTION NOT APPROVED**  
Runtime identity: `v2.2-test`  
Packaging cutoff: 2026-08-16  
Change class: consolidated Git-ready checkpoint; no application behavior change

This RC2 checkpoint consolidates the accepted DEX implementation through Inbound 2.0, Accounting-by-Default, Product Catalog + UPC, Source Documents, Receipt Intelligence, the Pre-Phase UX/Safety Hotfix, the Downstream Intake Bridge, SAM Recognition + Human Review, the Confirm Correction hotfix, local card-number OCR, and OCR Pass 3 staged/early-exit optimization.

Packaging RC2 changed no application behavior, API, schema, migration, recognition rule, confidence threshold, economics calculation, Compose/Jenkins convention, port, volume, container name, or production configuration. It does not authorize deployment or another feature phase.

## Included architecture and authority boundaries

- The preserved v2.1 economics lifecycle remains the authoritative acquisition, rip, sealed-unit, sale, correction, post-sale, and portfolio model.
- Inbound 2.0 creates resumable acquisitions, applies Accounting-by-Default, learns commercial products/UPC mappings, retains private source-document metadata, proposes receipt facts non-authoritatively, and projects confirmed lines through explicit downstream routing.
- SAM remains One Piece-only. It proposes or applies card identity under conservative backend rules and append-only human review; it does not create inventory or change acquisition cost, basis, rip economics, sales economics, market/listed values, or portfolio calculations.
- Local OCR uses Tesseract 5 with bounded deterministic crops and staged execution. Two independent valid reads are required for early exit; disagreement reaches the complete bounded fallback. OCR/visual conflict, missing-reference, variant, quality, confidence, and margin safeguards remain unchanged.
- Original SAM suggestions and evidence remain immutable. Operator corrections record the selected reference separately and fail visibly rather than silently.

## Migration ledger

The registered and disposable-startup ledger order was verified exactly:

1. `0001_phase3_acquisition_facts`
2. `0002_phase4_rip_sessions`
3. `0003_phase5_sealed_inventory`
4. `0004_phase7a_corrections_dispositions`
5. `0005_phase7b_post_sale_events`
6. `0006_v22_phase1_inbound_acquisitions`
7. `0007_v22_phase2_manual_acquisition_wizard`
8. `0008_v22_phase2_ux_revision`
9. `0009_v22_phase3_product_catalog_upc`
10. `0010_v22_phase4_source_documents`
11. `0011_v22_phase5_receipt_intelligence`
12. `0012_v22_prephase_ux_safety_hotfix`
13. `0013_v22_phase6_downstream_intake_bridge`
14. `0014_v22_phase7_sam_recognition`

Startup on empty disposable storage created only schema/ledger infrastructure. It created zero acquisitions, batches, cards, sealed units, sales, reference records, recognition jobs, or decisions. SQLite integrity returned `ok`.

## Preserved SAM validation reports

The accepted reports are packaged unchanged:

| Report | SHA-256 |
| --- | --- |
| `SAM_REAL_WORLD_VALIDATION_OP16_2026-08-15.md` | `B2EBD6ADA7F498780F0CF9FD338C3B5EFAC2CC24B27029A05AC65D979CDB26A0` |
| `SAM_REAL_WORLD_VALIDATION_OP16_OCR_PASS2_2026-08-15.md` | `73B9F9CFDCEA93503FA72AE66D53460B98570DC55CCA848660F05D37D4DDAC08` |
| `SAM_REAL_WORLD_VALIDATION_OP16_OCR_PASS3_2026-08-15.md` | `20CD13A73822FE106F0A3671BC39BCAE33AFA86AD9841E268A3DEAAFC4269730` |

Pass 3 retained 5/5 correct top candidates, 5/5 OCR reads, two correct automatic matches, three Needs Review, zero Unidentified, and zero false automatic matches while reducing mean latency to 750.56 ms. This five-card result is a controlled baseline, not production accuracy approval.

## External One Piece reference library

The operator-configured external reference-library path is supplied through `DEX_ONE_PIECE_REFERENCE_DIR`. The machine-specific path is not recorded in this package or hardcoded in application source.

Accepted corpus facts from the separate read-only audit:

- 61 folders and 5,594 files totaling 474,168,085 bytes;
- 5,593 supported/readable reference images and one unsupported `EB01.zip`;
- 5,590 identifiable assets, 2,838 unique normalized card numbers, and three unresolved Don images;
- zero exact SHA-256 duplicate groups;
- 2,747 multiple-reference families and 1,495 likely visual-near-duplicate groups;
- first index 27.868 seconds, unchanged second index 3.296 seconds with all 5,593 references skipped;
- reference search median 3.98 ms, p95 5.77 ms, and maximum 6.95 ms in the accepted measurement.

The 5,593 images, external index database, caches, audit manifests, and operator source material are **not packaged**. Docker builds copy application files only. A deployment would require a separately approved read-only bind mount; this checkpoint does not modify Compose.

## External Pass 4 validation corpus

The external Pass 4 validation location contains operator-owned physical scans, evaluation-only ground truth, identity-neutral blind staging, and results. None of those artifacts are packaged. The prepared initial five-card corpus passed its preflight with five hashes verified and recognition explicitly not run.

No physical validation scan, `ground_truth.csv`, blind key, staged image, readiness artifact, or Pass 4 result is packaged. Pass 4 remains a separate operator-approved validation activity.

## RC2 verification results

- Full Python regression suite: **175 passed in 22.050 seconds**.
- `static/app.js` and all frontend test files: JavaScript syntax passed.
- Frontend contract/regression suite: **13/13 passed**, including the seeded live authoritative batch-detail renderer and SAM correction success/failure execution path.
- Runtime sibling modules imported by `app.py`: **16/16 present** and copied/import-checked by the Dockerfile.
- Runtime/version identity: `VERSION`, `app.APP_VERSION`, Docker label, and isolated health response identify `v2.2-test`.
- Migrations: source registry and disposable SQLite ledger match `0001` through `0014` exactly.
- OCR/runtime: `dex-one-piece-card-number-ocr-v2-staged`; conservative rules remain `sam-conservative-2026-08-15-v1`.
- Local packaging check detected Tesseract `v5.5.0.20241111`.
- Dockerfile installs `tesseract-ocr` and `tesseract-ocr-eng`, runs `tesseract --version`, configures `/usr/bin/tesseract`, imports `dex_sam`, and includes every sibling runtime module.
- Browser rendering passed at desktop and mobile viewports with no browser-console errors.
- An isolated startup from the allowlisted package returned HTTP 200 from `/api/health`, identified itself as `v2.2-test`, applied migrations `0001` through `0014` in order, passed SQLite integrity checking, and created no batches, cards, sealed units, sales, acquisitions, or SAM records.
- The package/privacy gate found zero manifest differences, zero source-hash mismatches, zero forbidden/private artifacts, zero credential signatures, and zero machine-user absolute paths. Final package hashes are recorded in `SHA256SUMS.txt` and the packaging completion report.

The first Python invocation inherited the real external reference path and caused one legacy rescan test to index the full 5,593-image library inside its five-second timeout. The complete suite passed after removing that single external variable from the test process so the test used its intended disposable fixture. No source or test change was required. Future automated test runners should explicitly isolate `DEX_ONE_PIECE_REFERENCE_DIR`.

## Known limitations and technical debt

- Production accuracy is unproven beyond the controlled five-card OP16 baseline.
- One Piece only; no cross-TCG recognition adapter is approved.
- Visual fingerprints are conservative matching evidence, not grading or counterfeit detection.
- The legacy combined source-rescan endpoint also triggers the Phase 7 reference index; test environments must override the external reference path with a disposable fixture.
- Provider metadata coverage and local reference existence remain separate; provider absence must not remove local references.
- DEX has no application authentication and must remain on an operator-controlled private network.
- The actual Linux/Docker build and Tesseract runtime inside the image remain deployment-host gates.

## Outstanding release gates

Production remains blocked until all of the following are accepted:

1. Pass 4 preliminary 15-card full-library validation.
2. Pass 4 25–50 card stress validation.
3. Representative physical barcode-scanner QA.
4. Actual Docker image build on the deployment host.
5. Broader end-to-end operator stress testing.

## Deployment warnings

- **Do not deploy this checkpoint merely because packaging passed.** Production status is NOT APPROVED.
- Never upload databases, live inventory, source/reference images, scanner folders, receipt artifacts, environment files, credentials, logs, caches, or the Pass 4 corpus.
- Compose/Jenkins conventions still identify historical container/tag defaults and remain operator-controlled. RC2 does not silently change those deployment conventions.
- Rehearse migrations only against disposable or copied legacy storage. Do not test against the live SQLite database.
- Preserve the external reference library as read-only and keep source documents/storage matched with their database metadata.

## Rollback

1. Preserve this RC2 checkpoint and the prior accepted Phase 7 Correction Hotfix/Pass 3 checkpoint independently.
2. Before an approved deployment, create a verified timestamped storage backup/copy and record the currently deployed application/image identifier.
3. If candidate startup fails, stop only the failed candidate and restore the prior application/image. Do not delete, recreate, or replace production storage merely because startup failed.
4. If migration `0014` or any earlier additive migration was applied and rollback is required, restore the matching pre-upgrade database/storage copy together with the prior application. Do not manually drop tables, erase recognition history, null links, or delete migration-ledger rows.
5. External reference and Pass 4 corpus files are independent operator assets and require no application rollback.

## Exact upload and post-upload validation

- Upload only files listed in `GIT_UPLOAD_MANIFEST_v2.2-test_RC2.txt`.
- Exclude everything listed in `GIT_EXCLUSION_MANIFEST_v2.2-test_RC2.txt`.
- Verify every uploaded file against `SHA256SUMS.txt`.
- Run the full Python and frontend suites in a clean environment with the reference path pointed to a disposable fixture.
- Build the actual image on the approved host and require every Tesseract/runtime assertion.
- Start against empty disposable storage first; require `/api/health` HTTP 200, `v2.2-test`, migrations `0001`–`0014`, and zero startup-created business/recognition facts.
- Do not request production approval until every outstanding gate above passes.

## Production approval

**NOT APPROVED.** RC2 is a post-SAM hardening release candidate and Git-ready restore/checkpoint package only.
