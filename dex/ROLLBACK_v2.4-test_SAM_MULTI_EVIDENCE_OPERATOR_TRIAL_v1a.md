# Rollback — SAM Multi-Evidence Operator Trial v1a

Prior known-good application image: `192.168.2.92:5000/apps/dex:v2.4-test-wolff-sam-phase2-20260822` (record and use the exact live digest observed immediately before cutover).

1. If startup or health fails, change only the DEX image back to the recorded prior tag/digest and update the existing stack.
2. Leave `/data`, `/scanner-inbox`, `/source-database`, environment, network, and proxy settings unchanged.
3. Verify `/api/health`, Inventory, SAM, and WOLFF.
4. Do not delete 0019 tables, migration rows, original recognition results, or operator decisions.

Restore the timestamped pre-0019 `/data` backup only for a confirmed data-level problem after separate operator approval. Preserve the current storage first.
