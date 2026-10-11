"""Convert data/serial_killers.csv into docs/data.json for the search app."""
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
CITATION = re.compile(r"\[[^\]]*\]")
NUMBER = re.compile(r"\d+")
YEAR = re.compile(r"\b(\d{3,4})\b")


def clean(text):
    return CITATION.sub("", str(text)).strip()


def first_int(text):
    match = NUMBER.search(text.replace(",", ""))
    return int(match.group()) if match else None


def year_span(text):
    years = [int(y) for y in YEAR.findall(text)]
    return (min(years), max(years)) if years else (None, None)


def main():
    df = pd.read_csv(ROOT / "data" / "serial_killers.csv")
    records = []
    for i, row in df.iterrows():
        years = clean(row["Years active"])
        proven = clean(row["Proven victims"])
        possible = clean(row["Possible victims"])
        start, end = year_span(years)
        records.append({
            "id": i + 1,
            "name": clean(row["Name"]),
            "country": clean(row["Country"]),
            "years": years,
            "start": start,
            "end": end,
            "proven": proven,
            "possible": possible,
            "provenN": first_int(proven),
            "possibleN": first_int(possible),
            "notes": clean(row["Notes"]),
        })

    out = ROOT / "docs" / "data.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(records, ensure_ascii=False))
    print(f"Wrote {len(records)} records to {out}")


if __name__ == "__main__":
    main()
