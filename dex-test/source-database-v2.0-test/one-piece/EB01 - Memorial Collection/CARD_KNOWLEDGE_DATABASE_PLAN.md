# Dex Card Knowledge Database Plan

## Purpose

Dex should keep a local card knowledge database that SAM and future tools can use for card identity, set data, metadata, and market-watch context.

This is separate from inventory. Inventory tracks the physical cards you own. The card knowledge database tracks known card facts.

## Source Priority

| Game | Source | URL | Use in Dex |
| --- | --- | --- | --- |
| One Piece | OPTCG API | https://optcgapi.com/ | Card metadata, English One Piece card database, price context where available |
| Magic: The Gathering | MTGJSON | https://mtgjson.com/ | MTG card data, sets, formats, decks, downloadable JSON/CSV/database files, limited price history |
| Pokemon TCG | CardDex | https://carddex.dev/ | Pokemon TCG card/set lookup, printed card metadata, images, attacks, abilities, legality, and pricing fields |
| Pokemon support data | PokeAPI | https://pokeapi.co/ | Pokemon names, species, types, abilities, sprites, and universe metadata |

## Important Pokemon Note

PokeAPI is excellent for Pokemon universe data, but it is not primarily a Pokemon TCG card database. CardDex looks like a better first candidate for Pokemon TCG card data because it exposes card-specific fields and examples for TCG cards.

Additional candidate to evaluate later:

| Game | Source | URL | Use in Dex |
| --- | --- | --- | --- |
| Pokemon TCG | Pokemon TCG API / Scrydex | https://pokemontcg.io/ | Alternative Pokemon card sets, card IDs, printed card metadata, images, and TCG-specific data if access fits Dex |

## Recommended Local Cache Layout

```text
source-database-v2.0-test/
  api-cache/
    one-piece/
      optcgapi/
        cards.json
        prices.json
        last-sync.json
    magic/
      mtgjson/
        AllPrintings.json
        SetList.json
        last-sync.json
    pokemon/
      pokeapi/
        pokemon.json
        types.json
        species.json
        last-sync.json
    pokemon-tcg/
      carddex/
        cards.json
        sets.json
        last-sync.json
      pokemon-tcg-api-or-other/
        cards.json
        sets.json
        last-sync.json
  one-piece/
    OP16 - The Time of Battle/
      OP16-067.png
      OP16-112.png
  metadata/
    op16-card-list.csv
```

## How Dex Should Use Each Source

### OPTCG API

Use for One Piece card names, set information, card type, color, rarity, and possible pricing support.

Best fit:

- SAM One Piece matching
- OP set dropdowns
- card metadata refreshes
- market-watch signals

### MTGJSON

Use for Magic card knowledge if Dex expands into Magic.

Best fit:

- Magic set/card lookup
- deck/card reference data
- local downloadable database files
- possible market-watch support

### PokeAPI

Use as Pokemon support metadata, not the final Pokemon TCG card source.

Best fit:

- canonical Pokemon names
- type data
- species and evolution context
- image/name help for search and market-watch writing

Not enough by itself for:

- Pokemon TCG card numbers
- Pokemon TCG set names
- Pokemon card rarity
- Pokemon card market identity

### CardDex

Use as the first Pokemon TCG-specific candidate.

Best fit:

- Pokemon TCG card lookup
- Pokemon TCG set lookup
- official-looking card identity fields
- card images
- attacks, abilities, HP, types, weaknesses, retreat cost, regulation marks, and legality data where available
- possible pricing fields if reliable for the card

Questions to confirm before building:

- whether an API key is needed
- usage limits
- terms for caching images/data on a private home server
- whether pricing fields are complete enough for Dex decisions
- exact card ID format Dex should store

## Sync Rules

- Store API/cache data on the server, not GitHub.
- Keep source data refreshes manual at first.
- Add scheduled refresh later after we trust the source and data mapping.
- Log the last sync time per source.
- Never let API refreshes overwrite physical inventory records directly.
- SAM suggestions should stay reviewable before they change important card fields.

## Version Path

### v2.0-test

- Local source images and CSV metadata for One Piece SAM.

### v2.1-test

- Add What's New hub.
- Add visible card knowledge source status if simple enough.

### v2.2-test

- Add OPTCG API cache for One Piece metadata.
- Keep source image matching local.

### v2.3-test

- Start Pokemon and MTG source adapters as planning/spike work.
- Evaluate CardDex as the first Pokemon TCG source.
- Keep PokeAPI as optional Pokemon universe support data.
- Evaluate MTGJSON import size and useful fields.

### Later

- Scheduled source refresh.
- Cross-game SAM expansion.
- Market Watch source linking.
