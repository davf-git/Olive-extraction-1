"""
Step 1 of the Olive Network extraction pipeline.

Crawls all 12 category index pages (+ their /CaseList pagination) and writes
manifest.csv with one row per discovered item: id, slug, category, url, status.

Usage: python3 discover.py
"""
import csv
import re
import sys

from bs4 import BeautifulSoup

from olive_common import BASE_URL, CATEGORIES, get_session, polite_get

ITEM_LINK_RE = re.compile(r"^/Issue/([^/]+)/(\d+)/?$")
SITEMAP_ITEM_RE = re.compile(r"https?://olivenetwork\.org/Issue/([^/<]+)/(\d+)")
UNCATEGORIZED = "Uncategorized"


def parse_items(html: str) -> list[tuple[str, str]]:
    """Return list of (id, slug) tuples found in a chunk of HTML."""
    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen = set()
    for a in soup.select("div.item a[href]"):
        m = ITEM_LINK_RE.match(a["href"])
        if not m:
            continue
        slug, item_id = m.group(1), m.group(2)
        if item_id in seen:
            continue
        seen.add(item_id)
        items.append((item_id, slug))
    return items


def has_more_link(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    return soup.select_one(".list-more-wrapper") is not None


def discover_category(session, slug: str, cat_id: int, display_name: str) -> list[dict]:
    url = f"{BASE_URL}/{slug}/{cat_id}"
    print(f"[discover] {display_name}: fetching {url}", file=sys.stderr)
    resp = polite_get(session, url)
    resp.raise_for_status()

    all_items = parse_items(resp.text)
    more = has_more_link(resp.text)
    page = 0
    while more:
        params = {
            "page": page,
            "pagesize": 20,
            "type": 30,
            "display": 16,
            "userid": -1,
            "messageslarge": "True",
            "useroptions": 0,
            "groupinc": "False",
            "extraparams": f"themeid={cat_id}&latestissues=1&showdesc=False,False&",
        }
        cl_resp = polite_get(session, f"{BASE_URL}/CaseList", params=params)
        cl_resp.raise_for_status()
        batch = parse_items(cl_resp.text)
        print(f"[discover] {display_name}: page={page} -> {len(batch)} items", file=sys.stderr)
        if not batch:
            break
        all_items.extend(batch)
        page += 1

    rows = []
    seen_ids = set()
    for item_id, item_slug in all_items:
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        rows.append(
            {
                "id": item_id,
                "slug": item_slug,
                "category": display_name,
                "url": f"{BASE_URL}/Issue/{item_slug}/{item_id}",
                "status": "pending",
            }
        )
    return rows


def discover_sitemap_orphans(session, manifest: dict[str, dict]) -> list[dict]:
    """Items published on the site but not reachable from any of the 12
    category indexes (e.g. older content orphaned from current tagging).
    Found via sitemap.xml, which is a flat <urlset> (not a sitemap index)."""
    print("[discover] fetching sitemap.xml for orphaned items", file=sys.stderr)
    resp = polite_get(session, f"{BASE_URL}/sitemap.xml")
    resp.raise_for_status()

    seen = set()
    rows = []
    for slug, item_id in SITEMAP_ITEM_RE.findall(resp.text):
        if item_id in manifest or item_id in seen:
            continue
        seen.add(item_id)
        rows.append(
            {
                "id": item_id,
                "slug": slug,
                "category": UNCATEGORIZED,
                "url": f"{BASE_URL}/Issue/{slug}/{item_id}",
                "status": "pending",
            }
        )
    print(f"[discover] sitemap: {len(rows)} orphaned items found (not in any of the 12 categories)",
          file=sys.stderr)
    return rows


def main():
    session = get_session()
    manifest: dict[str, dict] = {}  # id -> row, dedup across categories

    for slug, cat_id, display_name in CATEGORIES:
        rows = discover_category(session, slug, cat_id, display_name)
        for row in rows:
            if row["id"] in manifest:
                print(
                    f"[discover] item {row['id']} already seen in "
                    f"{manifest[row['id']]['category']!r}, also in {display_name!r} - keeping first",
                    file=sys.stderr,
                )
                continue
            manifest[row["id"]] = row
        print(f"[discover] {display_name}: {len(rows)} items found (total unique so far: {len(manifest)})",
              file=sys.stderr)

    for row in discover_sitemap_orphans(session, manifest):
        manifest[row["id"]] = row

    with open("manifest.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "slug", "category", "url", "status"])
        writer.writeheader()
        for row in manifest.values():
            writer.writerow(row)

    print(f"[discover] done. {len(manifest)} unique items written to manifest.csv", file=sys.stderr)


if __name__ == "__main__":
    main()
