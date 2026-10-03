"""Export the Minimum Support Prices AIAIC holds for the pilot crops, for Aryan's forecast (2026-10-02).

    python for_team/aryan/export_msp_for_aryan.py

SOURCE. CACP Minimum Support Prices as AIAIC ingested them, both via data.gov.in (Government Open Data Licence -
India): `msp_cacp` ("MSP Fixed from 2018-19 to 2023-24") and `cacp_msp_current` ("Commodity-wise MSP Trend",
2025-26 and 2026-27). Read from AIAIC's committed evidence (`engine/historical_evidence/evidence/`), not re-typed.

WHAT IT IS. A government floor announced per marketing year, not a price and not a forecast. Onion has no MSP.

SEASONS. Every row is labelled by the MARKETING SEASON its MSP applies to (kharif crops: the crop year; wheat: the Rabi
Marketing Season, one year after the crop year: `msp_cacp`'s wheat "2023-24" column, Rs 2,275, is RMS 2024-25, audit
D-139 F2). The delivered file was made with AIAIC's proposed relabelling applied; it was then reverted in AIAIC at the
owner's request, so a re-run stops until the proposal is applied.

GAPS, computed into the manifest: for soybean and tur, 2024-25 and 2026-27 (the 2026-27 kharif MSPs are not in the
file AIAIC holds) and everything before 2018-19; for wheat, everything before 2019-20.

Outputs, in for_team/aryan/out/pilot_v2/: msp_pilot_crops.csv, MSP_MANIFEST.json
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
EVIDENCE = os.path.join(REPO, "engine", "historical_evidence", "evidence")
OUT = os.path.join(HERE, "out", "pilot_v2")
FILES = ("msp_cacp.json", "cacp_msp_current.json")

#: The labels these two files use for the pilot crops -> AIAIC's crop keys. Closed and exact: a label not listed is
#: not exported, and the manifest names it.
CROP_OF_LABEL = {"wheat": "wheat", "tur (arhar)": "tur", "tur": "tur", "soyabeen (yellow)": "soybean",
                 "soybean": "soybean"}
PILOT = ("soybean", "tur", "wheat")
YEARS_WANTED = [f"{y}-{str(y + 1)[2:]}" for y in range(2016, 2027)]


def main() -> int:
    # The delivered msp_pilot_crops.csv (2026-10-03) was made from msp_cacp evidence relabelled by AIAIC's PROPOSED
    # D-139 fix (rabi crops by marketing season; reverted at the owner's request, saved in
    # reports/team_reviews/D139_proposed_aiaic_fixes/). Without it, wheat would come out one season early again.
    with open(os.path.join(EVIDENCE, "msp_cacp.json"), encoding="utf-8") as fh:
        if not any("crop_year" in (r.get("dimensions") or {}) for r in json.load(fh)):
            print("msp_cacp still labels rabi crops by crop year: apply the proposed D-139 fix "
                  "(reports/team_reviews/D139_proposed_aiaic_fixes/) before re-running. The delivered file stays valid.")
            return 2
    rows, unmapped = [], set()
    for name in FILES:
        with open(os.path.join(EVIDENCE, name), encoding="utf-8") as fh:
            for r in json.load(fh):
                s = r.get("signal") or {}
                label = (s.get("crop") or "").strip().lower()
                crop = CROP_OF_LABEL.get(label)
                if crop is None:
                    unmapped.add(label)
                    continue
                if crop not in PILOT or s.get("msp") is None:
                    continue
                rows.append({"crop": crop, "marketing_year": s.get("year"), "msp_rs_per_quintal": s["msp"],
                             "variety": s.get("variety") or "", "published_label": (r.get("dimensions") or {}).get(
                                 "commodity_raw") or s.get("crop"), "aiaic_source_id": r.get("source_id"),
                             "source": s.get("source") or ((r.get("provenance") or {}).get("source_url") or "")})
    rows.sort(key=lambda x: (x["crop"], x["marketing_year"], x["aiaic_source_id"]))
    seen = {}
    for x in rows:                      # one value per crop and year; two files disagreeing would be a defect
        k = (x["crop"], x["marketing_year"])
        if k in seen and seen[k] != x["msp_rs_per_quintal"]:
            print(f"the two MSP files disagree for {k}: {seen[k]} vs {x['msp_rs_per_quintal']}")
            return 1
        seen[k] = x["msp_rs_per_quintal"]
    rows = [x for i, x in enumerate(rows) if i == 0 or (x["crop"], x["marketing_year"]) !=
            (rows[i - 1]["crop"], rows[i - 1]["marketing_year"])]
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "msp_pilot_crops.csv")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    held = {c: sorted(x["marketing_year"] for x in rows if x["crop"] == c) for c in PILOT}
    with open(path, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    manifest = {
        "what": "CACP Minimum Support Prices AIAIC holds for the pilot crops (Rs per quintal, per marketing year)",
        "sources": ["data.gov.in 'MSP Fixed from 2018-19 to 2023-24' (AIAIC source msp_cacp)",
                    "data.gov.in 'Commodity-wise MSP Trend' 2025-26 / 2026-27 (AIAIC source cacp_msp_current)"],
        "licence": "Government Open Data Licence - India (GODL-India); attribute data.gov.in / CACP",
        "held_years": held,
        "missing_years": {c: [y for y in YEARS_WANTED if y not in held[c]] for c in PILOT},
        "not_applicable": {"onion": "no MSP is announced for onion"},
        "labels_not_exported": sorted(unmapped),
        "meaning": "a government floor for a MARKETING SEASON (kharif seasons open in October, the Rabi Marketing "
                   "Season in April), not a market price and not a forecast; join it to a price date by the season "
                   "that date falls in. Wheat rows are Rabi Marketing Seasons (msp_cacp relabelled at its adapter, "
                   "2026-10-03; its 'crop year 2023-24' column, Rs 2,275, is RMS 2024-25)",
        "file": {"name": "msp_pilot_crops.csv", "rows": len(rows), "sha256": digest},
    }
    with open(os.path.join(OUT, "MSP_MANIFEST.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, indent=1)
        fh.write("\n")
    print(json.dumps({k: manifest[k] for k in ("held_years", "missing_years")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
