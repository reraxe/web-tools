# Dex What's New Hub Plan

## Feature Goal

Turn **What's New** into Dex's information hub: a place to see app updates, inventory workflow reminders, market-watch notes, and upcoming work without leaving Dex.

## Sidebar Placement

Add **What's New** near the lower-left sidebar, above the TCGplayer Capacity panel. This keeps it visible without competing with daily inventory work.

## Recommended Sections

### 1. Dex Updates

Purpose: show what changed in the current version.

Content:

- Current version
- Patch notes
- New buttons/features to test
- Known issues
- Next planned release

Best first implementation:

- Read local patch note files from the Dex repo.
- Show the newest release first.
- Keep it static/offline so it works without internet.

### 2. Daily Agenda

Purpose: keep the day focused.

Content:

- Current active target version
- Work-hours tasks
- Home/scanner tasks
- Waiting-on items

Best first implementation:

- Show a small editable or server-managed list.
- Start by displaying the current `DAILY_AGENDA.md` content in the app.

### 3. Market Watch

Purpose: summarize TCG movement, hype, releases, and buying/selling signals.

Content:

- One Piece market notes
- Pokemon market notes
- Watchlist cards
- New release calendar
- Social sentiment notes
- Links/sources reviewed
- Suggested action: hold, list, watch, research

Best first implementation:

- Manual Market Watch posts written or pasted into Dex.
- Later: AI-assisted summaries from approved sources.
- Do not auto-trust unsourced social posts. Treat them as signals, not facts.

### 4. Inventory Opportunities

Purpose: connect market info to your actual Dex inventory.

Content:

- Cards in inventory that may be worth listing
- Cards under TCGplayer $20 threshold
- eBay candidates above $20
- Cards missing prices
- Cards missing SAM match confidence

Best first implementation:

- Use existing Dex inventory fields.
- Add filters such as "Needs Price", "eBay Candidate", and "TCGplayer Candidate".

### 5. Coming Soon

Purpose: show roadmap without digging through notes.

Content:

- SAM improvements
- OPTCG API cache
- eBay connector
- TCGplayer bridge
- DPS pre-grading
- What's New/Market Watch automation

Best first implementation:

- Static roadmap cards based on version plan files.

## Suggested v2 Release Split

### v2.0-test

- SAM source-database matching.
- Keep What's New as documentation/backlog only.

### v2.1-test

- Add the actual **What's New** sidebar page.
- Display local patch notes and daily agenda.
- Add static roadmap cards.

### v2.2-test

- Add Market Watch posts.
- Let the user paste or upload market-watch text.
- Store posts in SQLite.
- Add tags such as One Piece, Pokemon, eBay, TCGplayer, Watchlist.

### v2.3-test

- Connect Market Watch to inventory.
- Surface "You own this card" and "Potential listing candidate" notes.
- Add price/watchlist tasks.

### v2.4-test or Later

- Add online source collection if credentials, APIs, and HTTPS are ready.
- Add AI-assisted summary generation with source links.

## Market Watch Source Rules

Use a source score so Dex does not treat every hype post equally:

| Source type | Trust level | Use |
| --- | --- | --- |
| Official game/release sites | High | Release dates, set names, card lists |
| eBay completed sales | High | Real sale comps |
| TCGplayer market/sales data | High if API/export available | Pricing and demand |
| Established TCG articles/blogs | Medium | Trends and context |
| YouTube/Reels/TikTok creators | Medium/Low | Early hype signals |
| Random posts/comments | Low | Watch only |

## UX Recommendation

The page should feel like a dashboard, not a blog archive.

Top cards:

- Current Dex version
- Last market watch
- Cards to review
- Waiting on API/credentials

Main tabs:

- Updates
- Market Watch
- Inventory Signals
- Roadmap

## Data Model Idea

Create a future SQLite table:

```text
news_posts
  id
  created_at
  title
  category
  tags
  summary
  body
  source_name
  source_url
  source_trust
  related_game
```

Optional future table:

```text
news_card_links
  post_id
  card_number
  card_name
  signal_type
```

## First Build Recommendation

Start simple:

1. Add **What's New** to the sidebar.
2. Show current version and patch notes.
3. Show today's agenda.
4. Show the roadmap.
5. Add a placeholder Market Watch tab.

Then build the market intelligence layer once SAM is stable.
