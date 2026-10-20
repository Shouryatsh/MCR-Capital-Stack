"""JSON API behind the React frontend: same numbers as the Streamlit app, exact integers, auth gate, no cross-entity mixing."""
import pytest
from fastapi.testclient import TestClient

from mcr import api, gnma
from test_tabs import seed_gnma, seed_observations


@pytest.fixture()
def client(env):
    seed_observations()
    seed_gnma(env)
    return TestClient(api.create_app(dist=env / "nodist"))


def test_meta(client):
    m = client.get("/api/meta").json()
    assert m["units"] == "$ millions" and m["has_cet1"] and m["has_gnma"] and m["periods"] == ["2025Q1"]
    assert m["last_updated"] and m["primary_provider"] == "Fannie Mae"


def test_gnma_reference_values_and_exactness(client):
    g = client.get("/api/gnma").json()
    latest = g["series"][-1]
    assert latest["latest"] and latest["fiscal_year"] == 2023 and latest["reporting_date"] == "2023-09-30"
    assert latest["total_usd"] == 2_613_623_651_000 and latest["total_usd_text"] == "$2,613,623,651,000"
    assert latest["total_published"] == "$2,613,623,651 (USD thousands)"
    assert latest["total_usd"] == latest["mbs_usd"] + latest["commitments_usd"]
    fy22 = next(r for r in g["series"] if r["fiscal_year"] == 2022)
    assert fy22["total_usd"] == 2_442_351_095_000 and fy22["total_published"] == "$2,442,351,095 (USD thousands)"
    assert [r["fiscal_year"] for r in g["series"]] == [2021, 2022, 2023]  # chronological
    assert g["reference"]["2023"]["total"] == 2_613_623_651_000


def test_gnma_traceability_and_validation(client):
    g = client.get("/api/gnma").json()
    latest = g["series"][-1]
    assert latest["source_report"] == "annual_report23.pdf" and latest["printed_page"] == "A-20"
    assert latest["source_url"].endswith("annual_report23.pdf") and latest["note"].startswith("Note 2")
    status = {c["name"]: c["status"] for c in g["validation"]}
    assert status["FY2023 equals the reference total $2,613,623,651 (USD thousands)"] == "pass"
    assert status["FY2022 equals the reference total $2,442,351,095 (USD thousands)"] == "pass"
    assert len(g["observations"]) == 4  # own + comparative column of each of two reports


def test_gnma_yoy_uses_consecutive_years_only(client):
    series = {r["fiscal_year"]: r for r in client.get("/api/gnma").json()["series"]}
    assert series[2021]["yoy"] is None  # FY2020 is not in this dataset: no fabricated change
    y = series[2023]["yoy"]
    assert y["prior_fiscal_year"] == 2022
    assert y["total_abs_usd"] == 2_613_623_651_000 - 2_442_351_095_000 == 171_272_556_000
    assert y["total_pct"] == round(171_272_556 / 2_442_351_095 * 100, 4) == 7.0126 and y["rounded"] is False


def test_peers_match_streamlit_summary(client):
    p = client.get("/api/peers").json()
    assert p["period"] == "2025Q1" and len(p["rows"]) == 10
    fannie = p["rows"][0]
    assert (fannie["name"], fannie["cet1_mm"], fannie["ata_mm"], fannie["rank"], fannie["of"]) == ("Fannie Mae", 61_000, 4_552_448, 1, 2)
    assert fannie["ratio"] == pytest.approx(61_000 / 4_552_448)
    assert fannie["cet1_src"]["source_file"] == "Fannie Mae.pdf"
    assert p["stats"]["have"] == 2 and p["stats"]["top"] == "Fannie Mae" and p["stats"]["primary_rank"] == 1
    assert client.get("/api/peers", params={"period": "1999Q1"}).status_code == 404


def test_entity_series_and_isolation_from_gnma(client):
    e = client.get("/api/entities").json()
    assert e["providers"] == ["Fannie Mae", "Freddie Mac"] and e["primary"] == "Fannie Mae"
    s = client.get("/api/entities/Freddie Mac/series").json()
    assert s["series"][0]["cet1_mm"] == 49_000 and s["series"][0]["ata"]["value_mm"] == 3_833_729
    assert client.get("/api/entities/GNMA/series").status_code == 404


def test_sources(client):
    s = client.get("/api/sources").json()
    assert len(s["observations"]) == 4 and set(s) == {"observations", "fetch_log", "ingest_log"}


def test_empty_database_returns_empty_not_errors(env):
    c = TestClient(api.create_app(dist=env / "nodist"))
    assert c.get("/api/peers").json() == {"periods": [], "period": None, "rows": [], "stats": None}
    g = c.get("/api/gnma").json()
    assert g["series"] == [] and g["validation"] == [] and c.get("/api/meta").json()["has_gnma"] is False


def test_token_gate(client, monkeypatch):
    monkeypatch.setenv("MCR_TOKEN", "s3cret")
    assert client.get("/api/gnma").status_code == 401
    assert client.get("/api/gnma", headers={"X-MCR-Token": "wrong"}).status_code == 401
    assert client.get("/api/gnma", headers={"X-MCR-Token": "s3cret"}).status_code == 200
    h = client.get("/api/health").json()
    assert h == {"status": "ok", "auth_required": True}


def test_refresh_runs_once_and_reports_status(client, monkeypatch):
    monkeypatch.setattr(gnma, "ingest_all", lambda: [gnma.ReportResult(2023, "annual_report23.pdf", [], ["gap"])])
    r = client.post("/api/gnma/refresh")
    assert r.status_code == 202
    for _ in range(50):
        st = client.get("/api/gnma/refresh").json()
        if not st["running"]:
            break
    assert st["reports"] == 1 and st["with_figures"] == 0 and st["error"] is None


def test_spa_fallback_and_static_serving(env):
    dist = env / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "assets" / "a.js").write_text("x")
    c = TestClient(api.create_app(dist=dist))
    assert c.get("/gnma").text == "<html>app</html>" and c.get("/assets/a.js").text == "x"
    assert c.get("/gnma").headers["cache-control"] == "no-cache"  # a rebuild must reach users immediately
    assert c.get("/api/nope").status_code == 404
    assert c.get("/..%2f..%2fREADME.md").text == "<html>app</html>"  # no path traversal out of dist
