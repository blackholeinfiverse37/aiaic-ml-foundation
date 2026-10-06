"""Test 3 / Task C experiments (v2).   Run:  python -m scripts.run_experiments

Every variant uses the SAME samples, the SAME walk-forward split (horizons 7/14/30, holdout 90, step 7, seed 42)
and the SAME calibration/scored halves as the trained baseline. The control must reproduce that baseline.
Per-crop variant choice (exp6) is made on the CALIBRATION half only; the scored half is only reported.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from pathlib import Path
from typing import Dict, List

os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(os.cpu_count() or 4))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd

from src.forecast.series import (CATEGORICAL_FEATURES, KEYS, NUMERIC_FEATURES, Series, daily_series,
                                 training_samples)
from src.forecast.train import QUANTILES, _fit, backtest_table, conformal_widening, walk_forward_split, widen

logging.basicConfig(level="INFO", format="%(asctime)s | %(levelname)s | %(message)s", stream=sys.stdout)
logger = logging.getLogger("experiments")

INPUT = "out/pilot_v2/agmarknet_pilot_mh_mp_2001_2026.csv.gz"
MSP_FILE = "out/pilot_v2/msp_pilot_crops.csv"
BASELINE_DIR = Path("models/forecast_v2")
CROPS = ["onion", "soybean", "tur", "wheat"]
HORIZONS = [7, 14, 30]          # same as the trained baseline, so the split is identical
SHOW = (7, 30)                  # the 16 groups Hemanth asked for
SEED, HOLDOUT_DAYS, STEP_DAYS = 42, 90, 7
OUT_DIR = Path("experiments")
OUT_DIR.mkdir(exist_ok=True)
TRIM_DAYS = int(os.environ.get("TRIM_DAYS", "0"))   # >0: drop the last N days, so an EARLIER fold is scored
_tag = (f"_trim{TRIM_DAYS}" if TRIM_DAYS else "") + ("_subset" if os.environ.get("ONLY") else "")
LOG_PATH = OUT_DIR / f"experiment_log{_tag}.json"
CACHE = OUT_DIR / "samples_cache_h7_14_30.pkl"   # delete this file if the dataset ever changes
ST = {"Madhya Pradesh": "MP", "Maharashtra": "MH"}
MSP_FEATS = NUMERIC_FEATURES + ["msp_gap_pct"]
RESULTS: Dict[str, dict] = {}


# ----------------------------------------------------------------------------- data
def load_data() -> pd.DataFrame:
    logger.info("Loading %s", INPUT)
    df = pd.read_csv(INPUT, usecols=["state", "date", "modal_price", "mandi", "crop"])
    df = df.rename(columns={"mandi": "market", "crop": "commodity"})
    return df[df["commodity"].isin(CROPS)]


def build_samples(daily: pd.DataFrame) -> pd.DataFrame:
    if CACHE.exists():
        logger.info("Loading cached samples %s", CACHE)
        return pd.read_pickle(CACHE)
    logger.info("Building samples (slow, done once)")
    s = training_samples(daily, HORIZONS, step_days=STEP_DAYS)
    s.to_pickle(CACHE)
    return s


def make_split(samples: pd.DataFrame):
    if TRIM_DAYS:
        samples = samples[samples["target_date"] <= samples["target_date"].max() - pd.Timedelta(days=TRIM_DAYS)]
    train_s, test_s, _ = walk_forward_split(samples, HOLDOUT_DAYS)
    test_s = test_s.sort_values("as_of").reset_index(drop=True)
    mid = test_s["as_of"].iloc[len(test_s) // 2]
    cal = test_s[test_s["as_of"] < mid].reset_index(drop=True)
    ev = test_s[test_s["as_of"] >= mid].reset_index(drop=True)
    return train_s, cal, ev


def _season(crop: str, ts: pd.Timestamp) -> str:
    # wheat: Rabi Marketing Season starts 1 Apr. soybean/tur: Kharif Marketing Season starts 1 Oct.
    first_month = 4 if crop == "wheat" else 10
    y = ts.year if ts.month >= first_month else ts.year - 1
    return f"{y}-{(y + 1) % 100:02d}"


def add_msp(samples: pd.DataFrame) -> pd.DataFrame:
    msp = pd.read_csv(MSP_FILE)
    msp = msp[msp["msp_rs_per_quintal"].notna()]
    lookup: Dict[tuple, float] = {}
    for crop, yr, val in zip(msp["crop"], msp["marketing_year"], msp["msp_rs_per_quintal"]):
        lookup.setdefault((str(crop).strip().lower(), str(yr).strip()), float(val))
    gap = []
    for crop, ts, last in zip(samples["commodity"], samples["as_of"], samples["last_price"]):
        m = lookup.get((crop, _season(crop, ts))) if crop != "onion" else None
        gap.append(100.0 * (last / m - 1.0) if m else np.nan)
    out = samples.assign(msp_gap_pct=gap)
    for crop, g in out.groupby("commodity"):
        logger.info("MSP gap available for %-8s %5.1f%% of samples", crop, 100 * g["msp_gap_pct"].notna().mean())
    return out


# ----------------------------------------------------------------------------- model helpers
def make_X(frame: pd.DataFrame, feats_num: List[str], categories: Dict[str, List[str]]) -> pd.DataFrame:
    X = frame[CATEGORICAL_FEATURES + feats_num].copy()
    for c in CATEGORICAL_FEATURES:
        X[c] = pd.Categorical(X[c].astype(str), categories=categories[c])
    for c in feats_num:
        X[c] = pd.to_numeric(X[c], errors="coerce").astype(float)
    return X


def predict_frame(models, frame, feats_num, categories, log_target):
    if len(frame) == 0:
        return frame.assign(r10=np.nan, r50=np.nan, r90=np.nan)
    raw = np.column_stack([models[q].predict(make_X(frame, feats_num, categories)) for q in QUANTILES])
    if log_target:
        raw = np.exp(np.clip(raw, -2.0, 2.0)) * frame["last_price"].to_numpy(float)[:, None]
    raw = np.sort(raw, axis=1)
    return frame.assign(r10=raw[:, 0], r50=raw[:, 1], r90=raw[:, 2])


def finish(name: str, cal_all: pd.DataFrame, ev_all: pd.DataFrame) -> dict:
    cal_all = cal_all.dropna(subset=["r10"]).reset_index(drop=True)
    ev_all = ev_all.dropna(subset=["r10"]).reset_index(drop=True)
    raw_q = ev_all[["r10", "r50", "r90"]].to_numpy()
    widening = conformal_widening(cal_all, cal_all[["r10", "r50", "r90"]].to_numpy())
    q = widen(raw_q, ev_all["horizon_days"].to_numpy(), widening)
    bt = backtest_table(ev_all, q, raw=raw_q)
    ev_out = ev_all.assign(p10=q[:, 0], p50=q[:, 1], p90=q[:, 2])
    return {"name": name, "bt": bt, "ev": ev_out, "cal": cal_all, "widening": widening}


def run_variant(name, split, categories, feats_num=None, log_target=False, per_crop=False, train_from=None):
    feats_num = list(feats_num or NUMERIC_FEATURES)
    train_s, cal, ev = split
    if train_from:
        train_s = train_s[train_s["as_of"] >= pd.Timestamp(train_from)]
    crops = sorted(train_s["commodity"].unique()) if per_crop else [None]
    cal_parts, ev_parts = [], []
    for crop in crops:
        tr = train_s if crop is None else train_s[train_s["commodity"] == crop]
        ca = cal if crop is None else cal[cal["commodity"] == crop]
        e = ev if crop is None else ev[ev["commodity"] == crop]
        if len(tr) < 200:
            logger.warning("%s: skipping %s, only %d training rows", name, crop, len(tr))
            continue
        y = np.log(tr["target"] / tr["last_price"]) if log_target else tr["target"]
        Xtr = make_X(tr, feats_num, categories)
        models = {q: _fit(Xtr, y, q, SEED) for q in QUANTILES}
        cal_parts.append(predict_frame(models, ca, feats_num, categories, log_target))
        ev_parts.append(predict_frame(models, e, feats_num, categories, log_target))
    return finish(name, pd.concat(cal_parts, ignore_index=True), pd.concat(ev_parts, ignore_index=True))


# ----------------------------------------------------------------------------- reporting
def _f(v, spec=".4f"):
    return "   n/a" if v is None else format(v, spec)


def print_table(title: str, bt: dict) -> None:
    print("\n" + "=" * 78 + f"\n  {title}\n" + "=" * 78)
    print(f"{'Crop':<9}{'State':<7}{'Days':>5}{'n':>7}{'MAE p50':>10}{'MAE pers':>10}{'Skill':>9}{'Cov':>8}{'Usable':>8}")
    rows = sorted([g for g in bt["groups"] if g["horizon_days"] in SHOW],
                  key=lambda g: (g["commodity"], g["state"], g["horizon_days"]))
    for g in rows:
        print(f"{g['commodity']:<9}{ST.get(g['state'], g['state']):<7}{g['horizon_days']:>5}{g['n']:>7}"
              f"{g['mae_p50']:>10.1f}{g['mae_persistence']:>10.1f}{_f(g['skill_vs_persistence']):>9}"
              f"{g['coverage_p10_p90']:>8.3f}{'YES' if g['usable'] else 'no':>8}")
    print(f"Usable: {sum(1 for g in rows if g['usable'])}/16")


def summarize(res: dict) -> dict:
    groups = [g for g in res["bt"]["groups"] if g["horizon_days"] in SHOW]
    d = res["ev"][res["ev"]["horizon_days"].isin(SHOW)]
    skill = 1 - (d["p50"] - d["target"]).abs().mean() / (d["last_price"] - d["target"]).abs().mean()
    return {"skill_7_30": float(skill), "usable": sum(1 for g in groups if g["usable"]),
            "soy_usable": sum(1 for g in groups if g["commodity"] == "soybean" and g["usable"]),
            "abstained": [f"{g['commodity']}/{ST.get(g['state'], g['state'])}/{g['horizon_days']}d"
                          for g in groups if not g["usable"]]}


def save(name: str, res: dict, extra: dict = None) -> None:
    RESULTS[name] = {"overall": res["bt"]["overall"], "groups": res["bt"]["groups"],
                     "range_widening": res.get("widening"), "summary": summarize(res), **(extra or {})}
    LOG_PATH.write_text(json.dumps(RESULTS, indent=2, default=str))


def safe(name: str, fn):
    try:
        return fn()
    except Exception:
        logger.error("%s FAILED:\n%s", name, traceback.format_exc())
        return None


def check_control(res: dict) -> None:
    files = sorted(BASELINE_DIR.glob("forecast_*.json"))
    if not files:
        logger.warning("CONTROL CHECK: no trained model in %s to compare with", BASELINE_DIR)
        return
    ref = json.loads(files[-1].read_text())["backtest"]["overall"]
    mine = res["bt"]["overall"]
    ok = ref["n"] == mine["n"] and abs(ref["skill_vs_persistence"] - mine["skill_vs_persistence"]) < 0.002
    logger.info("CONTROL CHECK: trained model n=%s skill=%s | control n=%s skill=%s -> %s", ref["n"],
                ref["skill_vs_persistence"], mine["n"], mine["skill_vs_persistence"],
                "SAME SPLIT, REPRODUCED" if ok else "MISMATCH - results below are NOT comparable to the trained model")


# ----------------------------------------------------------------------------- experiment 3: stronger baselines
def exp3_baselines(control: dict, daily: pd.DataFrame) -> List[dict]:
    series = {k: Series.from_frame(g) for k, g in daily.groupby(KEYS, observed=True, sort=False)}
    ev = control["ev"]
    ev = ev[ev["horizon_days"].isin(SHOW)].reset_index(drop=True)
    seasonal, mean4 = [], []
    for c, st, m, as_of, tdate, last in zip(ev["commodity"], ev["state"], ev["market"], ev["as_of"],
                                             ev["target_date"], ev["last_price"]):
        s = series.get((c, st, m))
        if s is None:
            seasonal.append(np.nan)
            mean4.append(np.nan)
            continue
        a, t = np.datetime64(as_of.date(), "D"), np.datetime64(tdate.date(), "D")
        now_ly = s.asof(a - np.timedelta64(364, "D"))[0]       # price at this time last year
        tgt_ly = s.asof(t - np.timedelta64(364, "D"))[0]       # price at the target date last year
        seasonal.append(last * tgt_ly / now_ly if now_ly and tgt_ly else np.nan)   # last year's move, applied now
        w = s.window(a, 28)
        mean4.append(float(w.mean()) if len(w) else np.nan)
    d = ev.assign(seasonal=seasonal, mean4=mean4).dropna(subset=["seasonal", "mean4"])
    d = d.assign(e_model=(d["p50"] - d["target"]).abs(), e_pers=(d["last_price"] - d["target"]).abs(),
                 e_seas=(d["seasonal"] - d["target"]).abs(), e_4wk=(d["mean4"] - d["target"]).abs())
    rows = []
    for (c, st, h), g in d.groupby(["commodity", "state", "horizon_days"]):
        mm = g[["e_model", "e_pers", "e_seas", "e_4wk"]].mean()
        best = min(mm["e_pers"], mm["e_seas"], mm["e_4wk"])
        rows.append({"commodity": c, "state": st, "horizon_days": int(h), "n": len(g),
                     "mae_model": mm["e_model"], "mae_persistence": mm["e_pers"], "mae_seasonal": mm["e_seas"],
                     "mae_4wk_mean": mm["e_4wk"],
                     "skill_vs_persistence": 1 - mm["e_model"] / mm["e_pers"],
                     "skill_vs_seasonal": 1 - mm["e_model"] / mm["e_seas"],
                     "skill_vs_4wk_mean": 1 - mm["e_model"] / mm["e_4wk"],
                     "skill_vs_best_baseline": 1 - mm["e_model"] / best})
    print("\n" + "=" * 98 + "\n  EXP 3: model (control) against stronger baselines, same rows for all\n" + "=" * 98)
    print(f"{'Crop':<9}{'State':<7}{'Days':>5}{'n':>7}{'vs pers':>10}{'vs seas':>10}{'vs 4wk':>10}{'vs BEST':>10}"
          f"{'MAE mdl':>10}{'MAE pers':>10}{'MAE seas':>10}{'MAE 4wk':>10}")
    for r in rows:
        print(f"{r['commodity']:<9}{ST.get(r['state'], r['state']):<7}{r['horizon_days']:>5}{r['n']:>7}"
              f"{r['skill_vs_persistence']:>10.4f}{r['skill_vs_seasonal']:>10.4f}{r['skill_vs_4wk_mean']:>10.4f}"
              f"{r['skill_vs_best_baseline']:>10.4f}{r['mae_model']:>10.1f}{r['mae_persistence']:>10.1f}"
              f"{r['mae_seasonal']:>10.1f}{r['mae_4wk_mean']:>10.1f}")
    return rows


# ----------------------------------------------------------------------------- experiment 6: choose per crop on CALIBRATION half
def cal_skill(cal: pd.DataFrame, crop: str) -> float:
    d = cal[(cal["commodity"] == crop) & cal["horizon_days"].isin(SHOW)]
    if len(d) < 50:
        return -np.inf
    den = (d["last_price"] - d["target"]).abs().mean()
    return float(1 - (d["r50"] - d["target"]).abs().mean() / den) if den > 0 else -np.inf


def exp6_select(runs: Dict[str, dict]):
    chosen, parts = {}, []
    for crop in CROPS:
        scores = {n: cal_skill(r["cal"], crop) for n, r in runs.items()}
        best = max(scores, key=scores.get)
        if not np.isfinite(scores[best]) and "control_pooled_level" in runs:
            best = "control_pooled_level"
        chosen[crop] = {"variant": best, "calibration_skill": {k: round(v, 4) for k, v in scores.items()}}
        ev = runs[best]["ev"]
        parts.append(ev[ev["commodity"] == crop])
    ev_all = pd.concat(parts, ignore_index=True)
    bt = backtest_table(ev_all, ev_all[["p10", "p50", "p90"]].to_numpy())
    return {"name": "exp6_cal_selected", "bt": bt, "ev": ev_all, "cal": None, "widening": None}, chosen


# ----------------------------------------------------------------------------- main
def main() -> None:
    df = load_data()
    daily = daily_series(df)
    categories = {c: sorted(daily[c].astype(str).unique().tolist()) for c in CATEGORICAL_FEATURES}
    samples = build_samples(daily)
    msp_ok = False
    try:
        samples = add_msp(samples)
        msp_ok = True
    except Exception:
        logger.error("MSP join FAILED, MSP variants skipped:\n%s", traceback.format_exc())
    split = make_split(samples)
    logger.info("rows: train=%d calibration=%d scored=%d", len(split[0]), len(split[1]), len(split[2]))

    specs = [("control_pooled_level", {}),
             ("exp1_pooled_log_change", {"log_target": True}),
             ("exp2_per_crop_level", {"per_crop": True}),
             ("exp2b_per_crop_log_change", {"per_crop": True, "log_target": True}),
             ("exp5_history_from_2016", {"train_from": "2016-01-01"})]
    if msp_ok:
        specs += [("exp4_msp_level", {"feats_num": MSP_FEATS}),
                  ("exp4b_msp_log_change", {"feats_num": MSP_FEATS, "log_target": True})]
        only = os.environ.get("ONLY")

    if only:
        keep = set(only.split(","))
        specs = [s for s in specs if s[0] in keep]    

    runs: Dict[str, dict] = {}
    for name, kw in specs:
        logger.info("running %s", name)
        res = safe(name, lambda name=name, kw=kw: run_variant(name, split, categories, **kw))
        if res is None:
            continue
        runs[name] = res
        title = {"control_pooled_level": "CONTROL = trained baseline re-run on this split (also EXP 5a: history from 2001)"}.get(name, name)
        print_table(title, res["bt"])
        save(name, res)
        if name == "control_pooled_level":
            check_control(res)

    if "control_pooled_level" in runs:
        rows = safe("exp3", lambda: exp3_baselines(runs["control_pooled_level"], daily))
        if rows is not None:
            RESULTS["exp3_stronger_baselines"] = rows
            LOG_PATH.write_text(json.dumps(RESULTS, indent=2, default=str))
    if "exp4_msp_level" in runs:
        print("\n(Next table: the same comparison for the exp4_msp_level model.)")
        rows4 = safe("exp3 on exp4", lambda: exp3_baselines(runs["exp4_msp_level"], daily))
        if rows4 is not None:
            RESULTS["exp3_stronger_baselines_exp4_model"] = rows4
            LOG_PATH.write_text(json.dumps(RESULTS, indent=2, default=str))        

    if runs:
        out = safe("exp6", lambda: exp6_select(runs))
        if out is not None:
            res6, chosen = out
            runs["exp6_cal_selected"] = res6
            print_table("EXP 6: per-crop variant chosen on the CALIBRATION half, scored on the untouched half", res6["bt"])
            print("\nChosen per crop (calibration-half skill, 7+30 days):")
            for crop, info in chosen.items():
                print(f"  {crop:<8} -> {info['variant']:<28} {info['calibration_skill']}")
            save("exp6_cal_selected", res6, {"chosen": chosen})

    print("\n" + "=" * 78 + "\n  SUMMARY (scored half, 7 and 30 days only)\n" + "=" * 78)
    base = RESULTS.get("control_pooled_level", {}).get("summary")
    print(f"{'Variant':<30}{'Skill':>9}{'Usable':>9}{'Soy ok':>8}  Adopt?  Abstained groups")
    for name, res in runs.items():
        s = summarize(res)
        adopt = "-" if name == "control_pooled_level" or not base else (
            "YES" if s["skill_7_30"] > base["skill_7_30"] and s["usable"] >= base["usable"] else "no")
        print(f"{name:<30}{s['skill_7_30']:>9.4f}{str(s['usable']) + '/16':>9}{str(s['soy_usable']) + '/4':>8}  "
              f"{adopt:<7} {', '.join(s['abstained']) or 'none'}")
    print("\nRule: adopt only if the scored-half skill improves AND usable groups do not drop. "
          "Any soybean group listed as abstained stays abstained (never shown).")
    print(f"\nFull log: {LOG_PATH}")


if __name__ == "__main__":
    main()