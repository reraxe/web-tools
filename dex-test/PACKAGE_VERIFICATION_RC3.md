# RC3 Package Verification

This report records the packaging workstation verification. Final generated counts and hashes are recorded after package assembly.

- Runtime identity: `v2.2-test`
- Python application tests: 180 passed in isolated mode
- Shadow tests: 26 passed (4 Challenger v2, 11 Geometry, 11 TCGplayer bridge)
- JavaScript syntax: 16 files passed
- Offline frontend suites: 13 passed
- Docker CLI: unavailable; deployment-host image build remains required
- External One Piece library: resolved read-only; 5,593 reference images plus one index file; excluded from package
- Production approval: NOT APPROVED

## Live frontend and disposable runtime

- Seeded authoritative batch-detail renderer: **passed**.
- `/api/health`: **HTTP 200**, status `ok`, version `v2.2-test`.
- Fresh empty database startup: **passed twice**, including process restart with the external reference path configured.
- Migration ledger: **14/14**, `0001` through `0014`, ordered correctly.
- SQLite `PRAGMA integrity_check`: **ok**.
- Empty-state counts: **0 acquisitions, 0 batches, 0 cards, 0 sealed units, 0 sale orders, and 0 SAM recognition jobs**.

## External reference boundary

- External library path resolved on both disposable starts.
- External corpus observed: **5,593 reference images**; none are packaged.
- Library metadata fingerprint before/after: `29cc91c18a20a20705d02696fd6a9a340f2741dd7e7ea2cef20cacd5a52cffd0`.
- Frozen readable reference-index SHA-256 before/after: `bba69bba3038067c93c8f96850e3f9d76681e4f9c5e50db2447329f85971232c`.
- No source reference file or index artifact changed.

## Runtime and Docker readiness

- All Python siblings imported by `app.py`: **passed**.
- Dockerfile statically verifies Tesseract and English language-data installation, executes `tesseract --version`, copies every authoritative sibling module, and asserts module imports during build.
- Local Tesseract executable: unavailable on the packaging workstation.
- Docker CLI: unavailable on the packaging workstation. **No Docker build is claimed**; deployment-host build remains an explicit gate.

## Privacy and reproducibility

- Prohibited/private artifact scan: **0 artifacts**.
- Secret-like credential/private-key scan: **0 matches**.
- Machine-local absolute-path scan: **0 matches**.
- Workspace/package comparison: 156 files byte-identical at the pre-manifest comparison point; five documentation-only files intentionally differ for RC3 release identity/path sanitation, and seven RC3 documents were new. See `WORKSPACE_PACKAGE_HASH_COMPARISON_RC3.txt`.

Production approval remains **NOT APPROVED**.

