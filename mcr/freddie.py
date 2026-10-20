"""Freddie Mac ERCF public disclosure fetcher: list PDFs on the index page, pick the newest, download, parse, log."""
from __future__ import annotations

import logging
import re
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from . import config, store
from .ingest import Outcome, ingest_file

log = logging.getLogger("mcr.freddie")
_FILE_RE = re.compile(r"(?<!\d)([1-4])Q(\d{2})_ercf_public_disclosure\.pdf$", re.I)  # 2Q26_ercf_public_disclosure.pdf


def period_from_url(url: str) -> str | None:
    m = _FILE_RE.search(url)
    return f"20{m.group(2)}Q{m.group(1)}" if m else None


def list_disclosures(html: str, base: str = config.FREDDIE_URL) -> list[dict]:
    """[{period, url}] newest first, from the index page's PDF links."""
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        url = urljoin(base, a["href"])
        p = period_from_url(url)
        if p and url not in seen:
            seen.add(url)
            out.append({"period": p, "url": url})
    return sorted(out, key=lambda d: d["period"], reverse=True)


def fetch_index() -> list[dict]:
    r = requests.get(config.FREDDIE_URL, headers={"User-Agent": config.USER_AGENT}, timeout=60)
    r.raise_for_status()
    items = list_disclosures(r.text)
    store.log_fetch(config.FREDDIE_URL, "ok", f"{len(items)} disclosure PDFs listed")
    log.info("Freddie Mac index: %d PDFs, newest %s", len(items), items[0]["period"] if items else "none")
    if not items:
        raise RuntimeError("no ERCF disclosure PDF links found on the Freddie Mac page (layout may have changed)")
    return items


def download(item: dict) -> Path:
    dest = config.RAW_DIR / "freddie" / Path(item["url"]).name
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(item["url"], headers={"User-Agent": config.USER_AGENT}, timeout=180)
    r.raise_for_status()
    if not r.content.startswith(b"%PDF"):
        raise RuntimeError(f"{item['url']} did not return a PDF")
    dest.write_bytes(r.content)
    lm = r.headers.get("Last-Modified", "")
    store.log_fetch(item["url"], "ok", f"downloaded {len(r.content):,} bytes; Last-Modified: {lm or 'n/a'}")
    log.info("downloaded %s (%s bytes)", item["url"], f"{len(r.content):,}")
    return dest


def fetch_latest(all_periods: bool = False) -> list[Outcome]:
    """Download + parse the newest Freddie Mac disclosure (or every one with all_periods=True)."""
    try:
        items = fetch_index()
    except Exception as e:
        store.log_fetch(config.FREDDIE_URL, "error", str(e))
        log.error("Freddie Mac fetch failed: %s", e)
        return [Outcome("freddiemac.com", "error", "Freddie Mac", "", f"fetch failed: {e}")]
    outcomes = []
    for item in (items if all_periods else items[:1]):
        try:
            path = download(item)
            outcomes.append(ingest_file(path, "Freddie Mac", item["period"], source_url=item["url"]))
        except Exception as e:
            store.log_fetch(item["url"], "error", str(e))
            outcomes.append(Outcome(Path(item["url"]).name, "error", "Freddie Mac", item["period"], f"download failed: {e}"))
    return outcomes
