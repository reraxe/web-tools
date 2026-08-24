# v2.4-live Migration Notes

No new migration is introduced by the TEST-to-LIVE promotion.

- Required ordered ledger: migrations 0001 through 0019.
- Clean Day Zero startup creates the schema and migration ledger only; it does not seed business records.
- One Piece catalog/reference knowledge is retained through packaged frozen catalog data and the separately mounted approved reference library.
- Future LIVE upgrades must test migrations against disposable live-like copies, preserve all records, use transactional migration behavior where SQLite permits, verify integrity/foreign keys, and keep the permanent LIVE storage lineage.
- Never delete migration rows or replace LIVE storage merely because application startup fails.
