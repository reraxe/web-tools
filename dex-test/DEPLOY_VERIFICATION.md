# DEX v2.4-test DEPLOY verification

Artifact: `DEX_v2.4-test_WOLFF_SAM_PHASE2_20260822_DEPLOY`  
Source: frozen `DEX-v2.4-test-WOLFF-SAM-Phase2-development-baseline-20260822`

- Frozen fingerprint reproduced: **PASS** (`3c22c2aa997315e4874e466fc8a99c788cd58f89e9bc7f3f88aeb5f86040d32a`).
- DEPLOY root shape: **PASS**; `app.py`, `Dockerfile`, all runtime siblings, `static/`, `tests/`, and required scripts are directly beneath the artifact root.
- Nested DEPLOY directory: **NONE**.
- Runtime/source hashes versus the tested FULL_CHECKPOINT: **0 mismatches**.
- Python from actual DEPLOY contents: **299/299 passed**, plus 124 subtests.
- Frontend from actual DEPLOY contents: **26/26 passed**.
- JavaScript syntax: **PASS**.
- Runtime imports: **PASS**.
- Isolated startup: **HTTP 200**, version `v2.4-test`.
- SQLite integrity: **ok**; foreign-key violations: **0**.
- Migrations: **0001–0018**.
- Startup-created inventory facts: **NONE**.
- Prohibited/private artifacts: **0**.
- Vision Intake POC files: **0**.
- Docker build: **PENDING OPERATOR/JENKINS HOST** because Docker is unavailable in the local packaging environment. The in-Docker Tesseract and complete receipt-orchestration smoke must pass before cutover.
- Production deployment: **NOT PERFORMED**.

The deploy ledger is `DEPLOY_SHA256SUMS.txt`. After GitHub upload, verify the exact commit against that accepted ledger before triggering Jenkins.
