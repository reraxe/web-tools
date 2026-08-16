# DEX v2.2-test Release Checkpoint

Release status: **RELEASE CANDIDATE — PRODUCTION APPROVAL NOT YET GRANTED**  
Scope cutoff: Inbound 2.0 Phase 7 SAM Recognition + Human Review  
Runtime identity: `v2.2-test`  
Outstanding gate: disposable and representative physical One Piece scanner/operator QA

This checkpoint packages the approved implementation only. It does not authorize production deployment, JANA, marketplace/listing work, cross-TCG recognition, a global Attention Center, autonomous retraining, or another development phase.

## Included Feature Scope

- Complete preserved v2.1 Acquisition and Rip Batch Economics lifecycle through Phase 7C.
- Inbound 2.0 Phase 1 Draft Acquisition/state/event foundation; Phase 2 guided wizard, Accounting-by-Default UX, and legacy compatibility; Phase 3 Product Catalog/UPC; Phase 4 private documents; Phase 5 receipt intelligence; and the pre-phase disclosure/acquisition-safety hotfix.
- Phase 6 explicit downstream routing into established homogeneous batches, stable sealed units, rip/open, and acquired-singles intake.
- Phase 7 One Piece-only conservative SAM recognition, OPTCG structured metadata cache, incremental local reference index, non-blocking human review, Find Match, and durable evidence/decisions.

## Architecture and Authority Boundaries

- `app.py` remains the HTTP/API composition root. Dedicated sibling modules own migrations, economics, acquisition, catalog, documents, receipts, intake routing, and SAM recognition.
- SQLite remains the source of truth. Registered migrations execute through the ordered `schema_migrations` ledger and transactional savepoints.
- Frontend code formats backend facts. It does not reproduce acquisition/economics or recognition-confidence formulas.
- UPC identifies a commercial product; stable sealed-unit IDs and card SKUs identify physical inventory.
- SAM enriches existing physical card records. It does not create a parallel inventory engine or assign/change acquisition cost, basis, rip economics, sales economics, or portfolio totals.
- Missing financial/identity facts remain Unknown. Only explicit acquisition confirmation or approved conservative/operator SAM decisions cross their respective authority gates.

## Inbound 2.0 and SAM Behavior

- Draft Acquisition receives an immutable ID immediately, autosaves non-authoritative progress, and remains resumable.
- Confirmed acquisition lines route only through explicit Phase 6 preview/confirmation into the established batch model.
- One Piece scans are narrowed using TCG/context, scan quality, normalized card-number evidence, cached/local metadata, and bounded visual reference families.
- `AUTO_MATCHED` requires strong multi-source agreement and no unresolved ambiguity. Otherwise results become `NEEDS_REVIEW` or `UNIDENTIFIED` without blocking intake.
- Operators can confirm, Find Match and correct with reason/note, or leave unidentified. Original SAM suggestions, alternates, evidence, provider/reference provenance, and engine/rules/index versions remain durable.
- OPTCG requests contain structured metadata only. Physical scans and local reference images are never transmitted.

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
10. `0010_v22_phase4_source_documents`
11. `0011_v22_phase5_receipt_intelligence`
12. `0012_v22_prephase_ux_safety_hotfix`
13. `0013_v22_phase6_downstream_intake_bridge`
14. `0014_v22_phase7_sam_recognition`

Migration `0014` creates empty cache/index/recognition/candidate/decision infrastructure and nullable card recognition links. It stores no image blobs, guesses no historical identity, creates no inventory, and changes no economics fact. Forced-failure testing confirms the schema work and ledger marker roll back together.

## Verification Results

- Full Python suite: **167 passed** in 16.415 seconds after the Phase 7 correction hotfix.
- JavaScript syntax: passed.
- Frontend contract/regression files: **13 passed**, including the executable SAM correction success/rejection path and live authoritative batch-detail renderer.
- Visual browser suite: desktop and mobile rendered without console errors.
- Phase 7 performance: 5,000 references **54.42 ms**; exact reference search **2.67 ms**; 5,000 metadata-cache rows **33.40 ms** / exact lookup **0.05 ms**; 1,000-card review queue **227.44 ms**.
- Disposable operation timings: six-image initial index **39.85 ms**, unchanged incremental index **3.49 ms**, four-card metadata refresh **0.22 ms**, and per-card recognition **3.51–24.12 ms**.
- Migration order/presence `0001` through `0014`, legacy no-backfill behavior, idempotency, and forced rollback: passed.
- Dockerfile copies/import-checks every sibling runtime module, including `dex_sam.py`.
- Final Git package verification records runtime imports, isolated `/api/health`, empty-startup boundaries, forbidden/private-artifact scanning, secret/path scanning, and workspace-to-package SHA-256 equality.

## Known Limitations

- One Piece recognition only. Other TCGs require separately approved provider/rule/reference adapters.
- Local OCR is optional and not bundled; without it, printed-number evidence uses existing intake facts or filenames and more scans may require review.
- Visual recognition uses conservative perceptual/frame fingerprints, not a trained embedding or grading/counterfeit system.
- Metadata refresh is operator-triggered for requested card numbers; no scheduled whole-provider synchronization exists.
- Physical scanner accuracy, false-positive rate, and variant behavior require representative operator QA.
- DEX has no application authentication and must remain on an operator-controlled private network.

## Docker and Deployment Warnings

- `VERSION`, application runtime, operator UI, and Docker image label identify `v2.2-test`.
- Compose/Jenkins deployment conventions, ports, volumes, container names, and production tags remain unchanged and operator-controlled.
- The configured One Piece reference folder is private runtime data and must not be packaged into Git. Prefer a read-only mount.
- Never test migrations against live or irreplaceable inventory. Use a timestamped disposable copy first.
- This checkpoint is not production authorization.

## Exact Git Manifests

- Upload exactly the files listed in `GIT_UPLOAD_MANIFEST_v2.2-test.txt`.
- Exclude every file, directory, and pattern listed in `GIT_EXCLUSION_MANIFEST_v2.2-test.txt`.
- Upload the checkpoint contents, not its machine-local parent directory.

## Rollback Strategy

1. Preserve the accepted Phase 6 application checkpoint and a matching pre-`0014` storage copy.
2. If startup fails, stop only the failed candidate runtime; do not delete or restore live storage merely because application startup failed.
3. Restore the prior application and its matching database/storage copy together.
4. Do not manually drop additive tables, null recognition links, erase evidence, or delete migration-ledger rows.
5. The external reference library is unchanged by DEX and requires no application rollback.

## Post-Upload Validation

1. Confirm the upload/exclusion manifests exactly.
2. Confirm `VERSION`, `/api/health`, and Docker metadata report `v2.2-test`.
3. Run all 167 Python tests, JavaScript syntax checks, and frontend regressions.
4. Build the image and require every build-time runtime-module import assertion.
5. Start only an isolated runtime on empty disposable storage with scanner watching disabled.
6. Require `/api/health` HTTP 200, ordered migrations `0001`–`0014`, and zero startup-created batches/cards/sealed units/recognition jobs.
7. Run `scripts/seed_v22_phase7_sam_demo.py` and complete the five Phase 7 review scenarios in the dedicated checkpoint document.
8. Complete representative physical One Piece scanner QA before requesting production approval.

## Production Approval

**NOT YET APPROVED.** This is a Git release checkpoint/release candidate only. Phase 7 operator QA is the exact current gate.
