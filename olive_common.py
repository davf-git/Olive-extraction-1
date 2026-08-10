"""Shared config/helpers for discover.py and scrape.py."""
import time
import requests

BASE_URL = "https://olivenetwork.org"
USER_AGENT = "OliveArchiveBot/0.1 (+one-off archive migration; contact: dave.forman@me.com)"
REQUEST_DELAY = 1.5  # seconds between requests, per CLAUDE.md

# (slug, id, display_name) for the 12 category index pages
CATEGORIES = [
    ("climate", 11, "Climate"),
    ("arts-culture", 483, "Arts & Culture"),
    ("charities", 412, "Charities"),
    ("dwelling", 477, "Dwelling"),
    ("economics", 1111, "Economics"),
    ("education", 181, "Education"),
    ("environment", 21, "Environment"),
    ("health", 30, "Health"),
    ("humanitarian", 461, "Humanitarian"),
    ("science-tech", 59, "Science & Tech"),
    ("sustainability", 113, "Sustainability"),
    ("un", 553, "UN"),
]


def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def polite_get(session: requests.Session, url: str, **kwargs) -> requests.Response:
    resp = session.get(url, timeout=30, **kwargs)
    time.sleep(REQUEST_DELAY)
    return resp
