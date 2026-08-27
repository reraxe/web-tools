# Release Checkpoint — DEX v2.5-live

Status: **GIT-READY LIVE PROMOTION CANDIDATE — NOT DEPLOYED**  
Build identifier: `DEX-v2.5-live-promotion-20260825`  
Runtime: `v2.5-live`  
Target image: `192.168.2.92:5000/apps/dex:v2.5-live`

## Source

This is the promotion of the accepted `v2.5-test` TCGplayer Inventory Bootstrap + Reconciliation V1 candidate. The accepted TEST source-ledger fingerprint is `02a491a0f7fd5d9e8488ccc3a4c149ce020f3db03e795836376c18589e1c4f75`.

Promotion changes are restricted to LIVE runtime identity, cache-busting/version presentation, promotion-specific acceptance assertions, and release/rollback documentation. TCGplayer bootstrap and reconciliation, quantity pools, operator modals, audit behavior, SAM, WOLFF, JANA, economics, and other application behavior are unchanged.

## Scope

- Migration `0020_v25_tcgplayer_inventory_bootstrap_v1`.
- TCGplayer opening-inventory preview, review, explicit confirmation, and audited import.
- Quantity-pool ownership and fulfillment events.
- Snapshot reconciliation without observation-driven inventory mutation.
- Explicit in-app forms for fulfillment, reconciliation, and destructive export approval.
- Exact printed One Piece card-number lookup with family/reference separation.

## Data behavior

Normal LIVE upgrade attaches to existing persistent LIVE storage. Migration 0020 is additive and transactional where SQLite permits. It creates the v2.5 TCGplayer ledger, snapshot, quantity-pool, inventory-event, reconciliation, and export infrastructure without rewriting existing inventory facts. Existing operational storage must not be reset or replaced.

## Acceptance boundary

Final acceptance is performed from the root-shaped DEPLOY contents. Required gates include the complete Python and frontend regression suites, JavaScript syntax, disposable migration from a v2.4-live-like database, pre/post preservation comparison, SQLite integrity, foreign-key integrity, exact package hashes, and zero prohibited/private artifacts.

## Deployment status

No deployment is performed by this checkpoint. Before Jenkins, the committed GitHub `/dex/` tree must match `DEPLOY_SHA256SUMS.txt` exactly. The operator must preserve the existing LIVE storage lineage and obtain a verified pre-cutover backup.
