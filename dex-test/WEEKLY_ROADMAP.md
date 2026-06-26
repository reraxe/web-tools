# Dex Weekly Roadmap

Last updated: 2026-06-23

## Release Cadence

Dex should move in weekly, low-drama steps.

- Weekdays, 9-5: testing, bug logging, docs, source database prep, API planning, and small quality-of-life improvements.
- Evenings: scanner/server checks, SAM matching tests, labels, outbound sales, and physical workflow validation.
- End of week: decide whether the active test version is stable enough to promote.
- Stable versions are used for real inventory work.
- Test versions are where we add new features and shake them down.

## Promotion Rule

A test version can become stable after:

- core tests pass
- no active blocker bugs remain
- scanner/import flow works
- labels print correctly
- outbound flow works
- Recycle Bin/undo behavior works
- user has run at least one real inventory session without major pain

## Current Active Lane

### v2.0-test: SAM One Piece Recognition

Goal: reduce manual card entry by matching One Piece scans against a local source database.

Weekday focus:

- Build and refine the source database folder.
- Run API/backend tests.
- Improve docs and test scripts.
- Log SAM mismatch patterns.
- Decide what confidence scores feel trustworthy.

Home/server focus:

- Load OP16 source images.
- Rescan SAM source.
- Import a small OP16 batch.
- Run SAM Match All.
- Check label queue after matching.

Potential promotion:

- `v2.0-test` can become `v2.1-stable` if SAM is useful enough and does not disrupt the stable inventory workflow.

See `DEX_OPERATING_MODEL.md` for the full Dex, SAM, Janna, and Project: Goose workflow.

## Next Planned Versions

### v2.1-test: What's New Hub

Goal: put Dex updates, daily agenda, roadmap, and known issues inside the app.

Scope:

- Add **What's New** to the sidebar near the lower-left utility area.
- Show current version.
- Show patch notes.
- Show daily agenda.
- Show roadmap cards.
- Keep Market Watch as a placeholder tab for now.

Why next:

- It helps us test weekly without losing track of what changed.
- It makes Dex feel more like an operating system for the business.

### v2.2-test: One Piece API Cache + Manual Market Watch

Goal: start Janna, the Market Watch layer, and turn Dex into a card knowledge and market awareness tool.

Scope:

- Add OPTCG API cache planning or first adapter.
- Add local/manual Market Watch posts for Janna.
- Store Market Watch notes in SQLite.
- Tag posts by game, set, marketplace, and watchlist.
- Summarize market notes into hold, watch, list, and research signals.

### v2.3-test: Inventory Signals

Goal: start Project: Goose as recommendation-only inventory and sales support.

Scope:

- Show cards missing prices.
- Show TCGplayer candidates under $20.
- Show eBay candidates at $20+.
- Show cards with low SAM confidence.
- Show sell, hold, watch, and review recommendations from Janna signals.
- Begin CardDex/MTGJSON source planning.

### v2.4-test: Pricing Recommendations

Goal: let Goose suggest price changes without silently changing business-critical fields.

Scope:

- Add suggested price fields.
- Add suggested platform fields.
- Add recommendation reasons.
- Add one-click apply after user review.
- Keep automatic price adjustment out of scope until the algorithm is proven.

### v2.5-test: Portfolio Analytics

Goal: add stock-portfolio-style inventory value tracking.

Scope:

- Add price snapshot storage.
- Add total inventory market value graph.
- Add daily, weekly, monthly, quarterly, and yearly time frame controls.
- Show top 3 positive movers.
- Show top 3 negative movers.
- Keep realized sales separate from unrealized inventory value.

See `PORTFOLIO_ANALYTICS_PLAN.md` for the full value graph, snapshot, and top-movers plan.

### v2.6-test: Marketplace Connector Prep

Goal: prepare eBay connection once developer approval and HTTPS are ready.

Scope:

- eBay credentials checklist.
- OAuth connection screen.
- Server-only token storage plan.
- Listing/order mapping table.
- No auto-posting until the flow is proven.

### v2.7-test: Broader Card Knowledge Sources

Goal: expand source data planning beyond One Piece.

Scope:

- CardDex adapter research for Pokemon TCG.
- PokeAPI support metadata plan.
- MTGJSON import size and useful-field review.
- Decide what belongs in Dex now versus later.

### v3.0-test or Later: DPS

Goal: Dex Pre-grading System for high-value cards.

Scope:

- Flatbed scan workflow.
- Centering measurements.
- edge/corner review.
- surface scan report.
- score summary and confidence notes.

See `DPS_PLAN.md` for the full DPS capture, measurement, validation, and safety plan.

## Weekday Work Menu

Good tasks while away from the scanner:

- Run automated tests.
- Update patch notes.
- Review screenshots.
- Write test checklists.
- Build small UI improvements.
- Prepare card/source metadata.
- Plan API credentials and storage.
- Document bugs from server testing.

Tasks that need home/scanner/server time:

- actual scan imports
- source image uploads to the server
- SAM matching against real scans
- label printing
- outbound phone scan tests
- HTTPS/camera tests
- Docker/Jenkins deployment checks

## Daily Question

Each morning, answer:

```text
What version are we testing today, and what is the one thing that would make it better?
```

If there is no clear upgrade needed, we stabilize instead of adding noise.
