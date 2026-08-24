# v2.4-live One-Time Day Zero

This procedure creates the first DEX LIVE business environment. It is not a reusable upgrade procedure.

## Before cutover

1. Preserve the existing TEST container, TEST storage, and accepted TEST package as the development archive.
2. Record the current application rollback image tag and digest.
3. Create new empty writable Portainer volumes named `dex-live-data` and `dex-live-scanner-inbox`; do not copy TEST business files into either volume.
4. Prepare `dex-live-source-database` with approved One Piece reference assets, or identify the existing reference-only volume. Verify it contains no `dex.db`, receipt, scan, inventory, or audit data. Prefer a read-only mount.
5. Configure the new LIVE container with `/data`, `/scanner-inbox`, and `/source-database` as documented in `OPERATOR_DEPLOY_INSTRUCTIONS_v2.4-live.md`. Set `DEX_SEED_DEMO=0`.

## Required initial state

Before real intake, verify migrations 0001–0019, SQLite integrity `ok`, foreign-key check clean, and zero inventory, acquisitions, batches, receipts/documents, sales, sealed units, SAM operational results/decisions/truth/deltas, and WOLFF operational events. Catalog/reference knowledge is allowed and required; it is not business history.

## Functional gate

Verify `/api/health` returns HTTP 200 and `v2.4-live`; Inventory, SAM, and Economics/WOLFF open; the sidebar shows `LIVE`; an unseen disposable card scan produces a suggestion without writing identity; confirm and correct require operator action; the original result remains immutable; exact printing remains manual.

Delete only the disposable test card and its test history through approved application workflows before declaring Day Zero. If a clean-state recheck does not return zero operational records, do not begin real use.

After the first real operational record is entered, this clean initialization authority expires permanently.
