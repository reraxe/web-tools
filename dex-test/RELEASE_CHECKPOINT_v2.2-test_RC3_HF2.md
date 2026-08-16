# DEX v2.2-test RC3 Hotfix 2 Release Checkpoint

Release identifier: `v2.2-test-rc3-hf2`  
Runtime family: `v2.2-test`  
Production deployment: **NOT PERFORMED**

## Scope

HF2 is a surgical operator-trial unblocker for failed/unavailable receipt image extraction. It adds an audited manual-facts decision, makes the receipt allocation warning informational only after that explicit choice, retains the receipt as evidence, and removes ghost active state after receipt removal.

No Receipt Image OCR, zero-entry accounting, SAM, JANA, catalog integration, pricing, economics formula, inventory identity, or production configuration change is included.

## Authority boundary

Manual fallback does not create authority. Confirmation still requires confirmed line allocations, exact HF1 component and inventory-basis reconciliations, explicit excluded amount/treatment/confirmation, and all material-discrepancy controls.

## Database

No migration 0016. The ledger remains migrations 0001–0015. `MANUAL_FALLBACK_SELECTED` is appended to the existing receipt event table only when the operator explicitly chooses it.

## Verification

- Python: 185 tests passed.
- JavaScript syntax: passed.
- Frontend regression files: 16 passed.
- Exact Mom and Pop Shop JPG manual-fallback regression: passed.
- PDF/text receipt regression: passed.
- Removed-document active-warning cleanup: passed.
- Package imports, isolated startup, health, hashes, and privacy scans are recorded in package verification.

## Deployment

Use only the root-shaped HF2 DEPLOY artifact and immutable image tag `192.168.2.92:5000/apps/dex:v2.2-test-rc3-hf2`. Deployment remains operator-controlled.
