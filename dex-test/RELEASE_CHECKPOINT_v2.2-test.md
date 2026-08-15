# DEX v2.2-test Release Checkpoint

Release status: **RELEASE CANDIDATE — PRODUCTION APPROVAL NOT YET GRANTED**  
Scope cutoff: Inbound 2.0 Phase 3 Product Catalog + UPC Intake  
Runtime identity: `v2.2-test`  
Outstanding gate: physical keyboard-emulating barcode-scanner operator QA

This checkpoint packages the accepted implementation only. It does not authorize a production deployment, receipt/document work, or another development phase.

## Included Feature Scope

- Complete v2.1 Acquisition and Rip Batch Economics lifecycle through Phase 7C: acquisition facts, receipt groups, rip allocations, exact sealed units/sales, batch economics, corrections/dispositions, post-sale events, and read-only portfolio Operational Economics.
- Inbound 2.0 Phase 1 additive Acquisition/state/event foundation with immediate immutable draft identity and nullable future batch linkage.
- Inbound 2.0 Phase 2 guided, resumable three-screen New Acquisition wizard with Advanced / Legacy New Batch compatibility.
- Phase 2 UX revision and Accounting-by-Default happy-path behavior.
- Phase 3 local commercial-product catalog and UPC/EAN/GTIN/internal identifier architecture.
- No receipt/document storage, OCR/extraction, acquisition SAM integration, downstream batch projection, global Attention Center, or post-v2.2 feature.

## Major Architecture

- `app.py` remains the HTTP/API composition root and uses dedicated sibling services for migrations, economics, acquisition facts, rips, sealed inventory, corrections, post-sale events, portfolio reporting, Inbound 2.0, and product catalog/UPC behavior.
- SQLite remains the source of truth. Registered migrations execute through the versioned `schema_migrations` ledger and transactional savepoints.
- `dex_inbound.py` owns Draft Acquisition identity, lifecycle, autosave, reconciliation, confirmation, and line facts.
- `dex_catalog.py` owns commercial-product identity, barcode normalization/validation, catalog lookup, scan aggregation, learned mappings, and append-only mapping corrections.
- The frontend formats backend facts. It does not reproduce economics formulas.
- UPC identifies a commercial product only. Stable physical card SKUs and sealed-unit IDs remain separate established concepts.

## Accounting-by-Default Rules

- Operators provide authoritative source facts; DEX automates only deterministic, reproducible decisions.
- Automatic results are visible. Ambiguous, conflicting, incomplete, or exceptional reality becomes Needs Attention.
- Draft autosave never confirms authoritative financial facts or reconciliation.
- Missing authoritative cost remains Unknown; it is never converted to `$0.00`.
- Intentional `$0.00` acquisitions require the explicit zero-cost exception workflow.
- Material purchase discrepancy remains `$5 OR 2%`; `50%+` receives severe escalation.
- Product-line allocations disclose their method and remain non-authoritative until explicit confirmation.
- Confirmed landed cost reconciles exactly to final USD paid.

## Inbound 2.0 Behavior

- New Acquisition is the primary entry; Advanced / Legacy New Batch remains available.
- Draft Acquisition receives an immutable ID immediately and remains resumable.
- The guided flow captures product type, product/purchase details, and review with progressive disclosure.
- Clean single-line acquisitions use disclosed backend `SINGLE_LINE_100_PERCENT` allocation at final confirmation.
- Multi-line ambiguity, missing cost, explicit zero, and material discrepancies retain protected exception flows.
- `READY_FOR_INTAKE` remains the boundary. No downstream batch or sealed-unit projection occurs.

## Product Catalog + UPC Behavior

- Catalog products have immutable IDs, extensible class/subtype text, provenance, active state, and verification timestamps.
- UPC-A, EAN-13, and GTIN-14 check digits are validated. Identifiers are stored as text, raw scans are retained, and canonical GTIN-14 lookup preserves leading-zero identity.
- A normal keyboard-emulating scanner can submit with Enter. Recognized Pack/Sealed products populate visibly.
- Repeated scans of one product increment one acquisition line; different products create separate lines. Request IDs and acquisition revisions prevent retry duplication.
- Unknown identifiers are never guessed. Operators may search, identify only for the current acquisition, or explicitly Remember Mapping.
- Remembered mappings are operator-confirmed, not manufacturer-authoritative. Silent reassignment is blocked; correction requires reason/note and appends history.
- Product recognition creates no purchase cost, basis, batch, sealed unit, card, rip, sale, or portfolio fact.

## Migration Ledger

Migrations must remain ordered exactly as follows:

1. `0001_phase3_acquisition_facts`
2. `0002_phase4_rip_sessions`
3. `0003_phase5_sealed_inventory`
4. `0004_phase7a_corrections_dispositions`
5. `0005_phase7b_post_sale_events`
6. `0006_v22_phase1_inbound_acquisitions`
7. `0007_v22_phase2_manual_acquisition_wizard`
8. `0008_v22_phase2_ux_revision`
9. `0009_v22_phase3_product_catalog_upc`

Migration `0009` creates empty additive catalog, identifier, and identifier-event tables plus nullable acquisition-line catalog linkage. It guesses no historical mapping, creates no inventory, and changes no economics fact. Forced-failure testing confirms schema work and its ledger marker roll back together.

## Verification Results

- Full Python suite: **117 passed**.
- JavaScript syntax: passed.
- Existing self-contained frontend regression suites: passed.
- Packaged sibling-module imports: passed.
- Isolated packaged startup: passed; `/api/health` returned HTTP 200 and `v2.2-test`.
- Empty-startup boundary: no batch, card, or sealed-unit record was created.
- Migration order and presence `0001` through `0009`: passed.
- Forbidden/private-artifact scan: passed.
- Secret and machine-local absolute-path scan: passed; the inherited machine-specific visual screenshot harness was deliberately excluded.
- Workspace-to-package SHA-256 file matching and aggregate package digest: recorded during packaging verification.
- A Docker CLI/engine was not available in the packaging environment. Dockerfile COPY/import-assertion coverage and direct packaged imports passed; an actual image build remains mandatory post-upload.

## Known Limitations

- Physical barcode-scanner QA is still outstanding. Automated Enter-key and browser simulation passed, but a real USB/Bluetooth keyboard-emulating device must be verified before production approval.
- The product catalog is local; no manufacturer or external catalog synchronization exists.
- The mapping-correction dialog loads a bounded product list and may need in-dialog search for a much larger catalog.
- Existing acquisition lines intentionally retain the catalog identity captured at the time; mapping corrections affect future lookup.
- Receipt/document storage and intelligence, acquisition SAM integration, downstream projection, and the global Attention Center are not included.
- DEX has no application authentication and must remain private behind operator-controlled network boundaries.

## Docker and Deployment Warnings

- `VERSION`, `app.py`, the operator interface, and the Docker image label identify `v2.2-test`.
- Docker copies every sibling Python runtime module imported by `app.py` and runs build-time import assertions.
- Compose and Jenkins intentionally retain their existing `v2.0-test` image/container/tag/storage conventions. This checkpoint does not silently retarget those production conventions.
- Do not deploy this release candidate until physical-scanner QA passes and the operator separately approves the deployment target, image/tag, storage, backup, and rollback steps.
- Never test migrations against the live or irreplaceable inventory database. Use a timestamped disposable copy first.

## Exact Git Manifests

- Upload exactly the files listed in `GIT_UPLOAD_MANIFEST_v2.2-test.txt`.
- Exclude every file, directory, and pattern listed in `GIT_EXCLUSION_MANIFEST_v2.2-test.txt`.
- Upload the checkpoint contents, not its machine-local parent directory.

## Rollback Strategy

1. Preserve the current application image/source and a timestamped storage backup before any separately approved deployment.
2. If startup fails, stop only the failed candidate runtime; do not delete or restore live storage merely because the application failed.
3. Restore the last approved application checkpoint with its matching pre-upgrade storage copy.
4. Do not manually drop additive tables or delete migration-ledger rows.
5. If v2.2 acquisition/catalog facts were created, export/reconcile them before rolling back to software that cannot expose those records.

## Post-Upload Validation

1. Confirm every file in `GIT_UPLOAD_MANIFEST_v2.2-test.txt` is present and no exclusion-manifest item exists.
2. Confirm `VERSION` contains `v2.2-test` and Docker label metadata also says `v2.2-test`.
3. Run `python -m unittest discover -s tests -v` and require all 117 tests to pass.
4. Run the JavaScript syntax check and existing frontend regression scripts.
5. Build the image and confirm all Docker build-time import assertions pass.
6. Start only an isolated container or local runtime using empty disposable storage with scanner watching disabled.
7. Require `/api/health` to return HTTP 200 and runtime version `v2.2-test`.
8. Confirm the empty database has migration ledger entries `0001`–`0009` and zero batches, cards, and sealed units.
9. Run the disposable Phase 3 catalog scenario documented in the README.
10. Complete physical scanner QA before requesting production-release approval.

## Production Approval

**NOT YET APPROVED.** This is a Git release checkpoint/release candidate only. Physical barcode-scanner operator QA remains the exact outstanding gate.
