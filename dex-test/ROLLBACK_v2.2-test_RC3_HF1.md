# DEX v2.2-test RC3 Hotfix 1 Rollback

Prior known-good application/image: RC3-r4.  
Prior immutable source/deploy artifacts: `DEX_v2.2-test_RC3_Operator_Trial_GitHub_Checkpoint` and `DEX_v2.2-test_RC3_DEPLOY`.

Before an operator-approved deployment, create a timestamped storage/database backup. If Hotfix 1 startup fails, switch only the application image back to RC3-r4 first. Never delete production storage, schema columns, or `schema_migrations` rows to repair startup.

If rollback must cross migration 0015, use the matching pre-0015 storage backup. Preserve the Hotfix 1 database separately if it contains newly confirmed mixed-purchase facts. Application and database rollback must remain a matched pair.
