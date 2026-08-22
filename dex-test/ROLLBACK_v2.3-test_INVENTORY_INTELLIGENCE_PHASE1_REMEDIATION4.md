# Remediation 4 Rollback

Immediate rollback target: the accepted immutable Remediation 3 DEPLOY package/image.

1. Leave production storage and the live SQLite database intact.
2. Re-select the previously accepted Remediation 3 application image or rebuild from its verified root-shaped DEPLOY contents.
3. Restart only the DEX application container through the normal operator-controlled deployment workflow.
4. Verify `/api/health`, the visible UI version, critical deployed-file hashes, inventory loading, Inbound loading, and receipt review access.

Remediation 4 adds no migration, so rollback requires no schema reversal. Never delete or restore production storage solely because application startup fails.
