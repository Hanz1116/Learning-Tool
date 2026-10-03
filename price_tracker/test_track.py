import track

PRODUCT_JS = {"title": "Refills", "variants": [
    {"id": 1, "title": "3 pack", "price": 4900, "compare_at_price": None, "available": True},
    {"id": 2, "title": "6 pack", "price": 8900, "compare_at_price": 9800, "available": True},
]}
PRODUCT_JSON = {"title": "Refills", "variants": [
    {"id": 1, "title": "3 pack", "price": "49.00", "compare_at_price": ""},
]}
HTML = """<html><head><script>var x="20% off code";</script></head><body>
<div class="announcement">Spring SALE: use code SPRING15 for 15% off</div>
<p>Filters remove microplastics.</p><footer>Free shipping over $50</footer></body></html>"""


def test_parse_js_and_json_prices():
    v = track.parse_variants(PRODUCT_JS, cents=True)
    assert v["1"]["price"] == 49.0 and v["2"]["compare_at_price"] == 98.0
    v = track.parse_variants(PRODUCT_JSON, cents=False)
    assert v["1"]["price"] == 49.0 and v["1"]["compare_at_price"] is None


def test_extract_promos_ignores_scripts():
    assert track.extract_promos(HTML) == [
        "Free shipping over $50",
        "Spring SALE: use code SPRING15 for 15% off",
    ]


def test_diff_detects_price_drop_and_new_promo():
    old = {"variants": track.parse_variants(PRODUCT_JS, cents=True), "promos": []}
    new_js = {"variants": [dict(PRODUCT_JS["variants"][0], price=3900), PRODUCT_JS["variants"][1]]}
    new = {"url": "u", "variants": track.parse_variants(new_js, cents=True), "promos": ["10% off"]}
    changes = track.diff(old, new)
    assert any("dropped" in c and "$49.00 → $39.00" in c for c in changes)
    assert any("10% off" in c for c in changes)
    assert track.diff(new, new) == []
    assert "| 3 pack | $39.00 |" in track.report(changes, new)
