# Release Checkpoint — DEX v2.4-test SAM Multi-Evidence Operator Trial v1a

Status: **GIT-READY DEPLOYMENT CANDIDATE — NOT DEPLOYED**  
Build identifier: `SAM-MULTI-EVIDENCE-BLIND-TRIAL-v1a-AUDIT-20260824`  
Runtime: `v2.4-test-sam-multi-evidence-operator-trial-v1a`  
Recommended image: `192.168.2.92:5000/apps/dex:v2.4-test-sam-multi-evidence-operator-trial-v1a`

## Scope

This checkpoint adds the accepted audited multi-evidence One Piece recognizer to the existing DEX SAM page as assisted intake. The result is immutable before operator interaction. The operator may confirm/correct family, request review/rescan, or mark the scan unidentified. Only explicit family confirmation/correction may update normal inventory identity. Exact printing remains operator-only.

The recognizer and its configuration are embedded under `sam_multi_evidence_frozen/` and verified against accepted fingerprint `dd899b6f73891252395ae9b8d09b43906ad15c656f0a0c739bd15a916c012493`. DEX uses an isolated process adapter solely to avoid Python module-name collisions. It does not change recognition behavior.

## Data and migration

Migration 0019 adds empty, append-only recognition-result, operator-decision, verified-truth, and forensic-delta structures. It performs no backfill and creates no batches, cards, sealed units, or identities. Migration execution is transactional where SQLite permits; forced-conflict rollback and repeat no-op are tested.

## Verification

- Python: 322/322 passed.
- Frontend: 27/27 regression files passed.
- JavaScript syntax: passed.
- Focused audited SAM integration: 23/23 passed.
- Frozen accepted recognizer/config changes: 0; 25/25 tracked components verified.
- False-authority increase: 0.
- Disposable startup and `/api/health`: HTTP 200 with the expected runtime.
- SQLite: integrity `ok`; migrations 0001–0019; empty startup created 0 batches, 0 cards, and 0 audited results.
- Dockerfile: includes every runtime sibling, frozen components, exact accepted trial dependencies, local Tesseract installation/check, build-time frozen hash assertion, and established receipt-orchestration smoke. An actual Docker build remains the normal Jenkins-host gate because Docker is unavailable on the packaging workstation.

## Known limitations

- One Piece only; it consumes an already indexed local One Piece reference library.
- Scans enter through existing DEX intake/card front-image storage; this checkpoint does not add a second upload system.
- Exact printing, treatment, rarity, pricing, listing, JANA, and reservations remain outside this integration.
- Operator corrections are not verified truth until independently reviewed and are never automatic training labels.
- The accepted frozen benchmark is preserved evidence; real assisted-use findings must be reviewed only after a closed operator batch.

## Rollback

Immediate application rollback is the currently live WOLFF/SAM Phase 2 image, expected tag `192.168.2.92:5000/apps/dex:v2.4-test-wolff-sam-phase2-20260822`; record its actual digest before cutover. Preserve a verified pre-0019 `/data` backup. First restore the prior image without touching storage. Never delete migration records or audited history. Restore storage only for a verified data-level problem with separate operator approval.

Production changes: **NONE — package only**.
