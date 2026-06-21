# Dex v1.1b-test Patch Notes

## Focus

This release is a quality-of-life pass for faster batch review after the first v1.1a live tests.

## Added

- Batch-first inbound layout: bulk drag-and-drop is now the primary intake action.
- Collapsed **Add One Card** panel for flatbed scans, rescans, and high-value one-offs.
- Batch-card selection checkboxes with **Select All** and **Clear** controls.
- Bulk actions for selected batch cards:
  - Bulk Edit shared fields.
  - Print/Reprint selected labels.
  - Move selected cards to Recycle Bin.
- Bottom **Finish & Print Labels** action under the Batch Cards grid.
- **Move Batch to Recycle Bin** action from the Inbound batch list and open batch summary.
- Inventory search now finds sold cards by sale order number.
- Sales rows with an order number can jump to matching sold cards in Inventory.
- Unified One Piece **Set** entry field for OP, EB, PRB, and future manually typed sets.

## Changed

- Removed separate **Custom Set Code** and **Custom Set Name** fields.
- Updated release metadata, Docker labels, compose defaults, Jenkins tags, and footer to `v1.1b-test`.
- Compose now uses separate `storage-v1.1b-test` and `scanner-inbox-v1.1b-test` folders.
- Hotfix: made batch-card selection visible by default, added click-to-select on the card body, and refreshed browser cache tags so old interface files do not linger.
- Hotfix: tightened New Inbound Batch form alignment so labels, inputs, and helper text line up consistently.
- Hotfix: large scan imports now upload in smaller chunks to avoid browser string-size failures during 50+ card batches.
- Batch recycle is a soft delete: every active card in the batch moves to Recycle Bin, the batch leaves the Inbound list, and Undo restores the batch and its cards together.

## Verified

- Automated API test suite passes: 6/6.
- JavaScript syntax check passes.
- Added coverage for Inventory search by sale order number after an outbound sale.
- Added coverage for batch recycle, Recycle Bin visibility, hidden inbound batch behavior, and Undo restore.
- Field test confirms the lower **Finish & Print Labels** action appears below the inbound Batch Cards grid.
- Field test issue addressed: importing 58 card pairs no longer builds one oversized browser payload.

## Notes

- Labels still intentionally queue after batch completion, not while an inbound batch is open.
- The heavier recognition/pricing/market-watch work remains planned for Version 2.
