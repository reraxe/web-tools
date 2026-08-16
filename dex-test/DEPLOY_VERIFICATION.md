# DEX v2.2-test RC3 Hotfix 2 Drop-In Deploy Verification

Artifact: `DEX_v2.2-test_RC3_HF2_DEPLOY`  
Source checkpoint: `DEX_v2.2-test_RC3_HF2_FULL_CHECKPOINT`  
Runtime identity: `v2.2-test`  
Immutable image tag: `192.168.2.92:5000/apps/dex:v2.2-test-rc3-hf2`

## Root shape and verification

- `app.py` and `Dockerfile` are directly at DEPLOY root.
- `static/app.js`, `static/index.html`, and `static/styles.css` exist.
- Every runtime sibling imported by `app.py` is directly where the Dockerfile expects it.
- Nested `DEX_v2.2-test_RC3_HF2_DEPLOY` directory: **absent**.
- Runtime-source hash mismatches against the tested HF2 workspace: **0**.
- Runtime sibling modules absent from the Dockerfile: **0**.
- Python runtime imports: **PASS**.
- Isolated startup and `/api/health`: **PASS**, HTTP 200, version `v2.2-test`.
- Migrations: **0001–0015**; no 0016.
- Prohibited/private artifacts: **0**.
- Secret/private-key/credential patterns: **0**.
- Machine-local absolute paths: **0**.

Jenkins, Compose, ports, volumes, container names, and production storage configuration are not replaced. Docker was not built or deployed from the packaging workstation.

## Operator copy rule

Open `DEX_v2.2-test_RC3_HF2_DEPLOY`, select everything **inside** it, and upload those contents directly into the GitHub `dex-test` root. Do not upload the outer DEPLOY folder.

## Rollback

Return first to `v2.2-test-rc3-hf1`; HF2 adds no migration. Preserve the database/storage. RC3-r4 plus its matching pre-0015 backup remains the older rollback boundary.
