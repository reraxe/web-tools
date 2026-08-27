# Release Checkpoint — DEX v2.5.1-live

Status: **GIT-READY LIVE RELEASE CANDIDATE — NOT DEPLOYED**  
Build identifier: `DEX-v2.5.1-live-SAM-operator-fallback-20260827`  
Runtime: `v2.5.1-live`  
Target image: `192.168.2.92:5000/apps/dex:v2.5.1-live`

## Source

Baseline: accepted `DEX_v2.5-live_PROMOTION_WORKTREE`.

Hotfix source: accepted isolated `DEX_v2.5-test_SAM_OPERATOR_FALLBACK_HOTFIX_WORKTREE`.

The original v2.5-live package and fingerprints remain unchanged. The approved SAM hotfix was applied to byte-equivalent v2.5 TEST/LIVE baseline files, followed only by v2.5.1 runtime identity and release documentation updates.

## Scope

- Separate exact catalog-family availability from local reference-image availability.
- Permit trusted exact-number OCR to create an operator-reviewable frozen-catalog family suggestion.
- Preserve missing-reference reporting and unresolved exact printing.
- Add persistent Search Local Reference request/result/error states and selectable family-only results.
- Preserve TCGplayer bootstrap/reconciliation, quantity pools, audit behavior, WOLFF, JANA, economics, and all existing authority boundaries.

## Database

No migration was added. Migrations remain 0001–0020. Existing v2.5 business facts are preserved, and startup creates no bootstrap, inventory-pool, sale, or reconciliation rows.

## Acceptance

- Python: 348/348 passed.
- Frontend: 29/29 passed.
- Phase 7 SAM focused: 24/24 passed.
- JavaScript syntax: passed.
- Migration ledger: 20 migrations, ending at 0020.
- SQLite integrity: `ok`; foreign-key violations: zero.
- Existing data preservation: passed; startup-created v2.5 business rows: zero.
- Private/prohibited artifacts: zero.

Final fingerprints are recorded by `SOURCE_SHA256SUMS.txt`, `DEPLOY_SHA256SUMS.txt`, and `PACKAGE_AGGREGATE_SHA256.txt` without embedding a circular self-hash in this document.

## Deployment status

Not deployed. GitHub, Jenkins, Portainer, registry state, and LIVE storage remain operator-controlled.
