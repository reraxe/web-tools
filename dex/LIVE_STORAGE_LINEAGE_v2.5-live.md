# LIVE Storage Lineage — v2.5-live

v2.5-live continues the established persistent LIVE storage lineage. It is not a clean-start release.

- Keep the existing LIVE `/data` bind mount unchanged.
- Keep the existing LIVE scanner inbox and approved read-only reference-library mount unchanged.
- Do not import TEST storage or replace LIVE storage.
- Obtain and verify a timestamped pre-v2.5 backup before cutover.
- Startup applies migration 0020 to the existing LIVE database after migrations 0001–0019.
- Migration alone creates no opening inventory, quantity pools, inventory events, or TCGplayer imports.

The existing LIVE database remains authoritative. TCGplayer observations do not change inventory until the operator explicitly confirms the relevant import, reconciliation, fulfillment, or export action.

