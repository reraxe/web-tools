# DEX v2.2-test RC3 — Operator Trial

Release status: **RELEASE CANDIDATE — PRODUCTION NOT APPROVED**  
Runtime identity: `v2.2-test`  
Checkpoint role: manual end-to-end operator trial with four newly purchased One Piece OP13 booster packs.

## System names

- **DEX:** Digital Encyclopedia Xchange
- **SAM:** Search And Match
- **JANA:** Judgment, Analytics & Navigation Assistant
- **STRIX:** Storage, Transfer, Repository & Information Xchange

## Authoritative scope

RC3 consolidates the accepted application through:

- Inbound 2.0 acquisition workflow and Accounting-by-Default controls
- Product Catalog and UPC intake
- source documents and receipt intelligence
- pre-phase disclosure-state and acquisition-safety improvements
- Downstream Intake Bridge
- SAM recognition, human review, and Confirm Correction hotfix
- local Tesseract card-number OCR with staged/early-exit optimization
- existing scanner, rip, inventory, sealed-unit, sales, correction, post-sale, and Phase 7C Operational Economics workflows

No application behavior, schema, authority threshold, economics rule, or deployment convention was changed while assembling RC3.

## Migration ledger

RC3 contains the established additive migration chain, in order:

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

Packaging adds no migration. Migration execution remains transactional where SQLite permits and records completion in `schema_migrations` only after success.

## Shadow-only research

The following are included only as isolated source, tests, design material, or tooling:

- SAM Challenger v1 shadow reporting support
- SAM Challenger v2 design/harness
- Geometry Challenger v1
- TCGplayer Commercial Printing Catalog Bridge v1

Authoritative SAM v1 behavior remains unchanged. Printing authority is disabled. Geometry is not routed automatically. TCGplayer catalog information is descriptive only and cannot establish recognition authority.

## External data boundary

The 5,593-image One Piece reference library is not packaged. Configure it with `DEX_ONE_PIECE_REFERENCE_DIR` at runtime. Pass 4, Variant Gauntlet, and Geometry Gauntlet scans, ground truth, blind staging, result databases, and source artifacts are also excluded.

## Verification summary

- Python application regression: **180 tests passed** in the isolated test environment.
- Environment-dependent diagnostic: an earlier unrestricted run timed out in `test_v20_sam_source_scan_and_match` while using local OCR/full-reference context; the server finished just after the fixed five-second client timeout. The full isolated rerun passed. This is recorded as an environment-dependent timeout, not silently counted as a pass.
- Shadow research tests: Challenger v2 **4/4**, Geometry Challenger v1 **11/11**, TCGplayer bridge **11/11**.
- JavaScript syntax: **16 files passed**.
- Offline frontend regressions: **13/13 passed**.
- Seeded live batch-render regression: recorded in `PACKAGE_VERIFICATION_RC3.md`.
- Disposable empty startup, health, migration, integrity, and zero-record checks: recorded in `PACKAGE_VERIFICATION_RC3.md`.
- Docker CLI was unavailable on the packaging workstation; no Docker image build is claimed.

## Known limitations and outstanding gates

- RC3 is test software and is not v2.2-stable.
- Physical barcode-scanner behavior remains an operator/deployment-host validation gate.
- The full reference library is an external operator-managed dependency.
- SAM Challenger v1/v2, Geometry Challenger v1, and TCGplayer bridge remain experimental and non-authoritative.
- Printing/variant authority remains unresolved and disabled.
- An actual Docker image build with Tesseract must run on the deployment host.
- The OP13 four-pack workflow and broader end-to-end operator stress test remain outstanding.

## Rollback

The RC2 checkpoint remains the known-good pre-RC3 application restore point. Stop RC3, restore the matching RC2 application checkpoint, and—if the operator trial created real data—restore the matching pre-trial database/storage backup. Never delete migrations or authoritative records from a live database by hand.

## Trial sequence

After release verification, the operator may manually exercise:

`New Acquisition → OP13 booster packs × 4 → receipt/purchase details → Accounting-by-Default confirmation → Continue Intake → Rip/Open → physical scanning → SAM → Human Review → inventory → basis/economics verification`

No trial acquisition is seeded or fabricated by this package.

