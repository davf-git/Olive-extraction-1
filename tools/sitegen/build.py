#!/usr/bin/env python3
"""
Builds a static review site from the Phase 1 extraction output.

Reads:  manifest.csv, articles/*.md (YAML front matter + markdown body)
Writes: index.html, browse/{id}.html, .nojekyll  (at repo root)

Run from the repo root:  python3 tools/sitegen/build.py
"""
import csv
import glob
import html
import re
from datetime import datetime
from pathlib import Path

import markdown
import yaml
from jinja2 import Environment, BaseLoader

ROOT = Path(__file__).resolve().parents[2]
ARTICLES_DIR = ROOT / "articles"
MANIFEST = ROOT / "manifest.csv"
BROWSE_DIR = ROOT / "browse"

FONT_LINKS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?'
    'family=Barlow:wght@400;500;600;700&'
    'family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&display=swap" '
    'rel="stylesheet">'
)


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "uncategorized"


def load_manifest():
    with open(MANIFEST, newline="", encoding="utf-8") as f:
        return [row for row in csv.DictReader(f) if row["status"] == "done"]


def find_article_file(item_id, slug):
    direct = ARTICLES_DIR / f"{item_id}-{slug}.md"
    if direct.exists():
        return direct
    matches = glob.glob(str(ARTICLES_DIR / f"{item_id}-*.md"))
    return Path(matches[0]) if matches else None


def parse_article(path):
    raw = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.DOTALL)
    if not m:
        return {}, ""
    front = yaml.safe_load(m.group(1)) or {}
    body = m.group(2).strip()
    return front, body


def format_date(d):
    try:
        return datetime.strptime(str(d), "%Y-%m-%d").strftime("%-d %B %Y")
    except Exception:
        return str(d) if d else ""


def to_embed_url(watch_url):
    m = re.search(r"(?:youtube\.com/watch\?v=|youtu\.be/)([\w-]+)", watch_url)
    if m:
        return f"https://www.youtube.com/embed/{m.group(1)}"
    m = re.search(r"vimeo\.com/(\d+)", watch_url)
    if m:
        return f"https://player.vimeo.com/video/{m.group(1)}"
    return None


def render_body_html(body_md):
    # article pages live one directory below root; images are referenced
    # relative to root in the source markdown, so bump them up a level
    fixed = body_md.replace("](images/", "](../images/")
    rendered = markdown.markdown(fixed, extensions=["extra"])

    def swap_for_embed(m):
        url = m.group(1)
        embed_url = to_embed_url(url)
        if embed_url:
            return (
                f'<div class="video-embed"><iframe src="{embed_url}" '
                f'title="Embedded video" loading="lazy" '
                f'allow="accelerometer; autoplay; clipboard-write; encrypted-media; '
                f'gyroscope; picture-in-picture" allowfullscreen></iframe></div>'
                f'<a href="{url}" target="_blank" rel="noopener" class="video-link-sub">Open on original site &#8599;</a>'
            )
        return (
            f'<a href="{url}" target="_blank" rel="noopener" class="video-link">'
            f'&#9654; Watch video</a>'
        )

    rendered = re.sub(
        r'<a href="(https?://[^"]+)">\[Video:[^<]*\]</a>',
        swap_for_embed,
        rendered,
    )
    return rendered


INDEX_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Olive Archive — review build</title>
<meta name="robots" content="noindex, nofollow">
{{ font_links }}
<link rel="stylesheet" href="style.css">
</head>
<body>
<div class="notice"><strong>Private review build.</strong> Not the public Olive Network site — generated from the Phase 1 archive extraction for internal review.</div>
<header class="site-header">
  <div class="wrap">
    <div class="wordmark">OLIVE<span>·</span>ARCHIVE</div>
    <div class="header-note">Phase 1 extraction review</div>
  </div>
</header>

<section class="stats">
  <div class="wrap">
    <div class="stat"><div class="stat-num">{{ total }}</div><div class="stat-label">Items extracted</div></div>
    <div class="stat"><div class="stat-num">{{ date_min }}–{{ date_max }}</div><div class="stat-label">Date range</div></div>
    <div class="stat"><div class="stat-num">{{ categories|length }}</div><div class="stat-label">Categories</div></div>
  </div>
</section>

<div class="wrap">
  <p class="header-note" style="padding-top:18px;margin-bottom:-6px;">The full archive — every item extracted from olivenetwork.org, filterable by category or search.</p>
  <div class="filters">
    <div class="filter-row">
      <div class="chips">
        <button class="chip active" data-category="all">All <span class="n">{{ sample_total }}</span></button>
        {% for cat in categories %}
        <button class="chip" data-category="{{ cat.slug }}">{{ cat.name }} <span class="n">{{ cat.count }}</span></button>
        {% endfor %}
      </div>
      <div class="search-wrap">
        <input id="search" type="text" placeholder="Search titles…" autocomplete="off">
      </div>
    </div>
    <div id="result-count"></div>
  </div>

  <div class="grid">
    {% for item in items %}
    <article class="card" data-category="{{ item.category_slug }}" data-title="{{ item.title_lower }}">
      <div class="card-media {{ 'placeholder' if not item.thumb }}">
        {% if item.thumb %}
          <img src="{{ item.thumb }}" alt="" loading="lazy">
        {% else %}
          <span>{{ item.category }}</span>
        {% endif %}
        <div class="card-tag">{{ item.category }}</div>
      </div>
      <div class="card-body">
        <div class="card-title"><a href="browse/{{ item.id }}.html">{{ item.title }}</a></div>
        <div class="card-date">{{ item.date_display }}</div>
      </div>
    </article>
    {% endfor %}
  </div>
  <div class="no-results">No items match that search.</div>
</div>

<footer class="site-footer">{{ total }} items extracted from olivenetwork.org · generated for internal review, not linked from any public page</footer>

<script src="app.js"></script>
</body>
</html>
"""

ARTICLE_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ item.title }} — Olive Archive</title>
<meta name="robots" content="noindex, nofollow">
{{ font_links }}
<link rel="stylesheet" href="../style.css">
</head>
<body>
<div class="notice"><strong>Private review build.</strong> Not the public Olive Network site — generated from the Phase 1 archive extraction for internal review.</div>
<header class="site-header">
  <div class="wrap">
    <div class="wordmark">OLIVE<span>·</span>ARCHIVE</div>
    <a class="back-link" href="../index.html">&larr; Back to archive</a>
  </div>
</header>

<div class="banner {{ 'placeholder' if not item.banner }}">
  {% if item.banner %}
    <img src="{{ item.banner }}" alt="">
  {% else %}
    <span>{{ item.category }}</span>
  {% endif %}
</div>

<div class="article-wrap">
  <div class="article-meta-top">
    <span class="pill">{{ item.category }}</span>
    <span>{{ item.date_display }}</span>
    <span>·</span>
    <span>{{ item.source }}</span>
  </div>
  <h1 class="article-title serif">{{ item.title }}</h1>
  <div class="article-body">{{ item.body_html | safe }}</div>
</div>

<div class="article-footer article-source-link">
  {% if item.original_url %}
    Originally published on Olive Network — <a href="{{ item.original_url }}" target="_blank" rel="noopener">view original ↗</a>
  {% else %}
    Item {{ item.id }}
  {% endif %}
</div>

<footer class="site-footer"><a href="../index.html">&larr; Back to archive</a></footer>
</body>
</html>
"""


SAMPLE_SIZE = None  # None = full archive, no sampling
MIN_NO_IMAGE_SAMPLES = 2
MIN_VIDEO_SAMPLES = 2


def evenly_spaced(lst, n):
    if n >= len(lst):
        return list(lst)
    if n <= 0:
        return []
    step = len(lst) / n
    return [lst[int(i * step)] for i in range(n)]


def pick_sample(all_items, target=SAMPLE_SIZE):
    if target is None:
        return sorted(all_items, key=lambda x: x["date_sort"], reverse=True)
    from collections import defaultdict
    by_cat = defaultdict(list)
    for it in all_items:
        by_cat[it["category"]].append(it)
    cats = list(by_cat.keys())
    total = len(all_items)

    alloc = {c: max(1, round(len(by_cat[c]) / total * target)) for c in cats}
    cats_by_size_desc = sorted(cats, key=lambda c: -len(by_cat[c]))
    diff = sum(alloc.values()) - target
    i = 0
    while diff > 0:
        c = cats_by_size_desc[i % len(cats_by_size_desc)]
        if alloc[c] > 1:
            alloc[c] -= 1
            diff -= 1
        i += 1
    while diff < 0:
        c = cats_by_size_desc[i % len(cats_by_size_desc)]
        alloc[c] += 1
        diff += 1
        i += 1

    sample = []
    sample_ids = set()
    for cat, n in alloc.items():
        chrono = sorted(by_cat[cat], key=lambda x: x["date_sort"])
        for it in evenly_spaced(chrono, n):
            if it["id"] not in sample_ids:
                sample.append(it)
                sample_ids.add(it["id"])

    have_no_img = sum(1 for it in sample if not it["thumb"])
    needed = max(0, MIN_NO_IMAGE_SAMPLES - have_no_img)
    for it in all_items:
        if needed <= 0:
            break
        if not it["thumb"] and it["id"] not in sample_ids:
            sample.append(it)
            sample_ids.add(it["id"])
            needed -= 1

    have_video = sum(1 for it in sample if it.get("has_video"))
    needed_video = max(0, MIN_VIDEO_SAMPLES - have_video)
    for it in all_items:
        if needed_video <= 0:
            break
        if it.get("has_video") and it["id"] not in sample_ids:
            sample.append(it)
            sample_ids.add(it["id"])
            needed_video -= 1

    sample.sort(key=lambda x: x["date_sort"], reverse=True)
    return sample


def main():
    env = Environment(loader=BaseLoader())
    index_tpl = env.from_string(INDEX_TEMPLATE)
    article_tpl = env.from_string(ARTICLE_TEMPLATE)

    rows = load_manifest()
    items = []
    dates = []
    missing = []

    for row in rows:
        item_id, slug, category = row["id"], row["slug"], row["category"] or "Uncategorized"
        path = find_article_file(item_id, slug)
        if not path:
            missing.append(item_id)
            continue
        front, body_md = parse_article(path)

        title = front.get("title") or slug.replace("-", " ").title()
        date_raw = front.get("date")
        images = front.get("images") or []
        has_video = bool(front.get("videos"))
        thumb = f"images/{item_id}/" + Path(images[0]).name if images else None
        banner = f"../images/{item_id}/" + Path(images[0]).name if images else None

        if date_raw:
            dates.append(str(date_raw))

        items.append({
            "id": item_id,
            "title": html.escape(title),
            "title_lower": html.escape(title).lower(),
            "category": html.escape(category),
            "category_slug": slugify(category),
            "date_display": format_date(date_raw),
            "date_sort": str(date_raw) if date_raw else "",
            "thumb": thumb,
            "banner": banner,
            "source": html.escape(front.get("source") or "ON Network"),
            "original_url": front.get("original_url"),
            "has_video": has_video,
            "body_html": render_body_html(body_md),
        })

    items.sort(key=lambda x: x["date_sort"], reverse=True)

    cat_counts = {}
    for it in items:
        key = (it["category_slug"], it["category"])
        cat_counts[key] = cat_counts.get(key, 0) + 1
    categories = sorted(
        [{"slug": s, "name": n, "count": c} for (s, n), c in cat_counts.items()],
        key=lambda x: -x["count"]
    )

    date_min = min(dates)[:4] if dates else "?"
    date_max = max(dates)[:4] if dates else "?"

    sample = pick_sample(items, SAMPLE_SIZE)

    sample_cat_counts = {}
    for it in sample:
        key = (it["category_slug"], it["category"])
        sample_cat_counts[key] = sample_cat_counts.get(key, 0) + 1
    sample_categories = sorted(
        [{"slug": s, "name": n, "count": c} for (s, n), c in sample_cat_counts.items()],
        key=lambda x: -x["count"]
    )

    # clear any previously generated browse pages before writing the sample
    if BROWSE_DIR.exists():
        for f in BROWSE_DIR.glob("*.html"):
            f.unlink()
    BROWSE_DIR.mkdir(exist_ok=True)

    (ROOT / "index.html").write_text(
        index_tpl.render(
            items=sample, categories=sample_categories, total=len(items),
            sample_total=len(sample),
            date_min=date_min, date_max=date_max, font_links=FONT_LINKS,
        ),
        encoding="utf-8",
    )

    for item in sample:
        (BROWSE_DIR / f"{item['id']}.html").write_text(
            article_tpl.render(item=item, font_links=FONT_LINKS),
            encoding="utf-8",
        )

    (ROOT / ".nojekyll").write_text("", encoding="utf-8")

    print(f"Archive: {len(items)} items across {len(categories)} categories, {date_min}-{date_max}.")
    print(f"Built index.html + {len(sample)} sample article pages (target {SAMPLE_SIZE}).")
    print("Sample categories:", ", ".join(f"{c['name']}({c['count']})" for c in sample_categories))
    if missing:
        print(f"WARNING: {len(missing)} manifest rows had no matching article file: {missing[:10]}{'...' if len(missing) > 10 else ''}")


if __name__ == "__main__":
    main()
