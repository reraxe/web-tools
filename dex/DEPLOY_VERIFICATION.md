# DEX v2.4-live Deploy Verification

Artifact: `DEX_v2.4-live_DEPLOY`  
Runtime: `v2.4-live`  
Target image: `192.168.2.92:5000/apps/dex:v2.4-live`

Certified source results:

- Accepted TEST source ledger: 150 entries, zero mismatches, ledger SHA-256 `dbdfc93b05221f79a8bd60a5a8d0537b742e114cda14fb9fb49c6efe89089de1`.
- Frozen audited recognizer: 25/25 components match; fingerprint `dd899b6f73891252395ae9b8d09b43906ad15c656f0a0c739bd15a916c012493`; recognizer changes none.
- Python regression: 326/326 passed.
- Frontend regression: 28/28 passed; JavaScript syntax passed.
- Focused audited-SAM integration: 23/23 passed.
- Clean isolated startup: HTTP 200, runtime `v2.4-live`, migrations 0001–0019, SQLite integrity `ok`, foreign keys clean, and zero operational business/audit records.
- Frozen One Piece family catalog: 2,838 families, non-authoritative.
- Disposable generated scan: suggestion-only until explicit confirmation/correction; original result immutable; exact printing manual.
- Prohibited/private artifacts, databases, scans, receipts, reference images, ground truth, secrets, caches, and machine-local paths: required final result zero.

The Dockerfile retains all runtime modules, Tesseract installation/checks, frozen component hash assertion, and complete receipt-orchestration smoke. Docker is unavailable on this workstation, so Jenkins must complete the actual Docker build before deployment approval.

No deployment was performed. The one-time Day Zero authority applies only to creating the first `v2.4-live` storage lineage. Future LIVE upgrades preserve that lineage.
