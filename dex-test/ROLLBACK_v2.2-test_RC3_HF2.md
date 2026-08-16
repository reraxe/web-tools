# DEX v2.2-test RC3 Hotfix 2 Rollback

Immediate rollback image: `192.168.2.92:5000/apps/dex:v2.2-test-rc3-hf1`

Hotfix 2 adds no schema migration. If HF2 startup or UI behavior fails, restore only the HF1 application image first and preserve the current database/storage. HF1 safely ignores the additive receipt-event type.

RC3-r4 remains the older rollback reference. Returning to RC3-r4 crosses migration 0015 and therefore requires its matching verified pre-0015 storage backup. Never delete migration rows, receipt events, documents, or acquisition facts manually.
