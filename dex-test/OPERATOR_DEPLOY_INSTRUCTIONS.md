# RC3 Drop-In Deploy Instructions

Target image tag: `192.168.2.92:5000/apps/dex:v2.2-test-rc3-r1`

1. Open `DEX_v2.2-test_RC3_DEPLOY`.
2. Copy **its contents**, not the enclosing folder, into the GitHub `dex-test` root.
3. Confirm `app.py`, `Dockerfile`, `static/`, and the `dex_*.py` modules now appear directly at the GitHub root.
4. Commit/upload the changes without adding databases, images, scanner folders, receipts, or secrets.
5. In Jenkins, select **Build Now** and confirm the build and registry push succeed for the target tag above.
6. In Portainer, change only the DEX image tag to the target tag and select **Update Stack**.
7. Hard refresh DEX.
8. Confirm `/api/health` returns HTTP 200 and runtime `v2.2-test`.
9. Confirm Receipt / Source Documents shows **Take Photo** and **Upload**, then continue the operator smoke test.

Rollback reference: the prior known-good RC2 image/checkpoint and matching database/storage backup. Never manually delete migrations or authoritative records.

