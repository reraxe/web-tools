# DEX LIVE Storage Lineage

Lineage identifier: `DEX_LIVE_STORAGE`  
Created for: `v2.4-live`  
Initial state: one-time clean Day Zero  
Status after operator cutover: `ACTIVE OPERATIONAL`

## Permanent rule

`v2.4-live` is the only release authorized to start with new, empty LIVE business storage. After the operator begins real use, `v2.5-live`, `v2.6-live`, `v3.0-live`, and all later ordinary LIVE promotions must attach to this same lineage and preserve every authoritative record.

A new image, version, migration, package, or Round Table approval is not authorization to reset data. A reset requires separate operator language equivalent to: `I AUTHORIZE RESETTING LIVE OPERATIONAL DATA.`

## Storage boundaries

- LIVE `/data`: dedicated writable business database, documents, images, SAM operational audit history, and WOLFF operational history.
- LIVE `/scanner-inbox`: dedicated writable intake folder.
- `/source-database`: approved One Piece reference/catalog assets only. It may be shared only after confirming it contains no business state and should be mounted read-only where the deployment permits.
- TEST writable business/audit storage remains separate and preserved as the DEX TEST / DEVELOPMENT ARCHIVE.

Recommended stable Portainer names are `dex-live-data`, `dex-live-scanner-inbox`, and either a dedicated `dex-live-source-database` or a verified reference-only source volume mounted read-only. Names must remain stable across future LIVE image upgrades.

## Rollback boundary

Application rollback and data rollback are separate. Roll back the image first while leaving this lineage attached and unchanged. Never delete migration rows, reseed LIVE, or replace the database as a startup troubleshooting step.
