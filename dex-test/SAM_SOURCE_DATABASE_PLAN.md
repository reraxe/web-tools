# SAM Source Database Folder Plan

SAM uses a local source database as its reference shelf. This folder is not inventory. It is only the known-card library Dex uses to identify scanned physical cards.

## Server Folder

For `v2.0-test`, Docker maps this host folder:

```text
source-database-v2.0-test/
```

to this container folder:

```text
/source-database
```

Dex scans the folder recursively, so subfolders are allowed.

## Recommended Layout

```text
source-database-v2.0-test/
  one-piece/
    OP01 - Romance Dawn/
      OP01-001.png
      OP01-002.png
      OP01-003.png
    OP16 - The Time of Battle/
      OP16-001.png
      OP16-067.png
      OP16-112.png
    EB01 - Memorial Collection/
      EB01-001.png
      EB01-002.png
    PRB02 - ONE PIECE CARD THE BEST Vol. 2/
      PRB02-001.png
      PRB02-018.png
  metadata/
    one-piece-card-list.csv
  incoming/
    unsorted-source-files-go-here-temporarily/
```

## File Naming Rules

Source-card images should use the card number as the filename:

- Good: `OP16-067.png`
- Good: `EB01-001.jpg`
- Good: `PRB02-018.webp`
- Also okay: `OP16-067_small.jpg`
- Avoid: `image2223.png`

Your physical scanner files can still be named `image2223.png`, `image2224.png`, and so on. Only the source database needs clean card-number filenames.

## Image Format

SAM supports:

- `.png`
- `.jpg`
- `.jpeg`
- `.webp`

Use the full-size source image when possible. Small images are useful as previews, but full images are better for matching.

## Optional Metadata CSV

Images alone can identify card number and set code. A CSV lets Dex fill more fields automatically.

Recommended CSV columns:

```csv
card_number,name,set_code,set_name,rarity,color,card_type
OP16-067,Tsuru,OP16,The Time of Battle,Uncommon,Purple,Character
OP16-112,Boa Hancock,OP16,The Time of Battle,Super Rare,Yellow,Character
EB01-001,Kozuki Oden,EB01,Memorial Collection,Leader,Red,Leader
```

Dex can read CSV files anywhere inside `source-database-v2.0-test`, but keeping them in `metadata/` makes the folder easier to manage.

## First Pilot Plan

Start with one set:

```text
source-database-v2.0-test/
  one-piece/
    OP16 - The Time of Battle/
      OP16-001.png
      OP16-002.png
      ...
      OP16-126.png
  metadata/
    op16-card-list.csv
```

Then test with one physical OP16 scan batch sorted by color.

## Dex Workflow

1. Copy source images into `source-database-v2.0-test`.
2. Add or update the metadata CSV if available.
3. Open Dex.
4. Go to **SAM**.
5. Click **Rescan Source**.
6. Open an inbound batch.
7. Use **SAM Match All** or **SAM Match Selected**.
8. Review low-confidence or unmatched cards manually.

## Future API Knowledge Sources

SAM starts with local images and CSV files. The broader Dex card knowledge database should also track API/cache sources:

- One Piece: https://optcgapi.com/
- Magic: The Gathering: https://mtgjson.com/
- Pokemon support data: https://pokeapi.co/

See `CARD_KNOWLEDGE_DATABASE_PLAN.md` for the full source plan and cache layout.

## What Goes Where

| File type | Folder |
| --- | --- |
| Known reference card images | `source-database-v2.0-test/` |
| Optional known-card CSV metadata | `source-database-v2.0-test/metadata/` |
| New physical card scans | Dex inbound batch upload or `scanner-inbox-v2.0-test/` |
| Dex inventory database/images | `storage-v2.0-test/` |

## Storage Notes

The source database should be small enough for the home server. Even thousands of One Piece card images are likely much smaller than the 1 TB drive you mentioned. Full-size images are worth keeping for matching quality, and we can add compression later if the folder grows too large.

## Do Not Put In GitHub

Do not commit the full source image database to GitHub unless you intentionally want that repo to become large. Keep source images on the server volume. GitHub should keep Dex code; the server should keep Dex data.
