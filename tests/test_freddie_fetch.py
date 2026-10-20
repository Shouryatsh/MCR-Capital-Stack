from mcr.freddie import list_disclosures, period_from_url

HTML = """<html><body>
<a href="/investors/docs/2Q26_ercf_public_disclosure.pdf">PDF</a>
<a href="/investors/docs/4Q24_ERCF_Public_Disclosure.pdf">PDF</a>
<a href="/investors/docs/1Q26_ercf_public_disclosure.pdf">PDF</a>
<a href="/investors/other.pdf">other</a><a href="/investors/ercf-public-disclosure">self</a></body></html>"""


def test_period_from_url():
    assert period_from_url("https://x/2Q26_ercf_public_disclosure.pdf") == "2026Q2"
    assert period_from_url("https://x/4Q24_ERCF_Public_Disclosure.pdf") == "2024Q4"
    assert period_from_url("https://x/other.pdf") is None


def test_list_disclosures_newest_first():
    items = list_disclosures(HTML, "https://www.freddiemac.com/investors/ercf-public-disclosure")
    assert [i["period"] for i in items] == ["2026Q2", "2026Q1", "2024Q4"]
    assert items[0]["url"] == "https://www.freddiemac.com/investors/docs/2Q26_ercf_public_disclosure.pdf"
