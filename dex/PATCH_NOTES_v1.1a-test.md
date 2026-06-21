# Dex v1.1a-test Patch Notes

Released for testing on June 21, 2026. This follow-up preserves `v1.1-test` and upgrades existing SQLite data in place when its database is copied or mounted into the new test deployment.

## Recycle Bin

- Move individual cards out of active inventory without destroying their SKU or history.
- Restore cards with their original SKU, status, batch, images, and details.
- Record removal reason, removal date, retention deadline, and activity history.
- Default retention to 180 days with optional automatic purge.
- Protect sold cards and financial records from permanent deletion.
- Permanently remove eligible records and their scan-image folder after confirmation.

## Scanner Intake

- Choose Front First (Face Down) or Back First (Face Up) for sequential files.
- Preserve explicit `_front` and `_back` filename orientation.
- Review every paired filename and unmatched file before import.
- Change scanner order from the batch scan-group controls.
- Swap an existing card's front/back images without replacing its SKU.

## Complete Card Editor

- View front and back scans together and open either at full resolution.
- Copy the immutable physical SKU.
- Swap image sides, reprint the label, or move the card to Recycle Bin.
- Continue editing identity, status, location, listing, and pricing details.

## Batch and Label Corrections

- Queue labels only after an inbound batch is completed.
- Preserve printed-label state when completed batches are reopened.
- Queue labels for newly added cards after the batch is completed again.
- Apply consistent Title Case to compact interface headings and statuses.

## Searchable Set Entry

- Replace separate One Piece set-code/name entry with a searchable combined picker.
- Include OP01 through OP16 and support searching by code or name.
- Preserve Custom / Other Set entry for EB, PRB, starter decks, promos, and future releases.

## Verification

- Five automated API/integration tests pass.
- JavaScript syntax validation passes.
- Tests cover upgrades, scanner order, image swapping, label gating, recycling, restoration, eligible purge, and sold-record purge protection.
- Automated browser screenshots could not be completed because the embedded browser could not reach the local preview in this workspace session.
