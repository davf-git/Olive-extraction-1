# Patch for scrape.py — capture video embeds

markdownify silently drops <iframe> tags, so YouTube/Vimeo embeds vanish
with zero trace. Add this BEFORE the `body_md = markdownify(...)` line in
`scrape_item()`:

```python
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
```

Inside `scrape_item()`, right before the `body_md = markdownify(...)` line:

```python
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
```

Then add `"videos": videos_rel,` to the `front_matter` dict, next to `"images"`.

That's it — the site generator doesn't need any changes, since the link
lands inline in the body text exactly where the embed was, and gets
rendered like any other link once the markdown is regenerated.

## Re-scraping

The raw HTML wasn't kept, only the converted Markdown, so fixing this
means re-fetching pages. Two options:
1. Reset just the 62 text-flagged rows in manifest.csv to "pending" and
   re-run scrape.py — fast, but likely still misses some silent drops.
2. Reset all 878 rows to "pending" and do a full re-scrape — slower, but
   the only way to be sure nothing else is being silently dropped the
   same way.

Given the whole point of Phase 1 was a trustworthy number, (2) is worth
the extra time.

## Known test case

id 25861 — https://olivenetwork.org/Issue/un-ocean-conference-lisbon-portugal/25861

Embed sits about halfway down the body, after the "MORE ABOUT THE
CONFERENCE" link and before the "Video message by Peter Thompson..."
heading. After the fix, `articles/25861-un-ocean-conference-lisbon-portugal.md`
should contain `videos: [https://www.youtube.com/watch?v=zXhB2r-A1qo]` in
the front matter, and the same link inline in the body at that position.

---

# Second issue — "no image" items may not actually be dead links

Phase 1 classified 45 items as having no images at all, attributed to
dead WordPress-era links (`olivenetwork.org/wp-content/uploads/...` —
a path preserved from Olive's site before it moved to Values Exchange).

Checked one directly: id 24630, "The Lampedusa Cross"
(https://olivenetwork.org/Issue/the-lampedusa-cross/24630). The original
page's images source from `olivenetwork.org/wp-content/uploads/2016/08/
lampedusa.jpg` — and that path is demonstrably still live today, because
the page's own Values Exchange banner is a resized crop of that same
file, served live right now. So "dead link" doesn't hold up as the
blanket explanation, at least not for this one.

In `scrape.py`, `download_image()` currently swallows the real failure
reason:

```python
    else:
        try:
            resp = polite_get(session, url)
            resp.raise_for_status()
        except Exception as e:
            print(f"    [image] failed to download {url}: {e}", file=sys.stderr)
            return None
        content = resp.content

    ext = sniff_ext(content)
    if ext is None:
        print(f"    [image] could not identify image type for {url[:80]}, skipping", file=sys.stderr)
        return None
```

Before re-running, make this log the actual status code and content-type
on failure, e.g.:

```python
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
```

That'll show whether these are genuine 404s, a redirect the scraper
isn't following, a block on the bot's user-agent, or something else —
worth knowing before concluding the images are actually gone. Given the
re-scrape is happening anyway for the video fix, re-attempt all 45
"no image" items (and ideally the ~145 partial-failure items too) with
this logging on, rather than trusting the original "dead link" call.
