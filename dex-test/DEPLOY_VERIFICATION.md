# DEX v2.2-test RC3 Drop-In Deploy Verification

Artifact: `DEX_v2.2-test_RC3_DEPLOY`  
Source checkpoint: `DEX_v2.2-test_RC3_Operator_Trial_GitHub_Checkpoint`  
Runtime identity: `v2.2-test`  
Recommended corrected-rebuild image tag: `192.168.2.92:5000/apps/dex:v2.2-test-rc3-r1`

## Purpose and boundary

This is a one-time root-shaped deployment artifact derived from the already verified RC3 checkpoint. It is not a new release and contains no application, schema, migration, recognition, economics, or frontend changes.

The contents of this directory—not the enclosing directory—are intended to be copied into the existing GitHub `dex-test` root. `app.py`, `Dockerfile`, `requirements.txt`, `VERSION`, `static/`, `tests/`, the migration module, and all runtime sibling modules are directly at the expected root level. There is no nested RC3 checkpoint directory.

Jenkins and Compose files are intentionally not replaced by this artifact. The operator's existing GitHub/Jenkins/Portainer deployment configuration remains separately controlled.

## RC3 source verification

- Copied RC3 source/test files checked against the immutable RC3 `SHA256SUMS.txt`: **62**
- RC3 hash mismatches: **0**
- Copied files missing from the RC3 ledger: **0**
- Runtime sibling modules imported by `app.py`: **17**
- Runtime sibling modules missing from the Dockerfile: **0**
- Runtime import check: **PASS**
- Runtime version: **v2.2-test**

The deploy-specific verification and operator-instruction documents are newly generated packaging metadata. They do not modify runtime behavior.

## Regression verification

- Python application regression: **180/180 passed**
- JavaScript syntax: **16/16 files passed**
- Frontend regression suites: **14/14 passed**
- Seeded disposable startup: **PASS**
- `/api/health`: **HTTP 200**, status `ok`, version `v2.2-test`

The first deploy-folder test run identified one missing documentation dependency: `PATCH_PLAN_ACQUISITION_RIP_BATCH.md`, which a Phase 4 contract test reads. The unchanged RC3 copy of that document was added; the complete rerun then passed 180/180. No code was changed.

## Docker/build structure

- Dockerfile is byte-identical to RC3.
- Tesseract and English language-data installation remain present.
- Docker build-time `tesseract --version` and Python import assertions remain present.
- `static/` and all Docker `COPY` inputs are at the deploy root.
- A Docker CLI/image build was not available on the packaging workstation; the actual image build remains the Jenkins-host gate.

## Privacy and exclusions

Final package scanning requires:

- prohibited/private artifacts: **0**
- machine-local absolute paths: **0**
- secrets/private-key/credential patterns: **0**

The artifact excludes databases, inventory data, physical scans, reference assets, receipt files, ground truth, benchmark corpora, blind stages, caches, logs, secrets, environment files, disposable QA data, shadow research packages, and machine-local configuration.

## RC3 preservation

The original RC3 checkpoint remains separate and immutable. Its aggregate SHA-256 must remain:

`5e18ae1daf813cffd30f1763b63853f608704ddbb31d7efc6e24f160f5150732`

Use RC2 and its matching data/storage backup as the rollback checkpoint. Never remove migrations or authoritative records manually.

