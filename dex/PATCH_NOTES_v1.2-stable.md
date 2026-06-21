# Dex v1.2-stable Patch Notes

## Focus

This stable release promotes the tested v1.1b workflow for weeklong real inventory use.

## Added

- Searchable **Color** picker on the New Inbound Batch form.
- Searchable **Color** picker on Change Scan Group.
- Common One Piece color values and combinations:
  - RED, GREEN, BLUE, PURPLE, BLACK, YELLOW.
  - Two-color combinations such as RED/GREEN, BLUE/PURPLE, and BLACK/YELLOW.
  - MULTI, MIXED, and COLORLESS.

## Changed

- Known color choices normalize automatically, so `purple`, `Purple`, and `PURPLE` become `PURPLE`.
- Drawer auto-location remains based on set and color, such as `OP16-PURPLE`.
- Version metadata, Docker label, Jenkins tag, compose defaults, footer, and API health response now report `v1.2-stable`.
- Compose uses `storage-v1.2-stable` and `scanner-inbox-v1.2-stable` by default.

## Carried Forward From v1.1b-test

- Batch-first inbound intake.
- Bulk scan import chunking for large batches.
- Collapsed Add One Card panel.
- Batch-card selection, bulk edit, selected label reprint, and selected recycle.
- Batch recycle with Recycle Bin behavior.
- Bottom Finish & Print Labels action.
- Sold-card search by order number.

## Verified

- JavaScript syntax check passes.
- Python compile check passes.
- Automated API test suite passes.

## Notes

- To keep existing test inventory, copy `storage-v1.1b-test` to `storage-v1.2-stable` before starting this stable compose file.
- Version 2 remains the next test lane for catalog intelligence, pricing automation, market watch, and AI-assisted recognition.
