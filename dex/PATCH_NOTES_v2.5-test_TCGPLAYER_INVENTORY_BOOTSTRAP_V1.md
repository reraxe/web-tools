# Patch Notes — DEX v2.5-test

Status: isolated TEST development checkpoint; not packaged and not deployment-approved.

## TCGplayer Inventory Bootstrap + Reconciliation V1

- Adds a dedicated TCGplayer Inventory page and operator-selected CSV preview.
- Creates quantity pools rather than fabricating one serialized card row per copy.
- Makes the first applied snapshot an explicit one-time opening bootstrap.
- Treats subsequent snapshots as external channel observations only.
- Keeps zero-quantity rows from creating phantom inventory.
- Maps One Piece by exact printed card number against the frozen local family catalog; ambiguous/missing mappings stay out of automatic import.
- Adds append-only quantity events, idempotent sales/intake/corrections, exact reversal links, and SAM existing-copy/new-copy reconciliation.
- Generates a minimal operator-download CSV using signed `Add to Quantity` deltas while preserving source prices/columns.
- Blocks stale, missing-price, and materially destructive exports unless their specific safety requirements pass.
- Adds private aggregate validation tooling and Docker build-time import coverage.

## Deliberately not included

No TCGplayer API write, auto-stage, auto-Live action, repricing, WOLFF/JANA change, full reservation engine, automatic legacy serialized-card conversion, LIVE deployment, or release package.

## Known limitations

- Initial quantity pools are structured commercial/condition quantities, not individually scanned card identities.
- One Piece rows without an exact recognizable card number require review and are not bootstrapped.
- Other games retain generic TCGplayer commercial IDs; DEX family normalization is deferred.
- Pending quantity remains Unknown when the exported contract omits the field.
- Channel reconciliation assumes the operator imports a complete, current Live-inventory export.
- Export creates a file for manual Staged Inventory use; DEX cannot confirm what the operator later stages or moves Live.
