#!/usr/bin/env python3
"""Build CheapAss: _src/**/*.html + data/*.json -> site pages (same paths).

Tier 1 (plain script, stdlib only). Run after refresh_prices.py.
Markers in src pages:
  {{TABLE:<group>}}  {{TABLE:<group>:pertb}}  {{TABLE:<group>:cloud}}
  {{BRAND:<Brand>}}      every product from one brand
  {{DEALS}} / {{DEALS:<Brand>}}   only real price drops, biggest % first
  {{SEASON}} {{SEASON_NOTE}}      sale heading/note from data/site.json by date
  {{CHECKED_AT}}  {{ROOT}} (relative path to site root)
First line of each src page: <!-- {"title": "...", "description": "..."} -->
A price shows only if checked within 14 days (store feeds) or 45 days (manual).
Links: manual link in links.json > Amazon product link (rows with "asin") > Awin deep link (brand approved) > plain store URL.
Amazon rows ("source": "amazon", "asin"): never store or show a price (Amazon rules); the link carries the
_amazon tag plus the UTM fields in _amazon.utm. Optional "faq": [[q, a], ...] in the meta line adds a
visible FAQ block and FAQPage schema.
"""
import json, re, html, datetime, pathlib, urllib.parse, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "_src"  # underscore: GitHub Pages does not publish it
TODAY = datetime.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else datetime.date.today()
MAX_AGE = {"shopify": 14, "manual": 45}

CSS = """body{font-family:Georgia,serif;max-width:780px;margin:0 auto;padding:16px;background:#fff;color:#111;line-height:1.5}
h1{font-size:1.6em;margin:.2em 0} h2{font-size:1.2em;margin-top:1.6em} .tag{color:#555;margin:2px 0 12px}
.brand{font-weight:bold;color:#111;text-decoration:none} nav{font-size:.9em;margin-bottom:8px;line-height:1.9} nav a{margin-right:10px}
.note{background:#ffffcc;border:1px solid #cc9;padding:8px;font-size:.9em} .sale{background:#111;color:#fff;padding:8px 10px;font-weight:bold}
.wrap{overflow-x:auto} table{border-collapse:collapse;width:100%;margin:12px 0;font-size:.95em}
td,th{border-bottom:1px solid #ddd;padding:6px 4px;text-align:left;vertical-align:top} th{font-size:.85em;color:#555}
.was{color:#888;text-decoration:line-through} .pct{color:#060;font-weight:bold} a{color:#00c} small{color:#666}
label{display:block;margin:6px 0} input{font:inherit;width:7em} .out{font-size:1.1em;background:#f4f4f4;padding:8px}
@media (prefers-color-scheme: dark){body{background:#111;color:#eee}.brand{color:#eee}.sale{background:#eee;color:#111}.note{background:#332;border-color:#665}td,th{border-color:#333}a{color:#8af}.tag,th,small{color:#aaa}.out{background:#222}input{background:#222;color:#eee;border:1px solid #555}}"""


def nav(r):
    return (f'<nav><a class="brand" href="{r}index.html">CheapAss</a> '
            f'<a href="{r}deals/gmktec.html">GMKtec</a><a href="{r}deals/beelink.html">Beelink</a>'
            f'<a href="{r}deals/unifydrive.html">UnifyDrive</a>'
            f'<a href="{r}guides/cheap-nas.html">NAS guide</a><a href="{r}guides/mini-pc-homelab.html">Mini PC guide</a>'
            f'<a href="{r}guides/index.html">All guides</a><a href="{r}index.html#under-30">Under $30</a></nav>')


def load(name, default=None):
    p = ROOT / "data" / name
    return json.loads(p.read_text()) if p.exists() else default


def fresh(it):
    if it.get("price") is None or not it.get("checked"):
        return False
    age = (TODAY - datetime.date.fromisoformat(it["checked"])).days
    return 0 <= age <= MAX_AGE.get(it.get("source"), 14)


def drop(it):
    return fresh(it) and it.get("was") and it["was"] > it["price"]


def pct(it):
    return round(100 * (1 - it["price"] / it["was"])) if drop(it) else 0


class Ctx:
    def __init__(self):
        cat = load("catalog.json")
        self.items, self.awin = cat["items"], cat.get("_awin", {})
        self.amazon_tag = cat.get("_amazon", {}).get("tag", "")
        self.amazon_utm = cat.get("_amazon", {}).get("utm", {})
        self.links = load("links.json", {})
        self.site = load("site.json", {})

    def url(self, it):
        manual = self.links.get(it["id"], "")
        if manual:
            return manual, True
        if it.get("asin") and self.amazon_tag:
            q = urllib.parse.urlencode({"tag": self.amazon_tag, **self.amazon_utm})
            return f"https://www.amazon.com/dp/{it['asin']}?{q}", True
        base = it.get("url") or it.get("feed") or "#"
        b = self.awin.get("brands", {}).get(it.get("brand", ""), {})
        if self.awin.get("affid") and b.get("approved") and b.get("mid"):
            q = urllib.parse.urlencode({"awinmid": b["mid"], "awinaffid": self.awin["affid"], "ued": base})
            return "https://www.awin1.com/cread.php?" + q, True
        return base, False

    def link(self, it, text):
        u, aff = self.url(it)
        rel = "sponsored nofollow" if aff else "nofollow"
        return f'<a href="{html.escape(u)}" rel="{rel}">{html.escape(text)}</a>'


    def amazon(self, it):
        if not (self.amazon_tag and it.get("amazon")):
            return ""
        u = "https://www.amazon.com/s?" + urllib.parse.urlencode({"k": it["amazon"], "tag": self.amazon_tag})
        return f'<br><small><a href="{html.escape(u)}" rel="sponsored nofollow">Check Amazon</a></small>'


def price_cell(c, it):
    if it.get("source") == "amazon":
        return c.link(it, "Check price on Amazon")
    if not fresh(it):
        return c.link(it, "See today's price")
    s = f"<b>${it['price']:,.2f}</b>"
    if drop(it):
        s += f' <span class="was">${it["was"]:,.2f}</span>'
        if pct(it) >= 5:
            s += f' <span class="pct">-{pct(it)}%</span>'
    return s


def table(c, rows, mode=None, show_cols=True):
    if not rows:
        return "<p><small>Nothing listed right now. Check back after the next price check.</small></p>"
    if mode == "pertb":
        rows = sorted(rows, key=lambda i: (not fresh(i), (i["price"] / i["tb"]) if fresh(i) else 0))
    cols = list(rows[0].get("cols", {}).keys()) if show_cols else []
    head = ["Product", "Price"] + (["Per TB"] if mode == "pertb" else []) \
        + (["Per year, kept 5 yrs"] if mode == "cloud" else []) + cols + ["Why it's here"]
    out = ['<div class="wrap"><table>', "<tr>" + "".join(f"<th>{h}</th>" for h in head) + "</tr>"]
    for i in rows:
        cells = [c.link(i, i["name"]) + c.amazon(i), price_cell(c, i)]
        if mode == "pertb":
            cells.append(f"${i['price']/i['tb']:,.2f}" if fresh(i) else "-")
        if mode == "cloud":
            cells.append("-" if not fresh(i) else
                         f"${i['price']/5:,.0f}" if i.get("kind") == "lifetime" else f"${i['price']:,.0f}")
        cells += [html.escape(i.get("cols", {}).get(k, "")) for k in cols]
        cells.append(html.escape(i.get("note", "")))
        out.append("<tr>" + "".join(f"<td>{x}</td>" for x in cells) + "</tr>")
    out.append("</table></div>")
    return "\n".join(out)


def season(c):
    for s in c.site.get("seasons", []):
        if s["from"] <= TODAY.isoformat() <= s["to"]:
            return s
    return {"heading": "This week's price drops", "note": ""}


def render(c, body, r):
    used = []

    def tab(m):
        kind, arg, mode = m.group(1), m.group(2), m.group(3)
        if kind == "TABLE":
            rows = [i for i in c.items if i["group"] == arg]
        elif kind == "BRAND":
            rows = [i for i in c.items if i.get("brand") == arg]
            rows.sort(key=lambda i: (i["group"], not fresh(i), i.get("price") or 0))
        else:  # DEALS
            rows = [i for i in c.items if drop(i) and i.get("brand") and (not arg or i.get("brand") == arg)]
            rows.sort(key=lambda i: -pct(i))
        used.extend(rows)
        same = len({tuple(i.get("cols", {})) for i in rows}) == 1
        return table(c, rows, mode, show_cols=(kind != "DEALS" and same))

    body = re.sub(r"\{\{(TABLE|BRAND|DEALS)(?::([\w ]+))?(?::(\w+))?\}\}", tab, body)
    s = season(c)
    dates = [i["checked"] for i in used if fresh(i)]
    checked = max(dates) if dates else None
    body = (body.replace("{{SEASON}}", html.escape(s["heading"]))
                .replace("{{SEASON_NOTE}}", html.escape(s.get("note", "")))
                .replace("{{CHECKED_AT}}", checked or "not yet")
                .replace("{{ROOT}}", r))
    return body, bool(used), checked, any(i.get("source") == "amazon" for i in used)


def build_page(c, src):
    rel = src.relative_to(SRC)
    r = "../" * (len(rel.parts) - 1)
    meta_line, body = src.read_text().split("\n", 1)
    meta = json.loads(meta_line.strip()[4:-3])
    body, has_products, checked, has_amazon = render(c, body, r)
    faq = meta.get("faq") or []
    schema = ""
    if faq:
        body += "\n<h2>FAQ</h2>\n" + "\n".join(
            f"<h3>{html.escape(q)}</h3>\n<p>{html.escape(a)}</p>" for q, a in faq)
        ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}
        schema = '<script type="application/ld+json">' + json.dumps(ld).replace("</", "<\\/") + "</script>"
    disclosure = ""
    if has_amazon:
        disclosure = ('<p class="note">As an Amazon Associate I earn from qualifying purchases. '
                      'Product links on this page go to Amazon. Prices are not shown here because Amazon '
                      'changes them by the hour. Check the price on Amazon before you buy.</p>')
    elif has_products:
        disclosure = ('<p class="note">Some links on this page may be affiliate links. If you buy '
                      'through them, CheapAss may earn a commission at no extra cost to you. '
                      f'Prices last checked: <b>{checked or "not yet"}</b> on each brand\'s own US store. '
                      'Prices change fast. Check at checkout. '
                      'As an Amazon Associate, CheapAss earns from qualifying purchases.</p>')
    canon = ""
    if c.site.get("site_url"):
        canon = f'<link rel="canonical" href="{c.site["site_url"].rstrip("/")}/{rel.as_posix()}">'
    verify = ""  # Search Console ownership tag, kept in site.json so rebuilds never drop it
    if c.site.get("google_site_verification"):
        verify = f'<meta name="google-site-verification" content="{html.escape(c.site["google_site_verification"])}" />'
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(meta['title'])}</title>
<meta name="description" content="{html.escape(meta['description'])}">
{canon}
{verify}
{schema}
<style>
{CSS}
</style>
</head>
<body>
{nav(r)}
{disclosure}
{body}
<hr>
<p><small>CheapAss is a one-person deal list. No sponsored rankings. If a deal dies, it comes off the page. As an Amazon Associate, CheapAss earns from qualifying purchases. Page built {TODAY.isoformat()}.</small></p>
</body>
</html>
"""
    out = ROOT / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)
    print("built", rel.as_posix())


def main():
    c = Ctx()
    pages = []
    for src in sorted(SRC.rglob("*.html")):
        build_page(c, src)
        pages.append(src.relative_to(SRC).as_posix())
    base = c.site.get("site_url", "").rstrip("/")
    if base:  # sitemap + robots so search engines find every page
        urls = "".join(f"<url><loc>{base}/{p}</loc><lastmod>{TODAY.isoformat()}</lastmod></url>" for p in pages)
        (ROOT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n')
        (ROOT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n")


if __name__ == "__main__":
    main()
