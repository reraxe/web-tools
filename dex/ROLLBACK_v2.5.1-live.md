# Rollback — DEX v2.5.1-live

Immediate rollback release: DEX v2.5-live.

Rollback image: `192.168.2.92:5000/apps/dex:v2.5-live`

Rollback checkpoint: `DEX_v2.5-live_FULL_CHECKPOINT`

This hotfix adds no migration, so application rollback does not require database reversal. Preserve the existing LIVE `/data`, scanner inbox, and read-only One Piece reference-library mounts. If a deployment fails, return the stack to the prior immutable image and verify `/api/health`, visible UI version, and inventory availability. Do not delete, replace, or restore LIVE storage solely because startup failed.

