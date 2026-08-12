"""
Step 2 of the Olive Network extraction pipeline.

Reads manifest.csv, visits each pending item, extracts title/date/byline/body
(as Markdown) + body images, and writes articles/{id}-{slug}.md with YAML
front-matter. Downloaded images go to images/{id}/. Resumable: re-run to pick
up any row still marked "pending" (or retry "failed" rows by resetting their
status first).

Usage: python3 scrape.py
"""
import base64
import csv
import os
import re
import sys
from datetime import datetime
from urllib.parse import urljoin

import yaml
from bs4 import BeautifulSoup
from markdownify import markdownify

from olive_common import BASE_URL, get_session, polite_get

MANIFEST_PATH = "manifest.csv"
ARTICLES_DIR = "articles"
IMAGES_DIR = "images"

IMAGE_MAGIC = [
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"RIFF", "webp"),  # WEBP: RIFF....WEBP, checked further below
    (b"BM", "bmp"),
]


def sniff_ext(data: bytes) -> str | None:
    for magic, ext in IMAGE_MAGIC:
        if data.startswith(magic):
            if ext == "webp":
                if data[8:12] != b"WEBP":
                    continue
            return ext
    return None


def load_manifest() -> list[dict]:
    with open(MANIFEST_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_manifest(rows: list[dict]) -> None:
    tmp_path = MANIFEST_PATH + ".tmp"
    with open(tmp_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "slug", "category", "url", "status"])
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp_path, MANIFEST_PATH)


def parse_date(soup: BeautifulSoup):
    span = soup.select_one("#issuemenu .hosttime")
    raw = span.get("data-utc") if span else None
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%B %d, %Y %I:%M %p").date()
    except ValueError:
        return None


def canonical_video_url(src: str) -> str:
    """Best-effort: turn an embed src into the normal watch/share URL."""
    src = urljoin(BASE_URL, src)  # handles protocol-relative //... too
    m = re.search(r"youtube(?:-nocookie)?\.com/embed/([\w-]+)", src)
    if m:
        return f"https://www.youtube.com/watch?v={m.group(1)}"
    m = re.search(r"player\.vimeo\.com/video/(\d+)", src)
    if m:
        return f"https://vimeo.com/{m.group(1)}"
    return src


def parse_source(soup: BeautifulSoup, desc) -> tuple[str, str, str | None]:
    """Returns (author, source, source_url). author = the ON Network account;
    source = original outlet named in an 'ON SOURCE:' line if present, else
    author; source_url = that outlet's own URL, if the line links to one."""
    author_link = soup.select_one("#issueauthor a.i-blk")
    author = author_link.get_text(strip=True) if author_link else "ON Network"

    source = author
    source_url = None
    if desc:
        for p in desc.find_all("p"):
            p_text = p.get_text(" ", strip=True)
            if p_text.upper().startswith("ON SOURCE:"):
                candidate = p_text[len("ON SOURCE:"):].strip()
                if candidate:
                    source = candidate
                link = p.find("a", href=True)
                if link:
                    source_url = link["href"].strip()
                break
    return author, source, source_url


def download_image(session, url: str, dest_dir: str, index: int) -> str | None:
    if url.startswith("data:"):
        try:
            header, b64_payload = url.split(",", 1)
            content = base64.b64decode(b64_payload)
        except Exception as e:
            print(f"    [image] failed to decode data URI: {e}", file=sys.stderr)
            return None
    else:
        try:
            resp = polite_get(session, url)
            resp.raise_for_status()
        except Exception as e:
            print(f"    [image] failed to download {url}: {e}", file=sys.stderr)
            return None
        if resp.status_code != 200:
            print(f"    [image] {url} -> HTTP {resp.status_code}", file=sys.stderr)
            return None
        content = resp.content

    ext = sniff_ext(content)
    if ext is None:
        print(f"    [image] {url} -> {len(content)} bytes, unrecognised type "
              f"(content-type: {resp.headers.get('content-type')}), skipping", file=sys.stderr)
        return None
    os.makedirs(dest_dir, exist_ok=True)
    filename = f"{index:02d}.{ext}"
    path = os.path.join(dest_dir, filename)
    with open(path, "wb") as f:
        f.write(content)
    return path


def scrape_item(session, row: dict) -> dict:
    item_id = row["id"]
    slug = row["slug"]
    url = row["url"]

    resp = polite_get(session, url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    title_tag = soup.select_one(".headertitle h1")
    if not title_tag:
        og_title = soup.select_one("meta[property='og:title']")
        title = og_title["content"].strip() if og_title else slug
    else:
        title = title_tag.get_text(strip=True)

    date = parse_date(soup)

    desc = soup.select_one("div.detail div.pnl div.desc")
    if desc is None:
        raise ValueError("could not find article body (div.desc)")

    author, source, source_url = parse_source(soup, desc)

    # Download body images, in document order, and rewrite src to local paths.
    images_rel = []
    img_dir = os.path.join(IMAGES_DIR, item_id)
    for i, img in enumerate(desc.find_all("img"), start=1):
        src = img.get("src")
        if not src:
            img.decompose()
            continue
        abs_url = urljoin(BASE_URL, src)
        local_path = download_image(session, abs_url, img_dir, i)
        if local_path:
            img["src"] = local_path
            images_rel.append(local_path)
        else:
            img.decompose()

    # Capture video embeds — markdownify drops <iframe> tags silently,
    # so pull the src out and swap in a link that survives conversion.
    videos_rel = []
    for iframe in desc.find_all("iframe"):
        src = iframe.get("src")
        if not src:
            iframe.decompose()
            continue
        video_url = canonical_video_url(src)
        videos_rel.append(video_url)
        link = soup.new_tag("a", href=video_url)
        link.string = f"[Video: {video_url}]"
        iframe.replace_with(link)

    body_md = markdownify(str(desc), heading_style="ATX").strip()

    front_matter = {
        "title": title,
        "date": date,
        "category": row["category"],
        "source": source,
        "source_url": source_url,
        "original_id": int(item_id),
        "original_slug": slug,
        "original_url": url,
        "images": images_rel,
        "videos": videos_rel,
    }

    os.makedirs(ARTICLES_DIR, exist_ok=True)
    article_path = os.path.join(ARTICLES_DIR, f"{item_id}-{slug}.md")
    with open(article_path, "w", encoding="utf-8") as f:
        f.write("---\n")
        f.write(yaml.safe_dump(front_matter, sort_keys=False, allow_unicode=True))
        f.write("---\n\n")
        f.write(body_md)
        f.write("\n")

    return {"article_path": article_path, "images": len(images_rel)}


def main():
    rows = load_manifest()
    session = get_session()

    pending = [r for r in rows if r["status"] == "pending"]
    print(f"[scrape] {len(pending)} pending items out of {len(rows)} total", file=sys.stderr)

    for i, row in enumerate(rows):
        if row["status"] != "pending":
            continue
        print(f"[scrape] ({i + 1}/{len(rows)}) id={row['id']} {row['slug']}", file=sys.stderr)
        try:
            result = scrape_item(session, row)
            row["status"] = "done"
            print(f"    -> {result['article_path']} ({result['images']} images)", file=sys.stderr)
        except Exception as e:
            row["status"] = f"failed: {e}"
            print(f"    -> FAILED: {e}", file=sys.stderr)
        save_manifest(rows)

    done = sum(1 for r in rows if r["status"] == "done")
    failed = sum(1 for r in rows if r["status"].startswith("failed"))
    print(f"[scrape] done. {done} succeeded, {failed} failed, {len(rows)} total", file=sys.stderr)


if __name__ == "__main__":
    main()
