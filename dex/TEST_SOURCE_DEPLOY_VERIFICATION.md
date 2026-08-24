# DEX v2.4-test SAM Multi-Evidence Operator Trial v1a — Deploy Verification

Artifact: `DEX_v2.4-test_SAM_MULTI_EVIDENCE_OPERATOR_TRIAL_v1a_DEPLOY`  
Runtime identity: `v2.4-test-sam-multi-evidence-operator-trial-v1a`  
Image tag: `192.168.2.92:5000/apps/dex:v2.4-test-sam-multi-evidence-operator-trial-v1a`

## Certified results

- Root-shaped package: `app.py`, `Dockerfile`, requirements, runtime modules, `static/`, tests, scripts, migrations, and frozen audited-SAM components are directly at their Jenkins-expected paths.
- Nested DEPLOY directory: absent.
- Runtime/source hash mismatches against the tested integration worktree: 0.
- Frozen audited recognizer/config: 25/25 accepted trial entries verified; accepted fingerprint `dd899b6f73891252395ae9b8d09b43906ad15c656f0a0c739bd15a916c012493`; recognizer/config changes 0.
- Python regression: 322/322 passed.
- Focused audited SAM integration: 23/23 passed.
- JavaScript syntax and frontend regressions: 27/27 passed.
- Isolated startup and `/api/health`: HTTP 200 with the expected runtime.
- Migrations: 0001–0019; SQLite integrity `ok`; empty startup created 0 batches, 0 cards, and 0 audited results.
- Prohibited/private artifacts, private scans/truth/reference assets/databases, secrets, and machine-local paths: 0.

The Dockerfile installs/checks local Tesseract, includes the accepted trial dependencies, verifies the frozen component hashes at build time, and retains the established receipt-orchestration smoke. Docker is unavailable on the packaging workstation, so the actual image build remains the normal Jenkins-host gate. No deployment occurred.

## Operator copy rule

Open `DEX_v2.4-test_SAM_MULTI_EVIDENCE_OPERATOR_TRIAL_v1a_DEPLOY`, select everything **inside** it, and upload those contents directly into the GitHub `dex-test` root. Do not upload the outer DEPLOY folder.

## Rollback

Restore the exact WOLFF/SAM Phase 2 image tag/digest recorded before cutover. Leave storage untouched unless a separately approved, verified data rollback is required.
