# Dex v2.0-test Patch Notes

## Focus

This test release introduces SAM, Dex's local One Piece card matcher. SAM compares front scan images against a source database stored on the server, then fills card identity fields when it has a confident match.

## Added

- New **SAM** sidebar page for source database status.
- Source database folder support through `DEX_SOURCE_DB_DIR`.
- One Piece source-card table in SQLite.
- Source rescan endpoint for local card images and optional CSV metadata.
- Image fingerprint matching for scanned front images.
- Card-number exact matching when the card number is already known.
- **SAM Match All** on an inbound batch.
- **SAM Match Selected** in the batch bulk action bar.
- **SAM Match** inside the card edit modal.
- Match metadata on cards:
  - source card ID
  - match confidence
  - match source
  - matched timestamp
- Source-reference preview inside the card editor.
- SAM confidence chips on batch card thumbnails.
- Batch card count badges for duplicate identified cards in the same inbound batch, while keeping every physical card on its own SKU.

## Source Database Format

- Put reference images in `source-database-v2.0-test`.
- Image filenames should include the card number, such as `OP16-067.png` or `EB01-001.jpg`.
- Optional CSV columns:
  - `card_number`
  - `name`
  - `set_code`
  - `set_name`
  - `rarity`
  - `color`
  - `card_type`

## Changed

- Version metadata now reports `v2.0-test`.
- Docker, compose, Jenkins, cache URLs, and footer text now use `v2.0-test`.
- Compose now creates a separate `source-database-v2.0-test` volume folder.
- Batch card tiles now show match status in addition to inventory status.

## Still Manual

- SAM does not yet pull live data from OPTCG API.
- SAM does not yet recognize Pokemon or Riftbound.
- SAM does not auto-price cards.
- Marketplace posting and order syncing remain separate future work.

## Verified

- Python compile check passes.
- JavaScript syntax check passes.
- Automated API test suite passes, including SAM source scan and image match.
