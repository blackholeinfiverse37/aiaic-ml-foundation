"""Compare YOUR forecast training's backtest with the one AIAIC measured and published in the guide.

Run the official configuration first (guide §3, step 3), then:

    python compare_with_official_backtest.py models/forecast_official/forecast_<stamp>_<hash>.json

It reads `official_backtest_2026-09-28.json` (next to this script) and prints every group row side by side. It exits
with status 0 when every figure agrees within rounding, and 1 otherwise. Nothing is hand-typed: the official file is
the output of the same `train()` with the same data, crops, horizons, holdout (180 days), step (7) and seed (42).
"""
from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
FIELDS = ("n", "mae_p50", "mae_persistence", "skill_vs_persistence", "coverage_p10_p90", "usable")
TOLERANCE = {"n": 0, "mae_p50": 0.5, "mae_persistence": 0.5, "skill_vs_persistence": 0.002, "coverage_p10_p90": 0.002}


def _rows(groups: list) -> dict:
    return {(g["commodity"], g["state"], int(g["horizon_days"])): g for g in groups}


def compare(mine: dict, official: dict) -> list[str]:
    """The differences, one line each; empty when the two agree within rounding."""
    out = []
    for key in ("trained_through", "backtest_cutoff"):
        if mine.get(key) != official.get(key):
            out.append(f"{key}: yours {mine.get(key)} vs official {official.get(key)}")
    theirs, ours = _rows(official["groups"]), _rows(mine["backtest"]["groups"])
    for k in sorted(set(theirs) | set(ours)):
        a, b = ours.get(k), theirs.get(k)
        if a is None or b is None:
            out.append(f"{k}: only in {'the official run' if a is None else 'yours'}")
            continue
        for f in FIELDS:
            x, y = a.get(f), b.get(f)
            same = x == y if f == "usable" else (x is not None and y is not None and abs(x - y) <= TOLERANCE[f])
            if not same:
                out.append(f"{k} {f}: yours {x} vs official {y}")
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    mine = json.loads(pathlib.Path(argv[1]).read_text(encoding="utf-8"))
    official = json.loads((HERE / "official_backtest_2026-09-28.json").read_text(encoding="utf-8"))
    diffs = compare(mine, official)
    print(f"{'Crop':10} {'State':16} {'Days':>4} {'Cases':>6} {'Skill (yours)':>14} {'Skill (official)':>17} {'Shown?':>7}")
    theirs = _rows(official["groups"])
    for k, g in sorted(_rows(mine["backtest"]["groups"]).items()):
        o = theirs.get(k, {})
        print(f"{k[0]:10} {k[1]:16} {k[2]:>4} {g['n']:>6} {g['skill_vs_persistence']:>+14.4f} "
              f"{o.get('skill_vs_persistence', float('nan')):>+17.4f} {('yes' if g['usable'] else 'no'):>7}")
    print("\nAGREES with the official backtest." if not diffs else "\nDIFFERS:\n  " + "\n  ".join(diffs))
    return 0 if not diffs else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
