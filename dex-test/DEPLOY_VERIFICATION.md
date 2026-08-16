# DEX v2.2-test RC3 Hotfix 1 Drop-In Deploy Verification

Artifact: `DEX_v2.2-test_RC3_HF1_DEPLOY`  
Source checkpoint: `DEX_v2.2-test_RC3_HF1_FULL_CHECKPOINT`  
Runtime identity: `v2.2-test`  
Immutable image tag: `192.168.2.92:5000/apps/dex:v2.2-test-rc3-hf1`

## Purpose and boundary

The contents of the DEPLOY directory—not its enclosing directory—are intended to be copied into the GitHub `dex-test` root. Application source, Dockerfile, static assets, runtime siblings, migration module, tests, and required release documentation are directly at that root.

Jenkins, Compose, ports, volumes, container names, and production storage configuration are not replaced by this artifact. Deployment remains operator-controlled.

## Verification

- Runtime-source hash mismatches against the tested full checkpoint: **0**.
- Runtime sibling modules imported by `app.py` but absent from the Dockerfile: **0**.
- Python runtime imports: **PASS**.
- Isolated startup: **PASS**.
- `/api/health`: **HTTP 200**, version `v2.2-test`.
- Migrations: **0001–0015**, ordered.
- Empty-startup acquisitions/batches/cards/sealed units created: **0**.
- Prohibited/private artifacts: **0**.
- Secret/private-key/credential patterns: **0**.
- Machine-local absolute paths: **0**.

The Dockerfile retains Tesseract installation and build-time runtime/import assertions. Docker was not built or deployed from the packaging workstation; the actual image build remains the Jenkins-host gate.

## Rollback

Keep RC3-r4 and its matching pre-0015 storage backup. Do not remove migration rows or columns manually. See `ROLLBACK_v2.2-test_RC3_HF1.md`.
