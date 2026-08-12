"""
Targeted re-fetch for the articles that came out of Phase 1 with zero
images. Doesn't touch the ~830 already-good articles, doesn't reset
manifest.csv status, doesn't do a full re-scrape — just re-visits this
specific list of pages and retries their images with headers that look
like a normal browser tab rather than a bot cold-fetching an image URL
(which is what's triggering some of the 403s).

Usage: python3 tools/recover_images.py
"""
import csv
import glob
import os
import re
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from olive_common import get_session
from scrape import scrape_item, ARTICLES_DIR, MANIFEST_PATH

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def find_no_image_rows():
    with open(MANIFEST_PATH, newline="", encoding="utf-8") as f:
        manifest_by_id = {r["id"]: r for r in csv.DictReader(f)}

    targets = []
    for path in glob.glob(os.path.join(ARTICLES_DIR, "*.md")):
        raw = open(path, encoding="utf-8").read()
        m = re.match(r"^---\n(.*?)\n---\n", raw, re.DOTALL)
        if not m:
            continue
        front = yaml.safe_load(m.group(1)) or {}
        if front.get("images") == []:
            item_id = str(front.get("original_id"))
            if item_id in manifest_by_id:
                targets.append(manifest_by_id[item_id])
    return targets


def main():
    targets = find_no_image_rows()
    print(f"[recover] {len(targets)} zero-image articles to retry", file=sys.stderr)

    session = get_session()
    session.headers.update({"User-Agent": BROWSER_UA})

    recovered, still_stuck = 0, 0
    for i, row in enumerate(targets, start=1):
        print(f"[recover] ({i}/{len(targets)}) id={row['id']} {row['slug']}", file=sys.stderr)
        session.headers["Referer"] = row["url"]
        try:
            result = scrape_item(session, row)
            n = result["images"]
            if n > 0:
                recovered += 1
                print(f"    -> recovered {n} image(s)", file=sys.stderr)
            else:
                still_stuck += 1
                print("    -> still no images (likely genuinely gone)", file=sys.stderr)
        except Exception as e:
            still_stuck += 1
            print(f"    -> FAILED: {e}", file=sys.stderr)

    print(f"[recover] done. {recovered} recovered, {still_stuck} still stuck, "
          f"{len(targets)} total", file=sys.stderr)


if __name__ == "__main__":
    main()
