# Rollback — DEX v2.5-live

Immediate application rollback: `192.168.2.92:5000/apps/dex:v2.4-live`.

Before cutover, record the exact running v2.4-live image digest and create a verified timestamped backup of the existing LIVE `/data` storage.

If v2.5-live startup or health validation fails:

1. Repoint the LIVE stack to the recorded v2.4-live image tag/digest.
2. Keep the existing LIVE `/data`, scanner inbox, and reference-library mounts unchanged.
3. Update the stack and verify health plus existing inventory.
4. Preserve v2.5 logs and migration evidence for diagnosis.

Do not delete migration 0020, its tables, inventory events, or operational storage. Do not restore the database merely because application startup failed. A database restore requires separate operator approval and a verified backup target.

