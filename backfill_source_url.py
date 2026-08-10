"""
One-off backfill: adds a `source_url` field (the original outlet's own URL,
parsed from the 'ON SOURCE: <a href=...>' line) to the front-matter of
already-scraped articles, without re-downloading any images.

Re-fetches each item's page (needed since we didn't capture this the first
time) but reuses the images/body already on disk. Resumable: skips any
article file that already has a source_url key set.

Usage: python3 backfill_source_url.py
"""
import glob
import os
import sys

import yaml
from bs4 import BeautifulSoup

from olive_common import get_session, polite_get
from scrape import parse_source

ARTICLES_DIR = "articles"


def backfill_one(session, path: str) -> bool:
    """Returns True if the file was modified."""
    with open(path, encoding="utf-8") as f:
        content = f.read()

    fm_end = content.index("---", 3)
    front_matter = yaml.safe_load(content[3:fm_end])
    body = content[fm_end + 3:]

    if "source_url" in front_matter:
        return False

    url = front_matter["original_url"]
    resp = polite_get(session, url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    desc = soup.select_one("div.detail div.pnl div.desc")

    _, source, source_url = parse_source(soup, desc)

    # Rebuild front matter preserving field order, inserting source_url
    # right after source. Keep the existing `source` value as-is (already
    # verified during the original scrape) unless it was missing.
    new_fm = {}
    for key, value in front_matter.items():
        new_fm[key] = value
        if key == "source":
            new_fm["source_url"] = source_url
    if "source_url" not in new_fm:
        new_fm["source"] = source
        new_fm["source_url"] = source_url

    with open(path, "w", encoding="utf-8") as f:
        f.write("---\n")
        f.write(yaml.safe_dump(new_fm, sort_keys=False, allow_unicode=True))
        f.write("---")
        f.write(body)

    return True


def main():
    session = get_session()
    paths = sorted(glob.glob(os.path.join(ARTICLES_DIR, "*.md")))
    print(f"[backfill] {len(paths)} article files found", file=sys.stderr)

    updated = 0
    skipped = 0
    for i, path in enumerate(paths, start=1):
        try:
            changed = backfill_one(session, path)
        except Exception as e:
            print(f"[backfill] ({i}/{len(paths)}) FAILED {path}: {e}", file=sys.stderr)
            continue
        if changed:
            updated += 1
            print(f"[backfill] ({i}/{len(paths)}) updated {path}", file=sys.stderr)
        else:
            skipped += 1

    print(f"[backfill] done. {updated} updated, {skipped} already had source_url, {len(paths)} total",
          file=sys.stderr)


if __name__ == "__main__":
    main()
