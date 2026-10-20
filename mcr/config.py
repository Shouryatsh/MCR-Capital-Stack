"""Paths, settings and peer registry (JSON files under config/, created with defaults on first use)."""
from __future__ import annotations

import json
import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
RAW_DIR = ROOT / "raw"
LOG_DIR = ROOT / "logs"
DB_PATH = DATA_DIR / "mcr.db"

APP_NAME = "MCR Dashboard"
FREDDIE_URL = "https://www.freddiemac.com/investors/ercf-public-disclosure"
USER_AGENT = "Mozilla/5.0 (MCR-Dashboard disclosure fetcher)"
MAX_UPLOAD_MB = 50
MAX_ZIP_TOTAL_MB = 200
MAX_ZIP_MEMBERS = 60

DEFAULT_SETTINGS = {
    "primary_provider": "Fannie Mae",
    "ratio_decimals": 2,
    # ProviderName_YYYYMMDD_disclosure.xlsx
    "filename_pattern": r"^(?P<provider>.+?)_(?P<date>\d{8})_disclosure\.(?:xlsx|csv)$",
    "allowed_extensions": [".pdf", ".xlsx", ".csv", ".zip"],
}
# Ten benchmark slots. The first two are fixed; the other eight are for the user to name in Settings.
DEFAULT_PEERS = [{"slot": 1, "name": "Fannie Mae", "provider": "Fannie Mae"},
                 {"slot": 2, "name": "Freddie Mac", "provider": "Freddie Mac"}] + \
                [{"slot": i, "name": "", "provider": ""} for i in range(3, 11)]


def _load(path: Path, default):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(default, indent=2), encoding="utf8")
        return json.loads(json.dumps(default))
    return json.loads(path.read_text(encoding="utf8"))


def load_settings() -> dict:
    return {**DEFAULT_SETTINGS, **_load(CONFIG_DIR / "settings.json", DEFAULT_SETTINGS)}


def save_settings(s: dict) -> None:
    re.compile(s["filename_pattern"])  # reject an invalid pattern before saving
    (CONFIG_DIR / "settings.json").write_text(json.dumps(s, indent=2), encoding="utf8")


def load_peers() -> list[dict]:
    return _load(CONFIG_DIR / "peers.json", DEFAULT_PEERS)


def save_peers(peers: list[dict]) -> None:
    (CONFIG_DIR / "peers.json").write_text(json.dumps(peers, indent=2), encoding="utf8")


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "unknown"


def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(exist_ok=True)
    log = logging.getLogger("mcr")
    if not log.handlers:
        log.setLevel(logging.INFO)
        h = RotatingFileHandler(LOG_DIR / "mcr.log", maxBytes=2_000_000, backupCount=3, encoding="utf8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(h)
        s = logging.StreamHandler()
        s.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        log.addHandler(s)
    return log
