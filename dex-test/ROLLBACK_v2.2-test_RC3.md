# RC3 Rollback

RC2 remains the known-good pre-RC3 checkpoint.

If RC3 startup or trial validation fails:

1. Stop only the RC3 runtime being tested.
2. Preserve its logs and operator-provided error output for diagnosis.
3. Restore the matching RC2 application checkpoint.
4. If real operator data was created, restore the matching verified pre-RC3 database and storage backup together.
5. Start the restored runtime and verify health, version, inventory counts, Inbound, Recycle Bin, Sales, and economics.

Never fix a startup failure by deleting production storage, removing migration records, or editing authoritative SQLite facts in place.

