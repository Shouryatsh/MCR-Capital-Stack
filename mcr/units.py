"""Unit detection and conversion. Units are always read from the file; never assumed."""
from __future__ import annotations

import re

TO_MILLIONS = {"thousands": 1e-3, "millions": 1.0, "billions": 1e3}
_PATTERNS = [
    re.compile(r"\(\s*(?:dollars?|us\s*dollars?|usd|\$)?\s*in\s+(millions|billions|thousands)\s*\)", re.I),
    re.compile(r"\$\s*(?:in\s+)?(millions|billions|thousands)\b", re.I),
    re.compile(r"\(\s*(millions|billions|thousands)\s*\)", re.I),
    re.compile(r"\b(?:dollars?|usd)\s+in\s+(millions|billions|thousands)\b", re.I),
    re.compile(r"\bin\s+(millions|billions|thousands)\b", re.I),
]


def detect_units(text: str) -> str | None:
    """'(Dollars in billions)' -> 'billions'; None when the text states no unit."""
    for pat in _PATTERNS:
        m = pat.search(text or "")
        if m:
            return m.group(1).lower()
    return None


def to_millions(value: float, units: str) -> float:
    try:
        return value * TO_MILLIONS[units]
    except KeyError:
        raise ValueError(f"unknown unit {units!r}") from None


def parse_number(tok: str) -> float:
    """Strip $ and commas; '(x)' is negative; an em dash is zero."""
    t = str(tok).strip()
    if t in ("—", "–", "-", ""):
        return 0.0
    neg = "(" in t or t.startswith("-")
    t = re.sub(r"[^\d.]", "", t)
    v = float(t)
    return -v if neg else v


_NUM_RE = re.compile(r"^\(?-?\$?\(?\d[\d,]*(\.\d+)?\)?$")


def is_number(tok: str) -> bool:
    t = str(tok).strip()
    return t in ("—", "–") or bool(_NUM_RE.match(t))
