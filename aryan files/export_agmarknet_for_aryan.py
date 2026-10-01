"""Export the OFFICIAL Agmarknet daily prices AIAIC holds, for Aryan's model (D-124). Run by the owner; sends a file.

Source: data.gov.in "Variety-wise Daily Market Prices" (Agmarknet, resource 35985678-...), the same series AIAIC's
price layers are built from; open data under the Government Open Data Licence - India (attribute data.gov.in).
The 91 raw CSVs live in `price-datasets/` (about 1.1 GB, gitignored, 2001-2026).

Output, in Aryan's loader's column names (`src/ingestion/csv_loader.py` aliases), with ISO dates:
    for_team/aryan/out/agmarknet_mh_mp_<first year>_<last year>.csv.gz
    columns: state, district, market, commodity, variety, grade, date (YYYY-MM-DD), min_price, max_price, modal_price

WHY ISO DATES: the raw files write `08/07/2020` for 8 July (day first). A reader that assumes month first turns it into
7 August without an error. An ISO date cannot be read two ways.

    python for_team/aryan/export_agmarknet_for_aryan.py [--from-year 2016] [--crops Onion Wheat Soyabean Tur Gram]
"""
from __future__ import annotations

import argparse
import glob
import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(REPO, "price-datasets")
STATES = ("Maharashtra", "Madhya Pradesh")
DEFAULT_CROPS = ("Onion", "Wheat", "Soyabean", "Arhar (Tur/Red Gram)(Whole)", "Bengal Gram(Gram)(Whole)", "Tomato",
                 "Potato", "Cotton", "Maize", "Paddy(Dhan)(Common)")
RENAME = {"State": "state", "District": "district", "Market": "market", "Commodity": "commodity", "Variety": "variety",
          "Grade": "grade", "Arrival_Date": "date", "Min_Price": "min_price", "Max_Price": "max_price",
          "Modal_Price": "modal_price"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-year", type=int, default=2016)
    ap.add_argument("--crops", nargs="+", default=list(DEFAULT_CROPS), help="exact Agmarknet commodity names")
    args = ap.parse_args()
    files = sorted(glob.glob(os.path.join(SRC, "*.csv")))
    if not files:
        raise SystemExit(f"No raw price files in {SRC}")
    parts = []
    for f in files:
        for chunk in pd.read_csv(f, usecols=list(RENAME), dtype=str, chunksize=500_000):
            chunk = chunk[chunk["State"].isin(STATES) & chunk["Commodity"].isin(args.crops)]
            if chunk.empty:
                continue
            chunk = chunk.rename(columns=RENAME)
            chunk["date"] = pd.to_datetime(chunk["date"], format="%d/%m/%Y", errors="coerce")
            chunk = chunk[chunk["date"].dt.year >= args.from_year].dropna(subset=["date"])
            for c in ("min_price", "max_price", "modal_price"):
                chunk[c] = pd.to_numeric(chunk[c], errors="coerce")
            parts.append(chunk)
    df = pd.concat(parts, ignore_index=True).drop_duplicates()
    df = df.sort_values(["state", "commodity", "market", "date"])
    first, last = df["date"].dt.year.min(), df["date"].dt.year.max()
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    out = os.path.join(HERE, "out", f"agmarknet_mh_mp_{first}_{last}.csv.gz")
    df[list(RENAME.values())].to_csv(out, index=False, compression="gzip")
    print(f"wrote {out}: {len(df):,} rows, {df['market'].nunique()} mandis, {df['commodity'].nunique()} crops, "
          f"{first}-{last}")
    print(df.groupby(["state", "commodity"]).size().to_string())


if __name__ == "__main__":
    main()
