#!/usr/bin/env python3
"""
Best-effort recovery for articles that ended up with zero images.

PHASE1_FIXES.md found that olivenetwork.org's WAF blocks direct requests to
`/wp-content/uploads/...` with a flat 403 (confirmed via curl with browser
headers, a Cloudflare block, not a UA/referer check) — so those "dead link"
images aren't actually dead. The site's own `/img.get/c_{id}_{w}_{h}_...`
thumbnail proxy can still serve the item's designated image, since it fetches
server-side rather than hot-linking. That proxy always returns the same image
for a given item id regardless of the trailing index, so this recovers at most
one (the item's primary/og:image) per article — not necessarily every image
originally embedded in the body.

For each article whose front matter has an empty `images` list, this script:
  1. Re-fetches the live page.
  2. Skips it if the body never had any <img> tags in the first place (that's
     not a recovery candidate — there was nothing to lose).
  3. Otherwise, downloads the page's og:image (served via the img.get proxy)
     and adds it to the article's images list + a line at the top of the body.

Resumable: articles that already have images are skipped.

Usage: python3 tools/recover_images.py
"""
import glob
import os
import re
import sys

import yaml
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from olive_common import get_session, polite_get
from scrape import sniff_ext, ARTICLES_DIR, IMAGES_DIR


def find_zero_image_articles() -> list[str]:
    paths = []
    for fp in sorted(glob.glob(os.path.join(ARTICLES_DIR, "*.md"))):
        text = open(fp, encoding="utf-8").read()
        fm = yaml.safe_load(text.split("---\n", 2)[1])
        if not (fm.get("images") or []):
            paths.append(fp)
    return paths


def recover_one(session, article_path: str) -> str:
    text = open(article_path, encoding="utf-8").read()
    _, fm_text, body = text.split("---\n", 2)
    fm = yaml.safe_load(fm_text)
    item_id = str(fm["original_id"])
    url = fm["original_url"]

    resp = polite_get(session, url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    desc = soup.select_one("div.detail div.pnl div.desc")
    if not desc or not desc.find_all("img"):
        return "skipped: no <img> tags in body, nothing was lost"

    og_image = soup.select_one("meta[property='og:image']")
    if not og_image or not og_image.get("content"):
        return "failed: no og:image to fall back to"

    proxy_url = og_image["content"].replace("http://", "https://", 1)
    try:
        img_resp = polite_get(session, proxy_url)
        img_resp.raise_for_status()
    except Exception as e:
        return f"failed: {e}"

    ext = sniff_ext(img_resp.content)
    if ext is None:
        return f"failed: unrecognised image type (content-type: {img_resp.headers.get('content-type')})"

    img_dir = os.path.join(IMAGES_DIR, item_id)
    os.makedirs(img_dir, exist_ok=True)
    local_path = os.path.join(img_dir, f"01.{ext}")
    with open(local_path, "wb") as f:
        f.write(img_resp.content)

    fm["images"] = [local_path]
    new_body = f"![]({local_path})\n\n" + body

    with open(article_path, "w", encoding="utf-8") as f:
        f.write("---\n")
        f.write(yaml.safe_dump(fm, sort_keys=False, allow_unicode=True))
        f.write("---\n\n")
        f.write(new_body.lstrip("\n"))

    return f"recovered: {local_path}"


def main():
    session = get_session()
    articles = find_zero_image_articles()
    print(f"[recover] {len(articles)} articles with zero images", file=sys.stderr)

    recovered = skipped = failed = 0
    for i, article_path in enumerate(articles):
        print(f"[recover] ({i + 1}/{len(articles)}) {article_path}", file=sys.stderr)
        result = recover_one(session, article_path)
        print(f"    -> {result}", file=sys.stderr)
        if result.startswith("recovered"):
            recovered += 1
        elif result.startswith("skipped"):
            skipped += 1
        else:
            failed += 1

    print(
        f"[recover] done. {recovered} recovered, {skipped} skipped "
        f"(no images to begin with), {failed} still failed, "
        f"{len(articles)} total",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
