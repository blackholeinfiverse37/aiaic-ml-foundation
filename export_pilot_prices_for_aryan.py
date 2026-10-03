"""Export the pilot crops' OFFICIAL Agmarknet daily prices for Aryan's forecast, with AIAIC's mandi identity (2026-10-02).

Run by the owner from the repo root. It only WRITES the files to send; it changes nothing else:
    python for_team/aryan/export_pilot_prices_for_aryan.py [--from-year 2001] [--crops onion soybean tur wheat]

SOURCE. data.gov.in "Variety-wise Daily Market Prices" (Agmarknet, resource 35985678-0d79-46b4-9ed6-6f13308a1d24), the
owner's download in `price-datasets/` (gitignored, about 1.1 GB, 2001-2026). Open data under the Government Open Data
Licence - India: attribute "data.gov.in / Agmarknet". The files are read EXACTLY as AIAIC's `price_history` table was
loaded (`price-prep/load_price_history_to_db.py`, with the helpers of `price-prep/build_seasonal_from_datasets.py`):
- a whole file that duplicates another is skipped;
- dates are DD/MM/YYYY (written out as ISO, which cannot be read two ways);
- a modal price must be a positive number;
- every published line is kept, with its file and line. Agmarknet publishes several lots per mandi, variety, grade and
  day, and none of them is a copy. `(source_file, source_line)` is the same key `price_history` uses, so every
  exported row can be found again in AIAIC's database.

WHAT IS NEW against the 2016-2026 export of 2026-09-28:
- `mandi`: AIAIC's identity for the market, by the IDENTITY rules of `badyears-prep/build_price_shock_years.py`
  (D-116 M1, m12), computed over the SAME raw files. Agmarknet renamed about 700 mandis "X" -> "X APMC" in November
  2025 ("Indore" ends on 2025-11-04 and "Indore APMC" starts on 2025-11-01). A model keyed on the published name sees
  two short series where there is one mandi, and lists the dead name as a mandi it can forecast. `market` stays
  exactly as published; `mandi` is what to key a series on.
- `mandi_district`: the mandi's district by AIAIC's closed district list.
- `crop`: AIAIC's crop for the published commodity name (`engine/dataset_adapters/agmarknet_adapter.COMMODITY_TO_CROP`,
  exact, hand-checked pairs). Agmarknet spelled whole tur three ways since 2001 ("Arhar (Tur/Red Gram)(Whole)" to
  2025-11-04, "Arhar(Tur/Red Gram)(Whole)" 2025-11-01 to 2026-05-06, "Red gram/Arhar/Tur(whole)" from 2026-04-01);
  selected by `commodity` alone, tur's prices stopped on 2025-11-04. Rows are SELECTED by `crop`.
- `source_file_id`, `source_line`: where each row was published (`sources.csv` maps the id to the file and its sha256).
- the years from 2001 (no 2016 cut), for the pilot crops (owner decision 9: Nashik onion, soybean, tur; Indore
  soybean, wheat), both states.

NOT IN THIS FILE (say so wherever it is used): arrivals (tonnes traded). AIAIC holds no arrivals history: the daily
price files carry no arrivals column (one raw 30 Aug 2026 report of about 19 rows, none for Nashik, is on disk and not
ingested). Prices are nominal rupees per quintal (no inflation adjustment).

Outputs, in for_team/aryan/out/pilot_v2/:
    agmarknet_pilot_mh_mp_<first year>_<last year>.csv.gz   the rows (gzip written with mtime 0: same input, same bytes)
    sources.csv                                             source_file_id, file name, its sha256, rows exported
    mandi_identity.csv                                      every (state, published market, district label) -> mandi
    MANIFEST.json                                           counts, period, rules, limits, and the sha256 of each file
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import glob
import gzip
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "price-prep"))
sys.path.insert(0, os.path.join(REPO, "engine"))

from build_seasonal_from_datasets import _RAW, _STATES, _dedup_files, _num, _parse_date  # noqa: E402
from dataset_adapters.agmarknet_adapter import COMMODITY_TO_CROP  # noqa: E402

PILOT_CROPS = ("onion", "soybean", "tur", "wheat")      # AIAIC's crop keys (owner decision 9)
#: The files whose content decides the exported rows (reading, identity, crop vocabulary, places), plus the evidence
#: inventory (the identity reads district places from the evidence tree).
DEPENDS_ON = ("for_team/aryan/export_pilot_prices_for_aryan.py", "badyears-prep/build_price_shock_years.py",
              "price-prep/build_seasonal_from_datasets.py", "engine/dataset_adapters/agmarknet_adapter.py",
              "engine/intelligence/market_regions.py", "engine/historical_evidence/evidence_inventory.json")
OUT = os.path.join(HERE, "out", "pilot_v2")
COLUMNS = ["state", "district", "market", "mandi", "mandi_district", "commodity", "crop", "variety", "grade", "date",
           "min_price", "max_price", "modal_price", "source_file_id", "source_line"]
SOURCE = ('data.gov.in "Variety-wise Daily Market Prices" (Agmarknet, resource 35985678-0d79-46b4-9ed6-6f13308a1d24), '
          "the AIAIC owner's download in price-datasets/")
LICENCE = "Government Open Data Licence - India (GODL-India); attribute data.gov.in / Agmarknet"


def _builder():
    """`badyears-prep/build_price_shock_years.py`, the home of AIAIC's mandi IDENTITY rules (not a package)."""
    path = os.path.join(REPO, "badyears-prep", "build_price_shock_years.py")
    spec = importlib.util.spec_from_file_location("build_price_shock_years", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _rows(path: str, crops: set, from_year: int, counts: collections.Counter):
    """In-scope rows of one file, read as `price-prep/load_price_history_to_db.py` reads them (csv records; the
    header is line 1). Yields (line, state, district, market, commodity, crop, variety, grade, date, min, max,
    modal), for rows whose AIAIC crop is in `crops`."""
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        r = csv.reader(fh)
        hdr = next(r, None)
        low = [h.lower().strip() for h in (hdr or [])]
        need = ("arrival_date", "state", "district", "market", "commodity", "variety", "grade", "min_price",
                "max_price", "modal_price")
        idx = {k: (low.index(k) if k in low else None) for k in need}
        if any(v is None for v in idx.values()):
            counts["files_missing_a_column"] += 1
            return
        wmax = max(idx.values())
        for line, row in enumerate(r, start=2):
            if len(row) <= wmax:
                continue
            st = _STATES.get(row[idx["state"]].strip().lower())
            if st is None:
                continue
            commodity = row[idx["commodity"]].strip()
            crop = COMMODITY_TO_CROP.get(commodity.lower(), commodity.lower())
            if crop not in crops:
                continue
            d = _parse_date(row[idx["arrival_date"]])
            modal = _num(row[idx["modal_price"]])
            if d is None or modal is None:
                counts["in_scope_rows_dropped_bad_date_or_price"] += 1
                continue
            if d.year < from_year:
                continue
            yield (line, st, row[idx["district"]].strip(), row[idx["market"]].strip(), commodity, crop,
                   row[idx["variety"]].strip(), row[idx["grade"]].strip(), d.isoformat(),
                   _num(row[idx["min_price"]]), _num(row[idx["max_price"]]), modal)


def _write_gz_csv(df: pd.DataFrame, path: str) -> None:
    """gzip with mtime 0 and no file name in the header, so the same rows give the same bytes (and sha256)."""
    with open(path, "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz, \
            io.TextIOWrapper(gz, encoding="utf-8", newline="") as text:
        df.to_csv(text, index=False, lineterminator="\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--from-year", type=int, default=2001)
    ap.add_argument("--crops", nargs="+", default=list(PILOT_CROPS),
                    help="AIAIC crop keys (COMMODITY_TO_CROP values, e.g. onion soybean tur wheat gram)")
    args = ap.parse_args(argv)
    files = _dedup_files()
    if not files:
        print(f"No raw price files in {_RAW}")
        return 1
    # The delivered pilot_v2 files (2026-10-03) were made with AIAIC's PROPOSED D-139 fixes applied: the mandi
    # identity as a function (`identities()`) and the 2025-11 tur spelling in COMMODITY_TO_CROP. They were reverted
    # at the owner's request and wait in reports/team_reviews/D139_proposed_aiaic_fixes/. Without them this export
    # would split tur and could not compute `mandi`, so it stops instead of writing a worse file.
    if COMMODITY_TO_CROP.get("arhar(tur/red gram)(whole)") != "tur" or not hasattr(_builder(), "identities"):
        print("This export needs AIAIC's proposed D-139 fixes (reports/team_reviews/D139_proposed_aiaic_fixes/), "
              "which are not applied. The delivered pilot_v2 files stay valid; apply the patch before re-running.")
        return 2
    crops = set(args.crops)
    counts: collections.Counter = collections.Counter()

    parts, used = [], []
    for fid, path in enumerate(files, 1):
        rows = list(_rows(path, crops, args.from_year, counts))
        if not rows:
            continue
        part = pd.DataFrame(rows, columns=["source_line", "state", "district", "market", "commodity", "crop",
                                           "variety", "grade", "date", "min_price", "max_price", "modal_price"])
        part.insert(0, "source_file_id", fid)
        for c in ("state", "district", "market", "commodity", "crop", "variety", "grade", "date"):
            part[c] = part[c].astype("category")
        parts.append(part)
        used.append((fid, path, len(rows)))
        print(f"  {os.path.basename(path)}: {len(rows):,} rows", flush=True)
    if not parts:
        print(f"No rows for {sorted(crops)} from {args.from_year}")
        return 1
    df = pd.concat(parts, ignore_index=True)
    for c in ("state", "district", "market", "commodity", "crop", "variety", "grade", "date"):
        df[c] = df[c].astype(str)            # plain strings: a categorical sorts by its category order, not by value
    found = set(df["crop"].unique())
    if crops - found:
        print(f"Crops with no rows (AIAIC crop keys, e.g. soybean not Soyabean): {sorted(crops - found)}")
        return 1

    # AIAIC's mandi identity, computed over the SAME raw files the bad-years build reads (all crops, both states).
    by = _builder()
    from intelligence.market_regions import display_name
    sums, _n, _dropped = by.load_cells(sorted(glob.glob(os.path.join(by.RAW, "*.csv"))))
    identity, home, info = by.identities(sums)
    keys = df[["state", "market", "district"]].drop_duplicates()
    ident_rows = []
    for state, market, district in keys.itertuples(index=False):
        mandi = identity(state, market, district)
        key_d = home.get((state, mandi))
        rule = ("as_published" if mandi == market else
                "one_name_two_mandis_split_by_district_label" if " [" in mandi else "apmc_rename_folded")
        ident_rows.append({"state": state, "market": market, "district": district, "mandi": mandi,
                           "mandi_district": (display_name(key_d) or key_d) if key_d else "",
                           "rule": rule if key_d else "not_in_identity_build"})
    imap = pd.DataFrame(ident_rows).sort_values(["state", "market", "district"]).reset_index(drop=True)
    df = df.merge(imap[["state", "market", "district", "mandi", "mandi_district"]], on=["state", "market", "district"],
                  how="left", validate="many_to_one")
    df = df.sort_values(["state", "crop", "mandi", "date", "source_file_id", "source_line"]).reset_index(drop=True)

    os.makedirs(OUT, exist_ok=True)
    first, last = df["date"].min(), df["date"].max()
    data_name = f"agmarknet_pilot_mh_mp_{first[:4]}_{last[:4]}.csv.gz"
    data_path = os.path.join(OUT, data_name)
    _write_gz_csv(df[COLUMNS], data_path)
    src = pd.DataFrame([{"source_file_id": fid, "file": os.path.basename(p), "sha256": _sha256(p), "rows_exported": n}
                        for fid, p, n in used])
    src.to_csv(os.path.join(OUT, "sources.csv"), index=False, lineterminator="\n")
    imap.to_csv(os.path.join(OUT, "mandi_identity.csv"), index=False, lineterminator="\n")

    per = (df.groupby(["state", "crop"], observed=True)
           .agg(rows=("modal_price", "size"), first=("date", "min"), last=("date", "max"),
                published_market_names=("market", "nunique"), mandis=("mandi", "nunique"),
                published_commodity_names=("commodity", "nunique")).reset_index())
    spellings = (df.groupby(["crop", "commodity"]).agg(rows=("modal_price", "size"), first=("date", "min"),
                                                       last=("date", "max")).reset_index())
    # PROVENANCE THAT CAN REPRODUCE THE FILE (audit D-139 F6): the commit alone cannot when the code that made the
    # export is not committed yet, so say whether it was, and fingerprint every file the export's rows depend on.
    try:
        head = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=False).stdout.strip() or None
        dirty = subprocess.run(["git", "-C", REPO, "status", "--porcelain", "--", *DEPENDS_ON], capture_output=True,
                               text=True, check=False).stdout.strip()
    except OSError:
        head, dirty = None, "unknown"
    depends = {f: _sha256(os.path.join(REPO, f)) for f in DEPENDS_ON if os.path.exists(os.path.join(REPO, f))}
    manifest = {
        "what": "Official Agmarknet daily mandi prices for the AIAIC pilot crops, Maharashtra and Madhya Pradesh, with "
                "AIAIC's mandi identity, for the aiaic-ml-foundation forecast",
        "source": SOURCE, "licence": LICENCE,
        "period": {"first": str(first), "last": str(last)}, "from_year_requested": args.from_year,
        "crops": sorted(crops), "states": sorted(df["state"].unique().tolist()),
        "rows": int(len(df)),
        "published_market_names": int(df[["state", "market"]].drop_duplicates().shape[0]),
        "mandis": int(df[["state", "mandi"]].drop_duplicates().shape[0]),
        "per_state_crop": [{k: (v if not hasattr(v, "item") else v.item()) for k, v in r.items()}
                           for r in per.astype({"first": str, "last": str}).to_dict("records")],
        "crop_spellings": [{k: (v if not hasattr(v, "item") else v.item()) for k, v in r.items()}
                           for r in spellings.to_dict("records")],
        "columns": {
            "state, district, market, commodity, variety, grade": "exactly as published",
            "crop": "AIAIC's crop for the published commodity (COMMODITY_TO_CROP): key a series on this, not on "
                    "`commodity`",
            "mandi": "AIAIC's identity for the market: key a series on this, not on `market`",
            "mandi_district": "the mandi's district by AIAIC's closed district list",
            "date": "ISO YYYY-MM-DD (published as DD/MM/YYYY)",
            "min_price, max_price, modal_price": "Rs per quintal, nominal, as published (min/max may be empty)",
            "source_file_id, source_line": "where the row was published; sources.csv names the file",
        },
        "crop_identity": "engine/dataset_adapters/agmarknet_adapter.py COMMODITY_TO_CROP (exact, hand-checked pairs; "
                         "the 2025-11 tur spelling added 2026-10-02 on measured price continuity)",
        "identity": {"rules": "badyears-prep/build_price_shock_years.py, IDENTITY (D-116 M1, m12), all raw files",
                     "rule_counts": imap["rule"].value_counts().to_dict(),
                     "build_info": {k: info[k] for k in ("apmc_names_folded", "names_split_into_two_mandis",
                                                         "mandis_placed_by_their_taluka")}},
        "reading_rules": "as price_history: whole duplicate files skipped, DD/MM/YYYY dates, modal price > 0, every "
                         "published line kept (file + line)",
        "raw_files_read": len(files), "raw_files_with_rows": len(used),
        "counts": dict(counts),
        "not_included": ["arrivals: AIAIC holds no arrivals history (the daily price files carry no arrivals column)",
                         "any price after the last raw file AIAIC holds"],
        "limits": ["Coverage is thin in the early years and varies by mandi; check per-mandi history before using a "
                   "year", "Prices are nominal rupees; no inflation adjustment",
                   "The identity rules are AIAIC's judgement, stated in the builder; mandi_identity.csv lists every "
                   "fold so it can be checked",
                   "In a renaming week Agmarknet publishes the SAME quote under both names (old and new mandi or "
                   "crop spelling): take one price per crop, mandi and day (e.g. the median), never a sum or a count "
                   "of rows",
                   "'Red Gram' (MP 2001-2016; MH 1,199 rows 2001-2008) is not included as tur. Botanically red gram "
                   "IS tur, but at the same mandi on the same day the two names' prices are a median 0.99 apart and "
                   "0.70-1.54x (p10-p90, 129,433 MP pairs): two co-reported series, not the identical quotes the "
                   "other spellings show. It waits for an agronomist's or the publisher's answer"],
        "files": {name: {"sha256": _sha256(os.path.join(OUT, name)), "bytes": os.path.getsize(os.path.join(OUT, name))}
                  for name in (data_name, "sources.csv", "mandi_identity.csv")},
        "generator": {"script": "for_team/aryan/export_pilot_prices_for_aryan.py", "aiaic_git_head": head,
                      "uncommitted_changes_in_dependencies": dirty or "none (the commit reproduces this export)",
                      "dependencies_sha256": depends,
                      "generated_at_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")},
    }
    with open(os.path.join(OUT, "MANIFEST.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    print(f"wrote {data_path}: {len(df):,} rows, {manifest['published_market_names']} published market names -> "
          f"{manifest['mandis']} mandis, {first} to {last}")
    print(per.to_string(index=False))
    print("identity rules:", manifest["identity"]["rule_counts"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
