import pytest

from mcr.ratio import cet1_leverage_ratio, fmt_ratio, rank_and_percentile
from mcr.units import detect_units, is_number, parse_number, to_millions


@pytest.mark.parametrize("text,unit", [
    ("(Dollars in millions)", "millions"), ("(Dollars in billions) Requirement", "billions"),
    ("(In millions)", "millions"), ("USD in thousands", "thousands"), ("$ millions", "millions"),
    ("Amounts (millions)", "millions"), ("No unit statement here", None), ("", None)])
def test_detect_units(text, unit):
    assert detect_units(text) == unit


def test_conversion_to_millions():
    assert to_millions(61, "billions") == 61_000
    assert to_millions(4_552_448, "millions") == 4_552_448
    assert to_millions(5_000_000, "thousands") == 5_000
    with pytest.raises(ValueError):
        to_millions(1, "trillions")


@pytest.mark.parametrize("tok,val", [("$3,775,463", 3775463), ("(73,965)", -73965), ("($89)", -89), ("—", 0), ("4.5", 4.5), ("-12", -12)])
def test_parse_number(tok, val):
    assert parse_number(tok) == val


def test_is_number():
    assert is_number("(14)") and is_number("$60") and not is_number("capital") and not is_number("%")


def test_ratio_correctness():
    assert cet1_leverage_ratio(61_000, 4_552_448) == pytest.approx(0.013399, abs=1e-6)
    assert cet1_leverage_ratio(4_250, 61_800) == pytest.approx(0.068770, abs=1e-6)
    with pytest.raises(ValueError):
        cet1_leverage_ratio(1, 0)


def test_ratio_formatting_precision():
    assert fmt_ratio(0.013399, 2) == "1.34% (0.0134)"
    assert fmt_ratio(0.013399, 3) == "1.340% (0.01340)"
    assert fmt_ratio(None) == "—"


def test_rank_and_percentile():
    out = rank_and_percentile({"A": 0.05, "B": 0.03, "C": 0.04, "D": None})
    assert out["A"] == {"rank": 1, "of": 3, "percentile": 100.0}
    assert out["B"]["rank"] == 3 and round(out["B"]["percentile"], 1) == 33.3
    assert "D" not in out
