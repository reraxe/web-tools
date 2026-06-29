# Dex Daily Agenda

Last updated: 2026-06-23

## Daily Rhythm

1. Morning check-in: pick the version we are working on and confirm blockers.
2. Work-hours tasks: handle planning, docs, API prep, data cleanup, and design decisions that do not need the scanner or server.
3. Home testing: run scanner, label, inventory, outbound, and server checks.
4. Wrap-up: log bugs, decide what goes into the next test build, and protect the current stable version.

See `WEEKLY_ROADMAP.md` for the version cadence and promotion rules.
See `DEX_OPERATING_MODEL.md` for the Dex, SAM, Janna, and Project: Goose workflow.

## Today: Tuesday, June 23, 2026

Current active target: v2.0-test with SAM.

### Work-Hours Agenda

- Keep eBay API on standby while the developer account is under review.
- Prepare the eBay credentials checklist so nothing sensitive goes into GitHub.
- Define the SAM source-database folder layout for One Piece card images and metadata.
- Define the broader card knowledge database sources: OPTCG API, MTGJSON, CardDex, and PokeAPI.
- Decide the first real SAM test set: start with OP16, then expand to EB/PRB once matching feels reliable.
- Draft the DPS test procedure for the Canon flatbed scanner.
- Plan the "What's New" hub for app updates, daily agenda, market watch, and roadmap notes.

### Home/Test Agenda

- Load One Piece source card images into the server source-database folder.
- Open Dex SAM page and run source rescan.
- Import a small scan batch, then run SAM Match All.
- Check whether SAM fills card number, name, rarity, color, set, and confidence.
- Test labels after SAM matching.
- Note any mismatches or low-confidence results.

### Waiting On

- eBay Developer Program approval.
- TCGplayer API access availability.
- Server HTTPS decision: Caddy, Nginx Proxy Manager, or another reverse proxy.

### Parking Lot

- v2.1-test: What's New hub with patch notes, agenda, and roadmap.
- v2.2-test: OPTCG API cache plus Market Watch posts and manual market notes.
- v2.3-test: Inventory-linked market signals, MTGJSON/CardDex/PokeAPI source planning, plus TCGplayer CSV/API bridge depending on access.
- v2.4-test: eBay connector screen and OAuth setup if developer approval is ready.
- v2.5-test or later: DPS grading lab workflow.
