# DEX v2.4-test WOLFF + SAM Phase 2 release checkpoint

Status: **VERIFIED FROZEN BASELINE — READY FOR OPERATOR DEPLOYMENT GATES**  
Release identifier: `DEX-v2.4-test-WOLFF-SAM-Phase2-development-baseline-20260822`  
Runtime version: `v2.4-test`  
Recommended immutable image tag: `192.168.2.92:5000/apps/dex:v2.4-test-wolff-sam-phase2-20260822`

This checkpoint packages the frozen 2026-08-22 baseline without changing application behavior, schema, recognition rules, economics, or deployment configuration. It does not include SAM Vision Intake, dense retrieval, DINOv2, FAISS, learned geometry, or any other external POC.

## Frozen fingerprint

- Protected file count: **247**
- Authorized fingerprint: `3c22c2aa997315e4874e466fc8a99c788cd58f89e9bc7f3f88aeb5f86040d32a`
- Reproduced using the exact historical PowerShell culture-aware, case-sensitive sort used at freeze: **PASS**
- Frozen worktree modified during release preparation: **NO**

The baseline document describes ordinal sorting, but ordinal sorting produces `041de488c33a82b1709452e297ba0ef0c366fdd5d05f224a3aa0fa77ac197cc1`. This is a documented reconstruction-method discrepancy, not a source-byte discrepancy. The authorized historical fingerprint remains reproducible.

## Verification

- Python regression suite: **299/299 passed**, plus **124 subtests**.
- Frontend regression suite: **26/26 passed**.
- JavaScript syntax: **passed**.
- Focused SAM/WOLFF/integration safety set: **63/63 passed**, plus **11 subtests**.
- Protected Remediation 5 receipt baseline: **234/234 hashes matched**.
- Protected receipt ledger SHA-256: `c999537d62f5e668d35c7dbbb81bf07a442d3fc3faa2ea789bfcafc1fd555c35`.
- Clean startup `/api/health`: **HTTP 200**, version `v2.4-test`.
- SQLite `PRAGMA integrity_check`: **ok**.
- SQLite foreign-key check: **0 violations**.
- Migration ledger: **0001 through 0018**, ordered and complete.
- Empty startup facts: **0 cards, 0 batches, 0 sealed units, 0 acquisitions**.

The Dockerfile's in-build Tesseract and complete receipt-orchestration smoke remains mandatory on the operator's Docker/Jenkins host. Docker was not available in this local release-preparation environment, so a successful operator build is a blocking pre-cutover gate.

## Included behavior

- Established DEX inventory, inbound, receipt, acquisition, economics, sales, correction, and portfolio workflows.
- SAM family recognition and Phase 2 printing evidence.
- Operator-only exact-printing authority.
- Existing Challenger shadow behavior.
- WOLFF Simplified Economics with Unknown-versus-authoritative-zero safeguards.
- Existing provenance, review, and receipt/economics protections.

## Deployment configuration observed in the frozen baseline

- Runtime working directory: `/app`
- Container application port: `8080`
- Compose host port: `8082`
- Compose service: `dex`
- Compose container name: `dex-v2.0-test` (legacy name retained)
- Persistent data mount: `./storage-v2.0-test:/data`
- Scanner mount: `./scanner-inbox-v2.0-test:/scanner-inbox`
- Source database mount: `./source-database-v2.0-test:/source-database`
- Startup: `python app.py`
- Health endpoint: `/api/health`

The frozen Jenkinsfile still builds local tags named `dex:v2.0-test-<build>` and `dex:v2.0-test`, and it does not show a registry push. This package does not change that convention. Before Portainer cutover, the operator must confirm that the normal deployment job has produced the recommended immutable registry tag and record its digest. If that cannot be confirmed, stop before updating Portainer.

## Data and migration behavior

Migrations 0017 and 0018 are additive and transactional where SQLite permits. They do not backfill authoritative printing identity, calculated totals, sale completeness, or economics authority. No production migration is authorized until the operator has verified a current backup and explicitly begins the release cutover.

## Rollback

Record the currently running immutable image tag and digest before cutover; that observed image is the immediate application rollback target. Preserve a verified pre-cutover storage/database backup. First rollback the image while leaving storage intact. Restore storage only if a verified data-level problem requires it and the operator explicitly approves that separate action. Never delete migration rows, tables, or authoritative facts manually.

The preserved local v2.3 Remediation 5 checkpoint is an available prior software checkpoint, but it must not be assumed to be the currently running image without operator confirmation.

## Production status

**NOT DEPLOYED BY JARVIS.** Production access and deployment remain operator-controlled. Cutover is allowed only after the GitHub build-context hash gate, successful Docker/Jenkins build smoke, verified backup, immutable image tag/digest confirmation, and post-start health/data checks.
