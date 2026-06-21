# Dex v1.1-test Patch Notes

Released for testing on June 20, 2026. This is a separate test release and does not replace `v1.0-stable`.

## Faster inbound organization

- Upload a complete group of front/back scans in one selection.
- Pair files by `_front` and `_back` names first, then by scan order.
- Assign a unique SKU to every physical card in a bulk upload.
- Display every card in a responsive batch grid with its image, identity, SKU, and status.
- Keep rarity and variant selections while moving through **Save and next** intake.
- Reopen completed batches with **Add more cards** while preserving existing SKUs and labels.
- Reprint one physical card label without reprinting the entire batch.

## Corrections

- Completed inbound batches now display **Complete**, not **Sold**.
- **In stock** and **Needs review** dashboard totals no longer count the same card twice.
- Batch and SKU dates use the configured business timezone.
- Camera errors distinguish unsecured HTTP, unavailable camera access, and unsupported QR detection.
- Long SKUs and descriptions fit within the 2 x 1 thermal label layout.

## Daily controls

- TCGplayer capacity is configurable and defaults to 500.
- Settings show recent supported inventory actions.
- **Undo** restores the most recent supported card edit, batch status change, or outbound sale.
- Inventory CSV includes per-card sale price and order financials.
- Sales CSV provides one row per order with SKUs, subtotal, shipping, fees, postage, and net proceeds.

## Deployment safety

- Docker, health metadata, and UI report `v1.1-test`.
- Test compose defaults to port `8081`, container `dex-v1.1-test`, and separate test storage folders.
- Jenkins tags the test release without overwriting the stable `latest` image.

## Deferred to Version 2

- OCR and automatic card identification.
- OPTCG API catalog synchronization and image matching.
- Pokemon catalog support.
- Automated eBay and TCGplayer market pricing.
