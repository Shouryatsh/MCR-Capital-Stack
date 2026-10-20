"""Shared types: canonical fields, provenance records, and user-facing errors."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

CET1 = "CET1_amount"
ATA = "Adjusted_total_assets"
CANONICAL_FIELDS = (CET1, ATA)
FIELD_LABELS = {CET1: "CET1 amount", ATA: "Adjusted total assets"}


class MCRError(Exception):
    """Base class for errors that are shown to the user verbatim."""


class ParseError(MCRError):
    def __init__(self, source: str, message: str, period: str = ""):
        self.source, self.period = source, period
        super().__init__(f"[{source}{' · ' + period if period else ''}] {message}")


class FieldNotFoundError(ParseError):
    def __init__(self, source: str, field_name: str, detail: str = "", period: str = ""):
        self.field_name = field_name
        super().__init__(source, f"field not found: {field_name!r}" + (f" ({detail})" if detail else ""), period)


class AmbiguousMappingError(ParseError):
    pass


class UnitsError(ParseError):
    pass


class ColumnShapeError(ParseError):
    pass


class UploadRejected(MCRError):
    pass


@dataclass
class Observation:
    """One extracted number plus everything needed to trace it back to the source."""

    provider: str
    period: str  # e.g. 2023Q4
    field: str  # canonical field
    source_file: str
    table_name: str  # sheet, or "Exhibit 11.1 · Tier 1 Leverage Ratio, Part 1"
    row_identifier: str  # e.g. "line 7" / "row 42" / the printed label
    field_label: str  # the label as it appears in the file
    raw_value: str  # exactly as printed, e.g. "(73,965)"
    parsed_value: float  # in the file's own units
    units_detected: str  # millions | billions | thousands
    units_source: str = "detected"  # detected | mapping (hint used because the file stated none)
    value_mm: float = 0.0  # parsed_value converted to $ millions
    location: str = ""  # page number / cell reference
    column_name: str = ""
    source_url: str = ""
    notes: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)

    def provenance_text(self) -> str:
        loc = f", {self.location}" if self.location else ""
        col = f" [{self.column_name}]" if self.column_name else ""
        return f"{self.source_file}{loc} · {self.table_name} · {self.field_label}{col}"


@dataclass
class Check:
    name: str
    status: str  # pass | fail
    detail: str = ""


@dataclass
class ParseResult:
    provider: str
    period: str
    observations: dict  # canonical field -> Observation
    checks: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.status == "pass" for c in self.checks)
