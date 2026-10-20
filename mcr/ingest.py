"""Validate, route, parse and store uploaded / fetched files (pdf, xlsx, csv, zip packages)."""
from __future__ import annotations

import logging
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

from . import capital, config, store
from .mappings import find_provider, load_mappings
from .models import MCRError, ParseError, ParseResult, UploadRejected
from .pdf_extract import detect_pdf_provider, infer_period, parse_pdf
from .tabular import parse_tabular

log = logging.getLogger("mcr.ingest")


@dataclass
class Outcome:
    file: str
    status: str  # ok | checks_failed | error
    provider: str = ""
    period: str = ""
    message: str = ""
    result: ParseResult | None = None


# ------------------------------------------------------------------ validation
def validate_file(path: Path, settings: dict | None = None) -> None:
    settings = settings or config.load_settings()
    ext = path.suffix.lower()
    if ext not in settings["allowed_extensions"]:
        raise UploadRejected(f"{path.name}: file type {ext or '(none)'} is not allowed (allowed: {', '.join(settings['allowed_extensions'])})")
    size_mb = path.stat().st_size / 1e6
    if size_mb > config.MAX_UPLOAD_MB:
        raise UploadRejected(f"{path.name}: {size_mb:.1f} MB exceeds the {config.MAX_UPLOAD_MB} MB limit")
    head = path.read_bytes()[:8]
    if ext == ".pdf" and not head.startswith(b"%PDF"):
        raise UploadRejected(f"{path.name}: not a real PDF (bad file signature)")
    if ext in (".xlsx", ".zip") and not head.startswith(b"PK"):
        raise UploadRejected(f"{path.name}: not a real {ext[1:]} file (bad file signature)")
    if ext == ".csv" and b"\x00" in path.read_bytes()[:4096]:
        raise UploadRejected(f"{path.name}: does not look like a text CSV")


def safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._ -]", "_", Path(name).name)[:120]


def unpack_zip(path: Path, dest: Path, settings: dict | None = None) -> list[Path]:
    """Extract only allowed members; guards against zip-slip, zip bombs and huge member counts."""
    settings = settings or config.load_settings()
    dest.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    with zipfile.ZipFile(path) as z:
        infos = [i for i in z.infolist() if not i.is_dir()]
        if len(infos) > config.MAX_ZIP_MEMBERS:
            raise UploadRejected(f"{path.name}: {len(infos)} files exceeds the limit of {config.MAX_ZIP_MEMBERS}")
        if sum(i.file_size for i in infos) > config.MAX_ZIP_TOTAL_MB * 1e6:
            raise UploadRejected(f"{path.name}: unpacked size exceeds {config.MAX_ZIP_TOTAL_MB} MB")
        for i in infos:
            name = safe_name(i.filename)
            if Path(i.filename).suffix.lower() not in (".pdf", ".xlsx", ".csv") or name.startswith("."):
                log.info("zip %s: skipping member %s", path.name, i.filename)
                continue
            target = dest / name  # flattened, so '../' tricks cannot escape dest
            with z.open(i) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            out.append(target)
    if not out:
        raise UploadRejected(f"{path.name}: the zip contains no .pdf, .xlsx or .csv files")
    return out


# ------------------------------------------------------------------ file name -> provider / period
def parse_filename(name: str, settings: dict | None = None):
    """(provider token, period) from ProviderName_YYYYMMDD_disclosure.xlsx (pattern is configurable), else None."""
    settings = settings or config.load_settings()
    m = re.match(settings["filename_pattern"], name, re.I)
    if not m:
        return None
    d = m.group("date")
    return m.group("provider").replace("_", " ").strip(), f"{d[:4]}Q{(int(d[4:6]) - 1) // 3 + 1}"


def sort_key(path: Path):
    """Newest-first ordering: period from the file name pattern, else file modification time."""
    pf = parse_filename(path.name)
    return (pf[1] if pf else "", path.stat().st_mtime)


def newest_per_provider(paths: list[Path]) -> list[Path]:
    best: dict = {}
    for p in paths:
        pf = parse_filename(p.name)
        key = (pf[0].lower() if pf else re.sub(r"[\d_\- ]+", "", p.stem.lower()))
        if key not in best or sort_key(p) > sort_key(best[key]):
            best[key] = p
    return list(best.values())


# ------------------------------------------------------------------ main entry
def _store_capital(path: Path, provider: str, period: str, source_url: str, db) -> tuple[bool, str]:
    """Minimum capital ratio, total and credit RWA. A failure here is reported but never hides the CET1 / ATA result."""
    try:
        res = capital.ingest(path, provider, period, source_url, db)
    except Exception as e:
        log.exception("capital extraction crashed for %s", path.name)
        return False, f"capital metrics: {e}"
    return res.ok, "; ".join(f"{c.name}: {c.detail}" for c in res.checks if c.status != "pass")


def ingest_file(path: Path, provider: str | None = None, period: str | None = None, source_url: str = "",
                db=None) -> Outcome:
    """Parse one pdf/xlsx/csv and store it. Never raises for bad input; returns an Outcome with a clear message."""
    path = Path(path)
    settings = config.load_settings()
    try:
        validate_file(path, settings)
        mappings = load_mappings()
        ext = path.suffix.lower()
        if ext == ".pdf":
            provider = provider or detect_pdf_provider(str(path), mappings)
            cfg = mappings.get(provider)
            if not cfg or cfg.get("kind") != "pdf":
                raise ParseError(path.name, f"provider {provider!r} has no PDF mapping; add one in Settings")
            period = period or infer_period(str(path))
            result = parse_pdf(str(path), provider, cfg, period, source_url)
        else:
            pf = parse_filename(path.name, settings)
            if not provider:
                if not pf:
                    raise ParseError(path.name, "file name does not match the pattern ProviderName_YYYYMMDD_disclosure.xlsx "
                                                "(see Settings); choose the provider manually")
                provider = find_provider(pf[0], mappings)
                if not provider:
                    raise ParseError(path.name, f"no mapping for provider {pf[0]!r}; add one in Settings → Mappings")
            cfg = mappings.get(provider)
            if not cfg or cfg.get("kind") != "tabular":
                raise ParseError(path.name, f"provider {provider!r} is not configured for spreadsheet files")
            period = period or (pf[1] if pf else None)
            if not period:
                raise ParseError(path.name, "cannot infer the period from the file name; enter it manually")
            result = parse_tabular(str(path), provider, cfg, period, source_url)
        # keep the original file under raw/<provider>/<period>__<name>
        dest = config.RAW_DIR / config.slug(provider) / f"{period}__{safe_name(path.name)}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if path.resolve() != dest.resolve():
            shutil.copyfile(path, dest)
        store.save_result(result, db)
        status = "ok" if result.ok else "checks_failed"
        msg = "; ".join(f"{c.name}: {c.detail}" for c in result.checks if c.status != "pass")
        if ext == ".pdf" and provider in capital.SPECS:
            cap_ok, cap_msg = _store_capital(path, provider, period, source_url, db)
            if not cap_ok:
                status = "checks_failed"
            msg = "; ".join(m for m in (msg, cap_msg) if m)
        store.log_ingest(path.name, provider, period, status, msg, db)
        return Outcome(path.name, status, provider, period, msg, result)
    except MCRError as e:
        log.error("ingest %s failed: %s", path.name, e)
        store.log_ingest(path.name, provider or "", period or "", "error", str(e), db)
        return Outcome(path.name, "error", provider or "", period or "", str(e))
    except Exception as e:  # unexpected: still report, never crash the UI
        log.exception("ingest %s crashed", path.name)
        store.log_ingest(path.name, provider or "", period or "", "error", f"unexpected error: {e}", db)
        return Outcome(path.name, "error", provider or "", period or "", f"unexpected error: {e}")


def ingest_upload(path: Path, provider=None, period=None, only_newest=False, db=None) -> list[Outcome]:
    """A single file or a zip package (unpacked to a temp folder under raw/uploads)."""
    path = Path(path)
    if path.suffix.lower() == ".zip":
        try:
            validate_file(path)
            members = unpack_zip(path, config.RAW_DIR / "uploads" / f"{config.slug(path.stem)}")
        except MCRError as e:
            return [Outcome(path.name, "error", message=str(e))]
        if only_newest:
            members = newest_per_provider(members)
        return [ingest_file(m, provider, period, db=db) for m in members]
    return [ingest_file(path, provider, period, db=db)]
