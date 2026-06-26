# Portfolio Analytics Plan

Last updated: 2026-06-24

## Purpose

Portfolio Analytics turns Dex inventory into a stock-portfolio-style view of the card business.

It should answer:

- What is the total market value of inventory?
- How has inventory value changed over time?
- Which cards moved up the most?
- Which cards moved down the most?
- Which cards should Goose consider for listing or repricing?

## Recommended Placement

Create a separate **Portfolio** page later, with a small dashboard preview on the Inventory page.

Why separate:

- the charts need more screen space
- time-frame controls deserve room
- top movers need context
- this becomes a business analytics page, not just an inventory table

Inventory page preview:

- total inventory value
- 24-hour change
- top positive mover
- top negative mover
- link to Portfolio

## Main Views

### 1. Total Inventory Value

Graph total inventory market value over time.

Formula:

```text
sum(quantity owned * market_average)
```

Later we can allow low/average/high views.

### 2. Portfolio Change Graph

Show value changes like a stock portfolio.

Time frames:

- daily
- weekly
- monthly
- quarterly
- yearly

Metrics:

- total value
- dollar change
- percent change
- number of cards gaining value
- number of cards losing value
- number of cards with missing price data

### 3. Top Movers

Show:

- top 3 positive movers
- top 3 negative movers

Recommended fields:

- card image
- card name
- card number
- quantity owned
- old market average
- new market average
- dollar change
- percent change
- suggested action from Goose

### 4. Value By Game / Set / Location

Useful later:

- One Piece vs Pokemon vs other games
- value by set
- value by drawer
- value by platform candidate
- value by status

## Data Needed

Dex currently stores current market values on each card. Portfolio graphs need historical snapshots.

Future SQLite table:

```text
market_snapshots
  id
  captured_at
  card_identity
  game
  set_code
  card_number
  variant
  condition
  market_low
  market_average
  market_high
  source
```

Future inventory-value table or view:

```text
portfolio_snapshots
  id
  captured_at
  total_market_low
  total_market_average
  total_market_high
  total_cards_counted
  total_cards_missing_price
```

Dex can calculate portfolio snapshots from inventory + market snapshots.

## Price Source Rules

At first:

- use manually entered prices
- snapshot whenever price is updated
- optionally run a daily snapshot even if nothing changes

Later:

- Janna pulls market/pricing notes
- Goose suggests price updates
- user approves
- Dex records the new price snapshot

With marketplace APIs:

- eBay completed sales can feed real comps
- TCGplayer pricing can feed market values if API/export access exists

## Goose Integration

Goose should use Portfolio Analytics to recommend:

- list now
- hold
- watch
- reprice
- move to eBay
- move to TCGplayer

Example:

```text
OP16-112 Boa Hancock
Change: +18.4% weekly
Owned: 3
Suggested action: List 1 on eBay, hold 2.
Reason: Positive weekly movement and market average above $20.
```

## Version Path

### v2.3-test

- Start inventory signals.
- Add missing-price and platform-candidate filters.

### v2.4-test

- Add Goose recommendation fields.
- Add reviewed pricing recommendations.

### v2.5-test

- Add Portfolio page foundation.
- Store price snapshots.
- Show total inventory value graph.
- Show top 3 gainers and top 3 losers.

### v2.6-test or Later

- Add daily/weekly/monthly/quarterly/yearly controls.
- Add game/set/location breakdowns.
- Connect to Janna market reports and marketplace APIs if available.

## Safety Rules

- Do not overwrite prices silently.
- Always record price source.
- Show missing-price counts so portfolio value is not misleading.
- Treat market value as an estimate, not cash in hand.
- Keep realized sales separate from unrealized inventory value.
