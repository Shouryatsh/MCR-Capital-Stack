import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Isolated config / raw / database so tests never touch real data."""
    from mcr import config, mappings, store
    for mod, attr, val in [(config, "CONFIG_DIR", tmp_path / "config"), (config, "RAW_DIR", tmp_path / "raw"),
                           (config, "DATA_DIR", tmp_path / "data"), (store, "DB_PATH", tmp_path / "data" / "mcr.db"),
                           (store, "DATA_DIR", tmp_path / "data"), (mappings, "CONFIG_DIR", tmp_path / "config")]:
        monkeypatch.setattr(mod, attr, val)
    (tmp_path / "raw").mkdir()
    return tmp_path


@pytest.fixture()
def with_banka(env):
    from mcr.mappings import load_mappings, save_mappings
    from samples import BANKA_MAPPING
    m = load_mappings()
    m["BankA"] = BANKA_MAPPING
    save_mappings(m)
    return env


@pytest.fixture()
def fannie_pdf():
    return FIX / "fannie_2023Q4.pdf"


@pytest.fixture()
def freddie_pdf():
    return FIX / "freddie_1Q25.pdf"
