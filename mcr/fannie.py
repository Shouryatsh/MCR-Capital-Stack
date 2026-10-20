"""Fannie Mae capital disclosures: parse the Period | Description | Format | Date table, download, ingest."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from . import config, store
from .ingest import Outcome, ingest_file

log = logging.getLogger("mcr.fannie")
INDEX_URL = "https://www.fanniemae.com/about-us/investor-relations/capital-disclosures"


def parse_index(html: str, base: str = INDEX_URL) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for table in soup.find_all("table"):
        if [th.get_text(strip=True) for th in table.find_all("th")][:4] != ["Period", "Description", "Format", "Date"]:
            continue
        for tr in table.find_all("tr"):
            a = tr.find("a", href=re.compile(r"\.pdf($|\?)", re.I))
            tds = tr.find_all("td")
            m = re.match(r"\s*Q([1-4])\s+(\d{4})", tds[0].get_text(strip=True)) if tds else None
            if a and m:
                out.append({"period": f"{m.group(2)}Q{m.group(1)}", "url": urljoin(base, a["href"])})
    return sorted(out, key=lambda d: d["period"], reverse=True)


def fetch_index() -> list[dict]:
    r = requests.get(INDEX_URL, headers={"User-Agent": config.USER_AGENT}, timeout=60)
    r.raise_for_status()
    items = parse_index(r.text)
    store.log_fetch(INDEX_URL, "ok", f"{len(items)} disclosure PDFs listed")
    if not items:
        raise RuntimeError("no Period/Description/Format/Date table with PDF links found on the Fannie Mae page")
    return items


def fetch(all_periods: bool = False, skip_existing: bool = True) -> list[Outcome]:
    try:
        items = fetch_index()
    except Exception as e:
        store.log_fetch(INDEX_URL, "error", str(e))
        return [Outcome("fanniemae.com", "error", "Fannie Mae", "", f"fetch failed: {e}")]
    have = {r["period"] for r in store.rows("SELECT period FROM observations WHERE provider='Fannie Mae'")}
    outcomes = []
    for item in (items if all_periods else items[:1]):
        if skip_existing and item["period"] in have:
            continue
        try:
            dest = config.RAW_DIR / "fannie" / f"{item['period']}.pdf"
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                r = requests.get(item["url"], headers={"User-Agent": config.USER_AGENT}, timeout=180)
                r.raise_for_status()
                if not r.content.startswith(b"%PDF"):
                    raise RuntimeError("response was not a PDF")
                dest.write_bytes(r.content)
                store.log_fetch(item["url"], "ok", f"downloaded {len(r.content):,} bytes")
            outcomes.append(ingest_file(dest, "Fannie Mae", item["period"], source_url=item["url"]))
        except Exception as e:
            store.log_fetch(item["url"], "error", str(e))
            outcomes.append(Outcome(Path(item["url"]).name, "error", "Fannie Mae", item["period"], f"download failed: {e}"))
    return outcomes
