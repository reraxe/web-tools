# Dex Operating Model

Last updated: 2026-06-23

## Big Picture

Dex is becoming the home base for a small TCG business. The goal is to make physical inventory, market awareness, pricing, and listing decisions work together without losing track of individual cards.

## System Roles

### Dex: Inventory System

Dex owns the source of truth for physical inventory.

Responsibilities:

- receive inbound cards
- assign physical SKUs
- create QR labels
- store front/back scan images
- track drawer location
- track status: review, in stock, listed, sold, recycled
- track outbound sales and order history

Rule:

- Dex does not guess silently. If data is uncertain, it marks the card for review.

### SAM: Sniff And Match

SAM automates inbound identity work.

Responsibilities:

- compare scanned cards to the local source database
- fill card number, name, set, rarity, color, and card type when confident
- keep low-confidence matches in Needs Review
- reduce typing during batch intake
- preserve the physical SKU assigned by Dex

Inputs:

- scanned card images
- local source images
- CSV metadata
- future API cache data

Outputs:

- suggested card identity
- confidence score
- match source
- review status

### Janna: Market Watch

Janna is the market intelligence layer.

Responsibilities:

- track TCG market news
- monitor relevant prices and completed-sales signals
- summarize current demand
- flag market interest in stored inventory
- recommend whether a card should be held, watched, listed, or repriced
- suggest where to post: eBay or TCGplayer

Inputs:

- manual Market Watch posts
- official release/news sources
- eBay completed sale data when available
- TCGplayer data when available
- Dex inventory data
- future source APIs and cached market data

Outputs:

- market report
- watchlist cards
- pricing signals
- platform recommendation
- inventory action suggestions

Rule:

- Janna gives recommendations. Dex should keep the final action reviewable before changing live listings or business-critical prices.

### Project: Goose

Project: Goose is the ShonenRiot sourcing and sales-support tool. It turns Janna's market report into practical pricing and listing decisions inside Dex.

Responsibilities:

- read Janna market signals
- compare recommendations against current Dex inventory
- suggest price updates
- mark cards as eBay candidates or TCGplayer candidates
- track inventory value movement and top movers through Portfolio Analytics
- help separate "sell now" cards from "store until interest" cards
- support sourcing and sales decisions

Inputs:

- Janna market report
- Dex inventory
- current price fields
- marketplace fee/shipping assumptions
- TCGplayer listing capacity
- eBay/TCGplayer API data if available later

Outputs:

- suggested listing price
- suggested platform
- suggested action: list, hold, watch, review, reprice
- top-gainer/top-loser notes from portfolio movement
- confidence/reason notes

Rule:

- Goose should start as recommendation-only. Automatic price changes can come later after the algorithm proves itself.

### DPS: Dex Pre-Grading System

DPS is the high-value-card condition screening layer.

Responsibilities:

- analyze high-resolution flatbed scans
- measure centering
- inspect corners and edges
- flag visible surface or print concerns
- create an evidence-first condition report
- help decide whether a card should be sold raw, held, or submitted for grading

Inputs:

- front/back flatbed scans
- optional angled-light photos
- card SKU and inventory history
- Janna/Goose market value context later

Outputs:

- capture quality result
- centering ratios
- defect/evidence map
- sub-scores
- DPS condition range
- confidence level
- grading/submission recommendation later

Rule:

- DPS is not an official third-party grade. It is an internal pre-screen with evidence and uncertainty.

## Physical Workflow

1. Open product: booster box, packs, purchase, trade, or existing stock.
2. Sort cards by set/color/finish as needed.
3. Scan or upload cards into Dex.
4. Dex creates SKUs and QR labels.
5. SAM identifies cards and fills details.
6. Cards move into drawers as inventory.
7. Janna watches the market.
8. Goose recommends which cards to sell now and where to list them.
9. User physically separates:
   - sell-now cards
   - hold/watch inventory
10. User posts cards using Goose recommendations.
11. Outbound sales are scanned back into Dex.

## Pricing Philosophy

Price changes should move through stages:

1. **Manual price fields**: user enters or edits prices.
2. **Janna suggestions**: market report recommends price movement.
3. **Goose recommendations**: Dex shows suggested platform and listing price.
4. **One-click apply**: user approves price updates.
5. **Automation later**: only after enough confidence and audit logs exist.

## Listing Platform Rules

Early rules:

- Under $20: usually TCGplayer.
- $20 and above: usually eBay because tracking/shipping math matters.
- High market volatility: review manually.
- Missing confidence or price data: do not auto-list.

Future rules can include:

- TCGplayer capacity
- eBay seller limits
- shipping cost
- platform fee estimates
- recent completed sales
- current inventory depth
- expected demand

## Version Path

### v2.0-test

- SAM source-database matching.
- Manual inventory review remains available.

### v2.1-test

- What's New hub.
- Roadmap and patch notes inside Dex.

### v2.2-test

- Janna starts as manual Market Watch posts.
- Market Watch notes stored in Dex.

### v2.3-test

- Goose starts as inventory signals.
- Show sell/hold/watch recommendations.
- Show eBay/TCGplayer candidate status.

### v2.4-test

- Add pricing recommendation fields.
- Support one-click apply for reviewed price suggestions.

### v2.5-test and Later

- Add Portfolio Analytics for inventory value graphs and top movers.
- Add marketplace connectors if API credentials and HTTPS are ready.
- Add scheduled market updates.
- Add stronger source scoring and audit trails.

### v3.0-test and Later

- Start DPS for high-value card pre-grading.
- Tie reports to physical SKUs.
- Keep DPS separate from official grading outcomes.

## Safety Rules

- Never overwrite physical inventory identity without review.
- Never auto-delete cards; use Recycle Bin first.
- Never store marketplace secrets in GitHub.
- Never auto-post listings until the workflow is proven.
- Always keep an audit trail for price and status changes.
- Never present DPS as an official PSA, Beckett, TAG, CGC, or third-party grade.
