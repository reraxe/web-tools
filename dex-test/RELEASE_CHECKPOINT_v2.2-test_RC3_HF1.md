# DEX v2.2-test RC3 Hotfix 1 Release Checkpoint

Release identifier: `v2.2-test-rc3-hf1`  
Runtime family: `v2.2-test`  
Production deployment: **NOT PERFORMED**

## Scope

This is a targeted RC3 operator-trial hotfix for mixed inventory/noninventory reconciliation. It preserves RC3 application scope and all SAM/shadow, economics, catalog, receipt, routing, inventory, and sales behavior outside acquisition reconciliation.

## Accounting contract

1. Component total plus a deterministically derived component adjustment equals final USD paid. Every nonzero adjustment retains a reason and explanation.
2. Confirmed inventory landed cost plus an explicit net excluded-noninventory amount equals final USD paid exactly.
3. A reason string never supplies or infers the excluded amount.
4. Excluded noninventory never enters product-line inventory basis and carries no tax/general-ledger conclusion.

Inbound calculation/audit payload version is `inbound-acquisition-v2`. Prior v1 events are not rewritten.

## Migration ledger

Migrations `0001` through `0015` are present and ordered. Migration 0015 adds only three nullable acquisition columns and its ledger row; it performs no fact backfill.

## Verification

- Python: 183 tests passed.
- Frontend: JavaScript syntax passed; 15 direct regression files passed.
- Exact mixed-purchase case, invalid bypasses, line invalidation, UI state preservation, and audit payloads passed.
- Fresh/RC3-era/confirmed/incomplete migration fixtures passed; SQLite integrity `ok`.
- Runtime import and isolated health/startup checks are required again against the final packaged hashes and are recorded in package verification.

## Deployment and rollback

Use the root-shaped DEPLOY artifact only. Build the unique tag `192.168.2.92:5000/apps/dex:v2.2-test-rc3-hf1`; do not overwrite RC3-r4. Deployment is operator-controlled. Back up storage before migration and retain RC3-r4 plus its matching pre-0015 backup as rollback.
