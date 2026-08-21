# DEX v2.2-test RC3 HF3 Zero-Entry — Drop-In Deploy Verification

Artifact: `DEX_v2.2-test_RC3_HF3_ZERO_ENTRY_DEPLOY`  
Source: tested Zero-Entry v1 workspace  
Runtime identity: `v2.2-test`  
Immutable image tag: `192.168.2.92:5000/apps/dex:v2.2-test-rc3-hf3`

## Certified results

- `app.py` and `Dockerfile` are directly at DEPLOY root.
- `static/app.js`, `static/index.html`, and `static/styles.css` exist.
- Every runtime sibling copied by the Dockerfile is present directly at the expected path.
- Nested `DEX_v2.2-test_RC3_HF3_ZERO_ENTRY_DEPLOY` directory: absent.
- Runtime-source hash mismatches against the tested workspace: 0.
- Python regression: 194/194 passed from the DEPLOY artifact.
- JavaScript syntax: passed.
- Frontend regressions: 17/17 passed from the DEPLOY artifact.
- Runtime imports, including `dex_receipt_ocr` and `dex_receipt_parser`: passed.
- Isolated startup and `/api/health`: HTTP 200, runtime `v2.2-test`.
- Local Tesseract provider: available, private/local, external transmission false.
- Migrations: 0001–0015; no migration 0016.
- Empty startup created 0 acquisitions, batches, cards, or sealed units; SQLite integrity `ok`.
- Prohibited/private artifacts: 0.
- Secrets/private keys/credentials: 0.
- Machine-local paths/configuration: 0.

The Dockerfile uses the HF3 OCI version label and installs/checks Tesseract. An actual Docker image build remains an operator/Jenkins-host gate. No deployment occurred during packaging.

## Operator copy rule

Open DEX_v2.2-test_RC3_HF3_ZERO_ENTRY_DEPLOY, select everything INSIDE it, and upload those contents directly into the GitHub dex-test root. Do not upload the outer DEPLOY folder.

## Rollback

Return the application image to `192.168.2.92:5000/apps/dex:v2.2-test-rc3-hf2`. HF3 adds no migration. Preserve production database/storage.
