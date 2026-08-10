# Olive Network — Phase 1: Archive Extraction

## Goal
Extract ~2,000 published items from olivenetwork.org (a proprietary ASP.NET
platform we don't control) into portable Markdown files + local images, with
zero data loss and a verifiable manifest. This is a one-off migration job —
not a scraper we'll run repeatedly.

## Before writing scraper logic — check these first
1. `https://olivenetwork.org/robots.txt` — respect it. If crawling is
   disallowed for the paths we need, stop and flag to the human rather than
   proceeding.
2. Fetch one category page and one item page manually (curl or a quick
   script) and actually read the HTML. Do not assume the selectors below —
   they're best guesses from a homepage-only view, not from the item page
   markup, which nobody here has inspected yet.
3. Check whether pagination ("More..") is a normal link, a POST postback
   (`__doPostBack`), or an AJAX call. If it's a WebForms postback (likely,
   given the platform), plain requests+BeautifulSoup can't follow it and
   we'll need Selenium/Playwright instead. Confirm this before building the
   rest — it changes the whole approach.
4. Add a delay between requests (start at 1–2s) and a proper User-Agent.
   Don't hammer someone else's server.

## What we know
- Category index pages (12 total), e.g. `/climate/11`, `/arts-culture/483`,
  `/charities/412`, `/dwelling/477`, `/economics/1111`, `/education/181`,
  `/environment/21`, `/health/30`, `/humanitarian/461`, `/science-tech/59`,
  `/sustainability/113`, `/un/553`.
- Item URLs follow the pattern `/Issue/{slug}/{id}`. IDs are non-contiguous
  (recent ones run up to ~26,324) — don't try to enumerate by ID, only by
  crawling the category indexes.
- No login appears to be required to read items (verify this holds for all
  categories, not just the homepage).

## Two-step pipeline

**`discover.py`** — crawl all 12 category indexes + pagination, collect
every item URL with slug/id/category. Output: `manifest.csv` with columns
`id, slug, category, url, status` (status starts `pending`).

**`scrape.py`** — read `manifest.csv`, visit each pending URL, extract:
- title
- publication date
- byline / source attribution (may say "ON Network" or name original outlet)
- body content → convert to Markdown (not raw HTML)
- all images in the body → download to `images/{id}/`

Write each item to `articles/{id}-{slug}.md` with YAML front-matter:

```yaml
---
title: "..."
date: 2026-08-06
category: "Arts & Culture"
source: "..."
original_id: 26323
original_slug: "featured-artwork-marie-claire-hamon-sorrow"
original_url: "https://olivenetwork.org/Issue/featured-artwork-marie-claire-hamon-sorrow/26323"
images: ["images/26323/01.jpg"]
---

body content in markdown
```

Update `status` to `done` or `failed` in the manifest as you go, so the
script is safely resumable if it dies partway through 2,000 items.

## Acceptance criteria
- Every item in the manifest is `done` or `failed` with a reason logged.
- Spot-check ~10 output files by eye against the live pages before calling
  it finished.
- Final counts (items found vs. items successfully scraped) reported back
  in plain terms — this is what tells us whether anything was missed.

## Explicitly out of scope for this phase
- No selection/curation of which items are "real" Olive vs. syndicated
  reposts — that's a separate editorial decision, keep everything for now.
- No publishing anywhere. This is extraction only.
