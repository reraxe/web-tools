# Release Checkpoint — DEX v2.4-live

Status: **GIT-READY LIVE PROMOTION CANDIDATE — NOT DEPLOYED**  
Build identifier: `DEX-v2.4-live-promotion-20260824`  
Runtime: `v2.4-live`  
Target image: `192.168.2.92:5000/apps/dex:v2.4-live`

## Source

This is a promotion of accepted TEST release `v2.4-test-sam-multi-evidence-operator-trial-v1a`, build `SAM-MULTI-EVIDENCE-BLIND-TRIAL-v1a-AUDIT-20260824`, accepted deployment-ledger SHA-256 `dbdfc93b05221f79a8bd60a5a8d0537b742e114cda14fb9fb49c6efe89089de1`.

The accepted TEST package remains separately preserved. Promotion changes are limited to release identity, the visible `LIVE` indicator, passive validation, and lifecycle/Day Zero documentation. The accepted recognizer fingerprint remains `dd899b6f73891252395ae9b8d09b43906ad15c656f0a0c739bd15a916c012493`; recognizer and authority changes are none.

## Operational boundary

`v2.4-live` is the one-time creation of clean LIVE business storage. TEST and LIVE use separate writable `/data` and `/scanner-inbox` storage. Existing TEST business history is not imported. Packaged catalog knowledge and an approved external reference library remain available without granting identity authority.

After the first real LIVE record, clean initialization expires. All future normal LIVE upgrades attach to the permanent LIVE storage lineage and preserve inventory, acquisitions, batches, receipts, sales, SAM audit history, WOLFF records, and future intelligence history. A reset requires separate explicit operator authorization.

## Verification

- Python 326/326 passed.
- Frontend 28/28 passed; JavaScript syntax passed.
- Audited SAM focused integration 23/23 passed.
- Clean isolated startup: HTTP 200, runtime `v2.4-live`, migrations 0001–0019, SQLite integrity `ok`, foreign keys clean, and all defined operational counts zero.
- Frozen One Piece family catalog: 2,838 families.
- Disposable generated scan: suggestion-only before confirmation; confirm/correct work; original result remains immutable; exact printing remains manual.
- Recognizer parity: top family 34/40, candidate inclusion 35/40, false-authority increase 0; frozen component mismatches 0.
- Private/prohibited artifacts: required final result is 0.

## Deployment and rollback

No deployment is included or authorized by this artifact. The final DEPLOY ledger must be verified against the committed GitHub tree before Jenkins. Jenkins must complete the actual Docker build and produce an immutable registry digest before Portainer cutover.

Application rollback uses the exact pre-cutover image tag/digest while leaving LIVE storage unchanged. Never delete migration rows or reset/restore operational data without a separately approved data-level action.
