"""Position-aware PDF reading: words -> lines (with x/y), and 'Exhibit/Table N.M: Title' sections."""
from __future__ import annotations

import re
from dataclasses import dataclass

import pdfplumber

LINE_TOL = 3.0  # points; words within this vertical distance share a line
# Fannie: "Exhibit 2.2: Title"   Freddie: "Table 2.2 - Title" (the dash is sometimes an odd glyph)
HEAD_RE = re.compile(r"^(Exhibit|Table)\s+(\d+\.\d+)\s*[:\-–—�]\s*(.*)$", re.I)


@dataclass
class Line:
    page: int  # 0-based
    top: float
    words: list

    @property
    def text(self) -> str:
        return " ".join(w["text"] for w in self.words)


def read_lines(path: str) -> list[Line]:
    lines: list[Line] = []
    with pdfplumber.open(path) as pdf:
        for pi, page in enumerate(pdf.pages):
            words = sorted(page.extract_words(keep_blank_chars=False), key=lambda w: (w["top"], w["x0"]))
            cur, cur_top = [], None
            for w in words:
                if cur_top is None or abs(w["top"] - cur_top) <= LINE_TOL:
                    cur.append(w)
                    cur_top = w["top"] if cur_top is None else cur_top
                else:
                    lines.append(Line(pi, cur_top, sorted(cur, key=lambda x: x["x0"])))
                    cur, cur_top = [w], w["top"]
            if cur:
                lines.append(Line(pi, cur_top, sorted(cur, key=lambda x: x["x0"])))
    return lines


def cover_text(path: str, pages: int = 8) -> str:
    out = []
    with pdfplumber.open(path) as pdf:
        for p in pdf.pages[:pages]:
            out.append((p.extract_text() or "").replace("\n", " "))
    return " ".join(out)


def norm_title(t: str) -> str:
    """Lower-case a heading and drop footnote markers ('Requirements8', 'Framework(8)')."""
    t = re.sub(r"\(\d+\)", "", t.lower())
    return re.sub(r"(?<=[a-z])\d+(?=\s|$)", "", t).strip()


def sections(lines: list[Line], title: str):
    """('Exhibit 2.2', clean title, lines) for every section whose heading contains `title`.

    Matched by title, never by exhibit number: Fannie Mae numbered its capital-metrics exhibit 2.1 through Q3 2023
    and 2.2 afterwards.
    """
    title = title.lower()
    out, cur = [], None
    for ln in lines:
        m = HEAD_RE.match(ln.text)
        if m:
            if cur:
                out.append(cur)
                cur = None
            if title in norm_title(m.group(3)):
                clean = re.sub(r"\(\d+\)|(?<=[A-Za-z])\d+$", "", m.group(3).replace("\ufffd", "'")).strip()
                cur = (f"{m.group(1).title()} {m.group(2)}", clean, [ln])
        elif cur:
            cur[2].append(ln)
    if cur:
        out.append(cur)
    return out
