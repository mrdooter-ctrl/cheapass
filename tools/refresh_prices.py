#!/usr/bin/env python3
"""Refresh CheapAss prices from public Shopify product feeds.

Tier 1 (plain script, no AI, no keys). Run weekly:
    python3 tools/refresh_prices.py            # dry run: prints changes only
    python3 tools/refresh_prices.py --write    # saves data/catalog.json
Then: python3 tools/build.py

Only rows with "source": "shopify" are touched. Manual rows are listed
when older than 30 days so a human (or Rio) can recheck them.
"""
import json, sys, time, urllib.request, datetime, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CATALOG = ROOT / "data" / "catalog.json"
UA = "Mozilla/5.0 (compatible; price-check)"
TODAY = datetime.date.today().isoformat()


def fetch_feed(base):
    """Return every product in a Shopify store's /products.json."""
    products, page = [], 1
    while page <= 10:
        url = f"{base}/products.json?limit=250&page={page}"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            batch = json.load(r).get("products", [])
        if not batch:
            break
        products += batch
        page += 1
        time.sleep(1)
    return products


def find(item, products):
    m = item["match"].lower()
    excl = [e.lower() for e in item.get("exclude", [])]
    for p in products:  # exact handle first
        if p.get("handle", "").lower() == m:
            return p
    hits = [p for p in products
            if m in p.get("title", "").lower()
            and not any(e in p["title"].lower() for e in excl)]
    return hits[0] if len(hits) == 1 else (None if not hits else "AMBIGUOUS")


def money(v):
    try:
        return round(float(v), 2) if v not in (None, "") else None
    except ValueError:
        return None


def main():
    write = "--write" in sys.argv
    data = json.loads(CATALOG.read_text())
    feeds, changes, problems = {}, [], []
    for it in data["items"]:
        if it.get("source") == "amazon":  # Amazon prices are never stored
            continue
        if it.get("source") != "shopify":
            if it.get("checked"):
                age = (datetime.date.today() - datetime.date.fromisoformat(it["checked"])).days
                if age > 30:
                    problems.append(f"MANUAL {it['id']}: last checked {age} days ago")
            else:
                problems.append(f"MANUAL {it['id']}: no price yet")
            continue
        base = it["feed"]
        if base not in feeds:
            try:
                feeds[base] = fetch_feed(base)
            except Exception as e:  # network or format error: keep old data
                feeds[base] = None
                problems.append(f"FEED {base}: {e}")
        prods = feeds[base]
        if prods is None:
            continue
        p = find(it, prods)
        if p == "AMBIGUOUS":
            problems.append(f"AMBIGUOUS {it['id']}: tighten match/exclude")
            continue
        if p is None:
            if it.get("price") is not None:
                changes.append(f"GONE {it['id']}: not in feed, price cleared")
            it.update(price=None, was=None)
            continue
        v = p["variants"][0]
        price, was = money(v.get("price")), money(v.get("compare_at_price"))
        if was is not None and price is not None and was <= price:
            was = None
        avail = any(x.get("available", True) for x in p["variants"])
        if not avail:
            price = None
            changes.append(f"SOLD OUT {it['id']}")
        if (price, was) != (it.get("price"), it.get("was")):
            changes.append(f"PRICE {it['id']}: {it.get('price')} -> {price} (was {was})")
        it.update(price=price, was=was, checked=TODAY,
                  url=f"{base}/products/{p['handle']}")
    print("\n".join(changes) or "No price changes.")
    if problems:
        print("\nNeeds a look:\n" + "\n".join(problems))
    if write:
        CATALOG.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
        print(f"\nSaved {CATALOG}")
    else:
        print("\nDry run. Add --write to save.")


if __name__ == "__main__":
    main()
