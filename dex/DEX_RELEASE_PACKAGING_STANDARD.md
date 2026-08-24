# Permanent DEX Release Packaging Standard

Effective date: 2026-08-16  
Status: mandatory for every future DEX release candidate, test release, hotfix, and stable release

This policy preserves the operator's existing deployment workflow while keeping complete archival evidence and rollback material. It does not retroactively alter the frozen RC3 checkpoint.

## Required Release Artifacts

Every release must produce two separate top-level artifacts.

### Full Checkpoint Package

Naming pattern: `DEX_<VERSION>_FULL_CHECKPOINT/`

Purpose: archival evidence, rollback, testing records, hashes, manifests, release notes, research modules, and preservation.

It may contain:

- authoritative source
- migrations
- tests
- documentation and release notes
- research/shadow modules
- verification reports
- upload/exclusion manifests and checksums
- rollback instructions

It must be clearly labeled archival/checkpoint material. It is **not** intended to be copied directly into the GitHub `dex-test` root.

### Drop-In Deploy Package

Naming pattern: `DEX_<VERSION>_DEPLOY/`

Purpose: preserve the operator workflow:

`copy contents → GitHub dex-test root → Jenkins Build Now → Portainer image update`

The deploy package must mirror the exact root structure Jenkins expects. Its contents—not the enclosing release directory—must be directly copyable into the GitHub `dex-test` root. There must be no nested release folder and no required path translation, restructuring, manual file selection, or server-side editing.

Expected root structure includes, as applicable:

- `app.py`
- `Dockerfile`
- `requirements.txt`
- `static/`
- migrations or the established migration module
- `tests/`
- every `dex_*.py` sibling required by `app.py`
- other required runtime files

## Deploy-Package Verification

Before delivery, compare the deploy package with the tested authoritative workspace by SHA-256. Required result: **0 runtime mismatches**.

Verify at minimum:

- `app.py`
- `Dockerfile`
- `requirements.txt`
- `static/index.html`
- `static/app.js`
- `static/styles.css`
- migrations
- every runtime sibling module imported by `app.py`

Every deploy package must contain:

- `DEPLOY_SHA256SUMS.txt`
- `DEPLOY_VERIFICATION.md`

## GitHub Build-Context Provenance Gate

`DEPLOYMENT-INTEGRITY-001` established that an accepted DEPLOY package can remain correct while an incomplete or stale GitHub upload causes Jenkins to build mixed backend/frontend source. Package verification alone is therefore not sufficient.

After uploading the accepted DEPLOY contents and before selecting Jenkins **Build Now**:

1. Record the resulting GitHub commit SHA.
2. Obtain that exact commit in a disposable checkout or download.
3. Verify the committed build context against the accepted package's `DEPLOY_SHA256SUMS.txt`.
4. Require zero missing or mismatched release files.
5. At minimum verify `app.py`, `static/index.html`, `static/app.js`, `static/styles.css`, and `Dockerfile`.
6. Do not trigger Jenkins when any verification fails. Correct the upload/commit and repeat the gate.

The accepted DEPLOY ledger—not an unverified ledger from the GitHub copy—is the comparison authority.

## Package and Privacy Boundaries

The deploy package must exclude:

- databases and disposable validation databases
- physical card scans
- reference libraries and source-image archives
- receipts and source documents
- ground-truth files, benchmark corpora, blind stages, and private results
- caches, logs, and generated runtime output
- passwords, secrets, tokens, credentials, and private keys
- machine-local absolute paths or configuration

Required result: **0 prohibited/private artifacts**.

## Release Provenance

Preserve the runtime family such as `vX.X-test`, and also record:

- release candidate or hotfix identifier
- package/release identifier
- Git revision when available
- build timestamp when appropriate

Prefer Docker OCI metadata such as:

- `org.opencontainers.image.version=v2.3-test-rc1`
- `org.opencontainers.image.revision=<git revision>`

Where practical, expose release identity through diagnostics or the footer, for example `Home Network · v2.3-test · RC1`. Historical deployment conventions must not be changed solely for aesthetics.

## Docker Image Tags

Each release candidate must use a unique image tag, for example:

- `dex:v2.2-test-rc3`
- `dex:v2.2-test-rc3-r1`
- `dex:v2.3-test-rc1`

Do not silently overwrite a previously deployed release-candidate tag. A corrected rebuild receives an immutable suffix such as `-r1`.

## Jenkins Compatibility

Jenkins expects the buildable DEX source directly at the `dex-test` root when it executes `docker build ... .`.

- Never require Jenkins to discover or descend into a nested checkpoint folder.
- The drop-in deploy package must be directly compatible with that root.
- Any Jenkins configuration change requires explicit operator approval before implementation.

## Portainer Compatibility

Deployment should require only updating the image line, such as:

`image: 192.168.2.92:5000/apps/dex:v2.3-test-rc1`

No additional Portainer or server configuration may be required unless separately approved.

## Production Access Policy

- No persistent SSH credentials, server passwords, or private keys are required or retained.
- JARVIS does not assume direct production, Jenkins, Portainer, registry, storage, or SQLite access.
- The operator runs deployment commands and UI actions.
- Production diagnosis uses operator-provided screenshots, logs, health responses, hashes, or command output.
- No destructive server action occurs without explicit approval and a verified rollback path.
- When release packaging can be completed without production access, use the no-access path.

## Operator Instructions

Every release handoff must include `OPERATOR_DEPLOY_INSTRUCTIONS.md`, written for a non-server-admin operator and limited to the steps actually required:

1. Open `*_DEPLOY`.
2. Copy its contents into the GitHub `dex-test` root.
3. Record the resulting GitHub commit SHA.
4. Obtain that exact commit in a disposable checkout/download and verify it against the accepted `DEPLOY_SHA256SUMS.txt`; require zero missing or mismatched files, including the five critical files named above.
5. Stop before Jenkins if verification fails.
6. Confirm the supplied Docker image tag.
7. In Jenkins, select **Build Now**.
8. Confirm the build and registry push succeed; record the immutable image tag and digest where available.
9. In Portainer, update the image tag.
10. Select **Update Stack**.
11. Verify `/api/health` and the visible sidebar report the same expected runtime version.
12. Compare deployed hashes for `/app/app.py`, `/app/static/index.html`, `/app/static/app.js`, and `/app/static/styles.css` with the accepted DEPLOY ledger.

`Dockerfile` belongs to the pre-build GitHub/build-context gate and may not be copied into `/app`. A backend/frontend version mismatch is a deployment-integrity failure, not a browser-cache assumption.

Prefer the existing Jenkins and Portainer interfaces over unnecessary server commands.

## Rollback

Every release must identify:

- the prior known-good image tag
- the prior full checkpoint
- whether a matching database/storage backup is required

Never instruct the operator to manually delete migrations or authoritative records.

## Required Final Delivery

Every future release must deliver:

- `DEX_<VERSION>_FULL_CHECKPOINT/`
- `DEX_<VERSION>_DEPLOY/`
- full-checkpoint aggregate SHA-256
- deploy SHA-256 ledger
- deploy verification report
- privacy scan result
- operator deployment instructions
- exact immutable Docker image tag
- rollback reference

The primary requirement is to preserve the operator's simple deployment workflow while retaining full release integrity, provenance, and rollback evidence. Do not redesign Jenkins, Portainer, the Git layout, or production infrastructure without separate approval.
