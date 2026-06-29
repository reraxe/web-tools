# Dex v2.0-test Patch Plan

Status: implemented for v2.0-test

## Theme

Reduce manual card entry by letting Dex recognize One Piece cards from scan images, then use a local card database to fill the boring fields.

## Main Goals

- [x] Add AI-lite card recognition for One Piece through SAM.
- [x] Match front scan images against a local source image database.
- [x] Match known card numbers against a local One Piece card database.
- [x] Auto-fill card name, set, color, rarity, and card number when Dex has a confident match and metadata is available.
- [x] Keep uncertain matches in `Needs Review` instead of guessing.

## New Inventory Concepts

- Card identity: the card type, such as `OP16-067`.
- Physical SKU: the individual physical copy, such as `OP-B20260621-074`.
- Listing identity: marketplace grouping, such as `OP16-067-NM-STANDARD`.
- Drawer location: physical home, such as `OP16-PURPLE`.

## UI/UX Changes

- [x] Show each batch card with:
  - Card name
  - Card number
  - Dex SKU
  - Match confidence
  - Match source
- [x] Add match source labels:
  - Manual
  - Card Number
  - Database
  - Visual Review
- [x] Add SAM Match actions for selected cards, full batches, and individual cards.
- [x] Keep `Needs Review` for cards that are missing a confident match.
- [x] Make the review flow feel like approving suggestions, not typing everything manually.

## Database/API Work

- [x] Add a local One Piece card reference table.
- [x] Add import/update support from a local source folder and optional CSV metadata.
- [x] Store card matching metadata:
  - matched card number
  - confidence score
  - match source
  - reviewed status
- [x] Keep marketplace API work separate from v2.0-test.

## First Supported Scope

- [x] Game: One Piece
- [x] Method: source image fingerprint matching first, with exact card-number matching when available.
- [x] Best first use case: one set per batch, such as `OP16 - The Time of Battle`
- [x] Manual fallback remains available for every card.

## Out Of Scope For v2.0-test

- Full cloud AI recognition by artwork alone.
- Pokemon recognition.
- Riftbound recognition.
- Auto-posting to eBay or TCGplayer.
- Fully automated marketplace order syncing.
- DPS pre-grading.

## Success Criteria

- Dex can take a batch of One Piece front scans and identify obvious card numbers.
- Matched cards auto-fill card details from the local database.
- Low-confidence cards stay in `Needs Review`.
- User can approve or correct matches quickly.
- Existing inbound, labels, outbound, recycle bin, and inventory workflows still pass tests.

## Risk Notes

- OCR/card-number detection may struggle with glare, skew, dark borders, or low contrast.
- Different One Piece layouts may require targeted detection rules.
- The local card database needs periodic updates.
- AI-lite should assist the workflow, not become a required gate.
