# TEST to LIVE Provenance — v2.5-live

Accepted TEST runtime: `v2.5-test`  
Accepted TEST scope: `TCGplayer Inventory Bootstrap + Reconciliation V1`  
Accepted TEST source-ledger SHA-256: `02a491a0f7fd5d9e8488ccc3a4c149ce020f3db03e795836376c18589e1c4f75`  
LIVE build identifier: `DEX-v2.5-live-promotion-20260825`

Promotion differences are limited to:

- `APP_VERSION`, `VERSION`, and Docker OCI version label;
- frontend cache-busting and visible LIVE environment badge;
- acceptance assertions that verify the LIVE identity;
- promotion, migration, upload, verification, and rollback documentation.

Application behavior is inherited from the accepted TEST source. Migration 0020, TCGplayer inventory logic, quantity pools, reconciliation semantics, operator modals, audit behavior, SAM, WOLFF, and JANA are not redesigned or tuned during promotion.
