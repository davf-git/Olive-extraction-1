"""
Diagnostic only — writes no article files, changes no manifest state.

Question: the back end reports 1176 non-deleted stories; we extracted 878
public ones. Where are the other ~298? This probes item IDs directly to
find out whether unlisted stories are (a) published but orphaned, (b)
unpublished/draft, or (c) simply not Olive records at all.

Design notes:
  * CONTROLS come first and matter more than the samples. We probe known-good
    IDs both with their correct slug and with a junk slug. If the junk slug
    still resolves, the site keys on ID alone and every other result in this
    run is trustworthy. If it doesn't, ID-only probing is meaningless and the
    run should be discarded.
  * IN-RANGE gaps test for orphaned/unpublished items among Olive's own IDs.
  * BELOW-RANGE tests the pre-2018 hypothesis: our archive starts abruptly in
    Dec 2018, but Olive ran from 2011, so earlier records may sit at lower IDs.
  * ABOVE-RANGE tests for recent unpublished drafts.
  * Values Exchange is a multi-tenant platform, so unused IDs may belong to
    other client instances entirely. Watch for pages that resolve but are
    clearly not Olive content.

Usage: python3 tools/probe_ids.py
Output: tools/probe_results.csv + a summary to stderr.
"""
import csv
import os
import random
import sys

from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from olive_common import BASE_URL, get_session, polite_get

MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "manifest.csv")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "probe_results.csv")

JUNK_SLUG = "probe"
SAMPLE_IN_RANGE = 30
SAMPLE_BELOW = 15
SAMPLE_ABOVE = 10
random.seed(1)  # reproducible sample


def load_known():
    with open(MANIFEST, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {int(r["id"]): r for r in rows}


def classify(resp, soup):
    """Best-effort bucket for what came back."""
    if resp.status_code == 404:
        return "404-not-found"
    if resp.status_code in (401, 403):
        return f"{resp.status_code}-forbidden"
    if resp.status_code != 200:
        return f"http-{resp.status_code}"

    text = resp.text.lower()
    title_tag = soup.select_one(".headertitle h1")
    body = soup.select_one("div.detail div.pnl div.desc")

    if title_tag and body:
        return "ARTICLE"
    if title_tag and not body:
        return "title-but-no-body"
    if "sign in" in text or "log in" in text or "login" in text:
        return "login-wall"
    return "200-but-no-article"


def probe(session, item_id, slug, note, writer, counts):
    url = f"{BASE_URL}/Issue/{slug}/{item_id}"
    try:
        resp = polite_get(session, url)
    except Exception as e:
        print(f"  {item_id} [{note}] ERROR {e}", file=sys.stderr)
        writer.writerow({"id": item_id, "slug_used": slug, "note": note,
                         "status": "EXCEPTION", "verdict": "exception",
                         "final_url": "", "title": str(e)[:120], "body_chars": 0})
        counts["exception"] = counts.get("exception", 0) + 1
        return

    soup = BeautifulSoup(resp.text, "html.parser")
    verdict = classify(resp, soup)
    title_tag = soup.select_one(".headertitle h1")
    title = title_tag.get_text(strip=True) if title_tag else ""
    body = soup.select_one("div.detail div.pnl div.desc")
    body_chars = len(body.get_text(strip=True)) if body else 0
    redirected = resp.url.rstrip("/") != url.rstrip("/")

    writer.writerow({
        "id": item_id,
        "slug_used": slug,
        "note": note,
        "status": resp.status_code,
        "verdict": verdict,
        "final_url": resp.url if redirected else "",
        "title": title[:120],
        "body_chars": body_chars,
    })
    counts[verdict] = counts.get(verdict, 0) + 1
    flag = " <-- REDIRECTED" if redirected else ""
    print(f"  {item_id} [{note}] {resp.status_code} {verdict} "
          f"{('| ' + title[:60]) if title else ''}{flag}", file=sys.stderr)


def main():
    known = load_known()
    ids = sorted(known)
    lo, hi = ids[0], ids[-1]
    known_set = set(ids)

    gaps = [i for i in range(lo, hi + 1) if i not in known_set]
    in_range = sorted(random.sample(gaps, min(SAMPLE_IN_RANGE, len(gaps))))
    below = sorted(random.sample(range(lo - 1200, lo), SAMPLE_BELOW))
    above = sorted(random.sample(range(hi + 1, hi + 400), SAMPLE_ABOVE))

    controls = ids[:2] + ids[len(ids) // 2:len(ids) // 2 + 1]

    session = get_session()
    counts = {}

    print(f"[probe] known range {lo}-{hi}, {len(gaps)} unused ids inside it", file=sys.stderr)
    print(f"[probe] {len(controls)*2 + len(in_range) + len(below) + len(above)} requests "
          f"at 1.5s each\n", file=sys.stderr)

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "id", "slug_used", "note", "status", "verdict", "final_url", "title", "body_chars"])
        writer.writeheader()

        print("[probe] CONTROLS - real ids, correct slug (expect ARTICLE):", file=sys.stderr)
        for cid in controls:
            probe(session, cid, known[cid]["slug"], "control-real-slug", writer, counts)

        print("\n[probe] CONTROLS - real ids, junk slug "
              "(does the site resolve by id alone?):", file=sys.stderr)
        for cid in controls:
            probe(session, cid, JUNK_SLUG, "control-junk-slug", writer, counts)

        print("\n[probe] IN-RANGE unused ids:", file=sys.stderr)
        for i in in_range:
            probe(session, i, JUNK_SLUG, "gap-in-range", writer, counts)

        print(f"\n[probe] BELOW-RANGE ids (< {lo}, pre-2018 hypothesis):", file=sys.stderr)
        for i in below:
            probe(session, i, JUNK_SLUG, "below-range", writer, counts)

        print(f"\n[probe] ABOVE-RANGE ids (> {hi}):", file=sys.stderr)
        for i in above:
            probe(session, i, JUNK_SLUG, "above-range", writer, counts)

    print("\n[probe] ==== SUMMARY ====", file=sys.stderr)
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {v:4d}  {k}", file=sys.stderr)
    print(f"\n[probe] full results: {OUT}", file=sys.stderr)
    print("[probe] READ THIS FIRST: if the junk-slug controls did not return "
          "ARTICLE, the site needs the correct slug and every id-only result "
          "below is meaningless — say so rather than drawing conclusions.",
          file=sys.stderr)


if __name__ == "__main__":
    main()
