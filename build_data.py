"""Convert data/serial_killers.csv into docs/data.json for the search app.

Photos and article links are looked up on Wikipedia and cached in
data/wiki_cache.json; delete that file to refresh them.
"""
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
CACHE = ROOT / "data" / "wiki_cache.json"
CITATION = re.compile(r"\[[^\]]*\]")
NUMBER = re.compile(r"\d+")
YEAR = re.compile(r"\b(\d{3,4})\b")
# Wikipedia short descriptions that confirm we matched the right person.
RELEVANT = re.compile(
    r"kill|murder|criminal|poison|strangler|ripper|cannibal|slayer|"
    r"robber|bandit|gang|assassin|crime|rapist|outlaw|executed|convicted",
    re.I,
)
PLACEHOLDER_NAMES = {"unknown", "unidentified", "unidentified killer", "unknown killer"}
API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "NightJar/1.0 (https://github.com/kemckai/NightJar)"


def clean(text):
    return CITATION.sub("", str(text)).strip()


def first_int(text):
    match = NUMBER.search(text.replace(",", ""))
    return int(match.group()) if match else None


def year_span(text):
    years = [int(y) for y in YEAR.findall(text)]
    return (min(years), max(years)) if years else (None, None)


def title_candidates(name):
    """'Lunz, Christopher' -> ['Christopher Lunz', 'Lunz, Christopher']."""
    parts = [p.strip() for p in name.split(",")]
    if len(parts) == 2 and all(parts) and " and " not in name:
        return [f"{parts[1]} {parts[0]}", name]
    return [name]


def query_wikipedia(titles):
    params = {
        "action": "query",
        "format": "json",
        "formatversion": 2,
        "redirects": 1,
        "prop": "pageimages|description|pageprops",
        "ppprop": "disambiguation",
        "piprop": "thumbnail",
        "pithumbsize": 240,
        "titles": "|".join(titles),
    }
    req = urllib.request.Request(
        f"{API}?{urllib.parse.urlencode(params)}", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        data = json.load(res)["query"]

    # Map each requested title through normalization/redirects to the final page.
    alias = {t: t for t in titles}
    for step in ("normalized", "redirects"):
        hops = {h["from"]: h["to"] for h in data.get(step, [])}
        alias = {t: hops.get(a, a) for t, a in alias.items()}

    pages = {p["title"]: p for p in data.get("pages", [])}
    results = {}
    for requested, final in alias.items():
        page = pages.get(final)
        if (
            not page
            or page.get("missing")
            or "disambiguation" in page.get("pageprops", {})
            or not RELEVANT.search(page.get("description", ""))
        ):
            results[requested] = None
            continue
        results[requested] = {
            "url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(page["title"].replace(" ", "_")),
            "photo": page.get("thumbnail", {}).get("source", "").split("?")[0] or None,
        }
    return results


def lookup_all(names):
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    wanted = sorted({t for n in names for t in title_candidates(n)} - cache.keys())
    for i in range(0, len(wanted), 50):
        batch = wanted[i : i + 50]
        cache.update(query_wikipedia(batch))
        print(f"  Wikipedia lookup {min(i + 50, len(wanted))}/{len(wanted)}")
        time.sleep(0.5)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0, sort_keys=True))

    matches = {}
    for n in names:
        matches[n] = next((cache[t] for t in title_candidates(n) if cache.get(t)), None)
    return matches


def tidy_name(raw):
    """'Muhammad, John Allen, 41 Malvo, Lee Boyd' -> 'John Allen Muhammad and Lee Boyd Malvo'."""
    name = clean(raw)
    accused = name.endswith("(accused)")
    name = name.removesuffix("(accused)").strip()
    people = [p.strip() for p in re.split(r",\s*\d+\b", name) if p.strip()]
    name = " and ".join(title_candidates(p)[0] for p in people)
    return f"{name} (accused)" if accused else name


def name_key(name):
    """'Gacy, John Wayne' and 'John Wayne Gacy' -> 'john wayne gacy'."""
    name = title_candidates(name)[0]
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", name).split())


def is_group(name):
    return bool(re.search(r"\band\b|&|brothers|sisters|crew|gang", name, re.I))


def dedupe(records):
    """Merge rows describing the same person, keeping the most detailed one.

    Rows match when their names are equal after normalization, or when they
    link to the same Wikipedia article and one name's words contain the
    other's (e.g. 'Kraft, Randy' / 'Randy Steven Kraft'). Group entries and
    placeholder names like 'Unknown' are never merged with anything else.
    """
    parent = list(range(len(records)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        parent[find(a)] = find(b)

    keys = [name_key(r["name"]) for r in records]
    first_by_key, by_wiki = {}, {}
    for i, r in enumerate(records):
        if keys[i] in PLACEHOLDER_NAMES:
            continue
        if keys[i] in first_by_key:
            union(i, first_by_key[keys[i]])
        else:
            first_by_key[keys[i]] = i
        if r["wiki"] and not is_group(r["name"]):
            by_wiki.setdefault(r["wiki"], []).append(i)

    for idxs in by_wiki.values():
        for a in idxs:
            for b in idxs:
                if a < b:
                    wa, wb = set(keys[a].split()), set(keys[b].split())
                    if wa <= wb or wb <= wa:
                        union(a, b)

    groups = {}
    for i in range(len(records)):
        groups.setdefault(find(i), []).append(records[i])

    merged = []
    for rows in groups.values():
        best = max(rows, key=lambda r: (len(r["notes"]), r["provenN"] or 0))
        merged.append({
            **best,
            "name": best["name"],
            "photo": best["photo"] or next((r["photo"] for r in rows if r["photo"]), None),
            "wiki": best["wiki"] or next((r["wiki"] for r in rows if r["wiki"]), None),
        })
    merged.sort(key=lambda r: r["id"])
    return merged


def main():
    df = pd.read_csv(ROOT / "data" / "serial_killers.csv")
    names = [tidy_name(n) for n in df["Name"]]
    wiki = lookup_all(names)

    records = []
    for i, row in df.iterrows():
        years = clean(row["Years active"])
        proven = clean(row["Proven victims"])
        possible = clean(row["Possible victims"])
        start, end = year_span(years)
        match = wiki.get(names[i]) or {}
        records.append({
            "id": i + 1,
            "name": names[i],
            "country": clean(row["Country"]),
            "years": years,
            "start": start,
            "end": end,
            "proven": proven,
            "possible": possible,
            "provenN": first_int(proven),
            "possibleN": first_int(possible),
            "notes": clean(row["Notes"]),
            "photo": match.get("photo"),
            "wiki": match.get("url"),
        })

    before = len(records)
    records = dedupe(records)
    print(f"Removed {before - len(records)} duplicate rows")

    out = ROOT / "docs" / "data.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(records, ensure_ascii=False))
    photos = sum(1 for r in records if r["photo"])
    links = sum(1 for r in records if r["wiki"])
    print(f"Wrote {len(records)} records to {out} ({photos} with photos, {links} with Wikipedia links)")


if __name__ == "__main__":
    main()
