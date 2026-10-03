"""Watch a Shopify product page for price drops, sales and coupon/promo banners.

Run: python price_tracker/track.py
Exits 0 always; writes a Markdown report to $REPORT_FILE (default report.md) only
when something changed since the last run, and updates state.json.
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

PRODUCT_URL = os.environ.get(
    "PRODUCT_URL", "https://tappwater.com.au/products/tap-water-filter-refills"
)
STATE_FILE = Path(os.environ.get("STATE_FILE", Path(__file__).with_name("state.json")))
REPORT_FILE = Path(os.environ.get("REPORT_FILE", "report.md"))
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# Sentences on the page that look like a promotion or coupon.
PROMO_RE = re.compile(
    r"(\d+\s?%\s?off|save\s+(?:up\s+to\s+)?\$?\d+|\bcoupon\b|\bpromo\b|discount code"
    r"|\buse code\b|\bcode\s*:|\bsale\b|free shipping|\bbogo\b|buy \d+.{0,20}get)",
    re.I,
)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _money(value, cents: bool) -> float | None:
    """Shopify .js gives integer cents; .json gives strings like '49.00'."""
    if value in (None, ""):
        return None
    return int(value) / 100 if cents else float(value)


def parse_variants(product: dict, cents: bool) -> dict:
    variants = {}
    for v in product.get("variants", []):
        variants[str(v["id"])] = {
            "title": v.get("title") or product.get("title"),
            "price": _money(v.get("price"), cents),
            "compare_at_price": _money(v.get("compare_at_price"), cents),
            "available": v.get("available"),
        }
    return variants


def get_variants(url: str) -> dict:
    try:
        return parse_variants(json.loads(fetch(url + ".js")), cents=True)
    except Exception:
        data = json.loads(fetch(url + ".json"))
        return parse_variants(data["product"], cents=False)


def page_text(raw_html: str) -> str:
    raw_html = re.sub(r"(?is)<(script|style|noscript|svg)\b.*?</\1>", " ", raw_html)
    text = re.sub(r"(?s)<[^>]+>", "\n", raw_html)
    return html.unescape(text)


def extract_promos(raw_html: str) -> list[str]:
    found = set()
    for line in page_text(raw_html).splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if 4 <= len(line) <= 200 and PROMO_RE.search(line):
            found.add(line)
    return sorted(found)


def snapshot(url: str) -> dict:
    variants = get_variants(url)
    promos = set(extract_promos(fetch(url)))
    home = re.match(r"https?://[^/]+", url).group(0)
    try:
        promos |= set(extract_promos(fetch(home)))
    except Exception as e:
        print(f"warning: homepage fetch failed: {e}", file=sys.stderr)
    return {"url": url, "variants": variants, "promos": sorted(promos)}


def fmt(p: float | None) -> str:
    return "—" if p is None else f"${p:,.2f}"


def diff(old: dict | None, new: dict) -> list[str]:
    """Human-readable list of changes worth alerting on."""
    if old is None:
        return ["Tracker started — current baseline recorded below."]
    changes = []
    for vid, v in new["variants"].items():
        o = old["variants"].get(vid)
        if o is None:
            changes.append(f"New option **{v['title']}** at {fmt(v['price'])}")
            continue
        if v["price"] != o["price"]:
            arrow = "🔻 dropped" if (o["price"] or 0) > (v["price"] or 0) else "🔺 rose"
            changes.append(
                f"**{v['title']}** price {arrow}: {fmt(o['price'])} → {fmt(v['price'])}"
            )
        if v["compare_at_price"] != o["compare_at_price"]:
            changes.append(
                f"**{v['title']}** 'was' price changed: "
                f"{fmt(o['compare_at_price'])} → {fmt(v['compare_at_price'])}"
            )
        if v["available"] != o["available"]:
            changes.append(
                f"**{v['title']}** is now {'in stock' if v['available'] else 'sold out'}"
            )
    for vid in old["variants"].keys() - new["variants"].keys():
        changes.append(f"Option **{old['variants'][vid]['title']}** was removed")
    for p in sorted(set(new["promos"]) - set(old["promos"])):
        changes.append(f"🏷️ New promo/coupon text: “{p}”")
    for p in sorted(set(old["promos"]) - set(new["promos"])):
        changes.append(f"Promo text gone: “{p}”")
    return changes


def report(changes: list[str], snap: dict) -> str:
    lines = [f"Changes on {snap['url']}", ""]
    lines += [f"- {c}" for c in changes]
    lines += ["", "### Current prices", "", "| Option | Price | Was | In stock |", "|---|---|---|---|"]
    for v in snap["variants"].values():
        on_sale = v["compare_at_price"] and v["compare_at_price"] > (v["price"] or 0)
        was = fmt(v["compare_at_price"]) if on_sale else "—"
        lines.append(f"| {v['title']} | {fmt(v['price'])} | {was} | {'✅' if v['available'] else '❌'} |")
    lines += ["", "### Promo / coupon text on the site", ""]
    lines += [f"- {p}" for p in snap["promos"]] or ["- (none found)"]
    return "\n".join(lines) + "\n"


def main() -> None:
    old = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else None
    snap = snapshot(PRODUCT_URL)
    changes = diff(old, snap)
    STATE_FILE.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n")
    if changes:
        REPORT_FILE.write_text(report(changes, snap))
        print(f"{len(changes)} change(s); report written to {REPORT_FILE}")
    else:
        print("No changes.")


if __name__ == "__main__":
    main()
