"""
One-off backfill: adds an empty `missing_images: []` field to the front
matter of already-scraped articles, for schema consistency with scrape.py's
new failed-image-download tracking (see the `missing_images` field it now
writes on every fresh scrape).

Pure local rewrite — no network calls, no re-fetching, no image downloads.
Resumable: skips any article file that already has a missing_images key.

Usage: python3 tools/add_missing_images_field.py
"""
import glob
import os
import sys

import yaml

ARTICLES_DIR = "articles"


def backfill_one(path: str) -> bool:
    """Returns True if the file was modified."""
    with open(path, encoding="utf-8") as f:
        content = f.read()

    fm_end = content.index("---", 3)
    front_matter = yaml.safe_load(content[3:fm_end])
    body = content[fm_end + 3:]

    if "missing_images" in front_matter:
        return False

    # Insert right after images, matching scrape.py's field order.
    new_fm = {}
    for key, value in front_matter.items():
        new_fm[key] = value
        if key == "images":
            new_fm["missing_images"] = []
    if "missing_images" not in new_fm:
        new_fm["missing_images"] = []

    with open(path, "w", encoding="utf-8") as f:
        f.write("---\n")
        f.write(yaml.safe_dump(new_fm, sort_keys=False, allow_unicode=True))
        f.write("---")
        f.write(body)

    return True


def main():
    paths = sorted(glob.glob(os.path.join(ARTICLES_DIR, "*.md")))
    print(f"[backfill] {len(paths)} article files found", file=sys.stderr)

    updated = skipped = 0
    for path in paths:
        if backfill_one(path):
            updated += 1
        else:
            skipped += 1

    print(f"[backfill] done. {updated} updated, {skipped} already had missing_images, {len(paths)} total",
          file=sys.stderr)


if __name__ == "__main__":
    main()
