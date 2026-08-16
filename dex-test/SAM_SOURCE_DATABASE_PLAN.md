# SAM One Piece Reference Library Plan

SAM uses a local One Piece reference library as one evidence layer. This folder is not inventory and is not the sole identity authority. Phase 7 combines physical-scan evidence, cached structured OPTCG metadata, acquisition/batch context, and local reference comparison.

## Server Folder

Docker maps this host folder:

```text
source-database-v2.0-test/
```

to this container folder:

```text
/source-database
```

Dex scans the folder recursively, so subfolders are allowed. `DEX_ONE_PIECE_REFERENCE_DIR` selects the library and defaults to `DEX_SOURCE_DB_DIR`; never hardcode a workstation path. In Docker it defaults to `/source-database`.

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

Legacy Dex can read CSV files anywhere inside the source tree. Phase 7's provider-neutral index records image/reference facts and enriches them from the normalized OPTCG cache when available. Missing metadata remains Unknown.

## Indexing and Preservation

Phase 7 indexing is incremental and resumable:

- SHA-256 is checked on every configured image;
- unchanged files are skipped;
- changed/new files are indexed;
- exact duplicate hashes and near-duplicate visual families are recorded;
- index runs record status, version, counts, duration, and errors;
- derived hashes/features live in SQLite, while image bytes remain external.

DEX never renames, relocates, resizes, overwrites, watermarks, or otherwise normalizes the original reference files. Mount the library read-only where practical and back it up independently from inventory storage.

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
5. Click **Index references**.
6. Optionally refresh OPTCG structured metadata for the test card numbers.
7. Continue One Piece Scan & Identify intake or open SAM.
8. Review the Matched, Needs Review, and Unidentified lanes.
9. Compare the physical scan with SAM's best/alternate reference; confirm, Find Match and correct, or leave unidentified.

## Structured Metadata Provider

Phase 7 integrates `optcgapi.com` behind a provider-neutral service. Requests contain structured card-number/search data only. DEX never sends physical scans or local reference images. Normalized results retain provider, source key, provider/version information, fetch/refresh timestamps, and active/stale/missing state.

Recognition does not depend on a live request. Provider outage or missing/new card coverage falls back to cached metadata, local reference evidence, and manual Find Match. External metadata never silently overwrites an operator-confirmed identity.

## Future Knowledge Sources

The provider/reference interfaces can later support other sources and games, but Phase 7 recognizes One Piece only:

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

Reference images do not belong in SQLite, DEX release packages, or Git. SQLite stores only normalized metadata, source references, hashes/features, duplicate relationships, index state, and recognition evidence. Physical inventory scans remain in DEX inventory storage and are not transmitted to the metadata provider.

## Do Not Put In GitHub

Do not commit the reference image database to GitHub. Keep references on a private operator-controlled volume. Git keeps DEX code, tests, and documentation only; the operator controls reference and inventory data.
