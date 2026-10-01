"""Answer a forecast request from the latest trained bundle, or say plainly why not.

Abstains (answers with `abstain: true` and a reason code, never a guessed range) when:
- `not_trained_for`: the commodity, state or mandi is not in the model's closed lists;
- `horizon_not_trained`: the horizon is not one the model was trained for;
- `no_recent_price`: the mandi has no quote in the 7 days before `as_of`;
- `as_of_outside_history`: `as_of` is later than the model's data plus 7 days (it would forecast from stale prices);
- `no_skill`: in the walk-forward backtest the model did not beat "the price stays where it is" for this crop, state
  and horizon, or had too few test samples to say.
The backtest row is returned in every case, so a caller can show how the model has done.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

import joblib
import numpy as np
import pandas as pd

from src.forecast.series import ASOF_TOLERANCE_DAYS, Series, features_as_of
from src.forecast.train import _categorical, predict_quantiles


class ForecastUnavailable(Exception):
    """No trained forecast bundle is present."""


def _latest(models_dir: Path) -> Path:
    found = sorted(p for p in models_dir.glob("forecast_*.json"))
    if not found:
        raise ForecastUnavailable(f"No trained forecast in {models_dir}. Run: python -m src.forecast.train")
    return found[-1]


@lru_cache(maxsize=1)
def load_bundle(models_dir: str) -> Dict:
    meta_path = _latest(Path(models_dir))
    meta = json.loads(meta_path.read_text())
    bundle = joblib.load(Path(models_dir) / meta["model_file"])
    history = pd.read_csv(Path(models_dir) / meta["history_file"], parse_dates=["date"])
    return {"meta": meta, "bundle": bundle, "history": history}


def _norm(v: Optional[str]) -> str:
    return str(v or "").strip()


def _backtest_row(meta: Dict, commodity: str, state: str, horizon: int) -> Optional[Dict]:
    for g in meta["backtest"]["groups"]:
        if g["commodity"] == commodity and g["state"] == state and g["horizon_days"] == horizon:
            return g
    return None


def forecast(req: Dict, models_dir: str) -> Dict:
    """`req`: commodity, state, market, as_of (YYYY-MM-DD), horizon_days, optional history [{date, modal_price}]."""
    loaded = load_bundle(models_dir)
    meta, bundle = loaded["meta"], loaded["bundle"]
    commodity, state, market = _norm(req.get("commodity")), _norm(req.get("state")), _norm(req.get("market"))
    horizon = int(req.get("horizon_days") or 0)
    as_of = np.datetime64(pd.Timestamp(req.get("as_of")).normalize().date(), "D")
    target = as_of + np.timedelta64(horizon, "D")
    base = {
        "commodity": commodity, "state": state, "market": market, "as_of": str(as_of), "horizon_days": horizon,
        "target_date": str(target), "unit": "INR per quintal (modal price)",
        "model": {"file": meta["model_file"], "trained_at": meta["trained_at"], "trained_through": meta["trained_through"],
                  "data_source": meta["data_source"], "data_hash": meta["data_hash"]},
        "backtest": _backtest_row(meta, commodity, state, horizon),
    }

    def abstain(code: str, why: str) -> Dict:
        return {**base, "abstain": True, "reason_code": code, "reason": why, "p10": None, "p50": None, "p90": None}

    if commodity not in meta["commodities"] or state not in meta["states"] \
            or market not in meta["markets"].get(f"{commodity}|{state}", []):
        return abstain("not_trained_for", "This crop, state and mandi are not in what the model was trained on.")
    if horizon not in meta["horizons_days"]:
        return abstain("horizon_not_trained", f"Horizons trained: {meta['horizons_days']} days.")
    if target <= np.datetime64(meta["trained_through"], "D"):
        # The served models were fitted on every sample up to `trained_through`, so this day's outcome is in their
        # training data. A range here would describe a known price, and it would look far better than a forecast.
        return abstain("in_sample", f"This day's outcome ({target}) is inside the model's training data (to "
                                    f"{meta['trained_through']}), so a range here would not be a forecast.")
    latest = np.datetime64(meta["trained_through"], "D") + np.timedelta64(ASOF_TOLERANCE_DAYS, "D")
    if as_of > latest and not req.get("history"):
        return abstain("as_of_outside_history", f"The model's prices end on {meta['trained_through']}; send `history` "
                                                "to forecast from a later day.")
    bt = base["backtest"]
    if not bt or not bt.get("usable"):
        return abstain("no_skill", "In its backtest the model did not beat 'the price stays where it is' for this crop, "
                                   "state and horizon, or its range held too few of the real outcomes (under 70%), or "
                                   "there were too few test cases to say.")

    if req.get("history"):
        h = pd.DataFrame(req["history"])
        h["date"] = pd.to_datetime(h["date"]).dt.normalize()
        g = h[["date", "modal_price"]]
    else:
        hist = loaded["history"]
        g = hist[(hist["commodity"] == commodity) & (hist["state"] == state) & (hist["market"] == market)]
    g = g[g["date"] <= pd.Timestamp(as_of)]
    if g.empty:
        return abstain("no_recent_price", "No price for this mandi on or before that day.")
    row = features_as_of((commodity, state, market), Series.from_frame(g), as_of, horizon)
    if row is None:
        return abstain("no_recent_price", f"The mandi has no quote in the {ASOF_TOLERANCE_DAYS} days before {as_of}.")
    X = _categorical(pd.DataFrame([row]), bundle["categories"])
    qhat = float((meta.get("range_widening") or {}).get(str(horizon), {}).get("qhat", 0.0))
    raw = predict_quantiles(bundle["models"], X)[0]
    p10, p50, p90 = (round(float(v), 2) for v in (raw[0] - qhat, raw[1], raw[2] + qhat))
    return {**base, "abstain": False, "p10": p10, "p50": p50, "p90": p90,
            "last_price": row["last_price"], "days_since_last_price": int(row["days_since_last"]),
            "range_widened_by": qhat,
            "what_this_is": ("A range for the modal price at this mandi around the target date: p50 is the middle "
                             "estimate. In the backtest the outcome fell inside p10-p90 in the share of cases given as "
                             "backtest.coverage_p10_p90. It is a model estimate, not a promise.")}


def list_meta(models_dir: str) -> Dict:
    meta = load_bundle(models_dir)["meta"]
    keep = ("model_file", "trained_at", "trained_through", "backtest_cutoff", "data_source", "horizons_days",
            "quantiles", "features", "features_never_used", "commodities", "states", "markets", "backtest",
            "range_widening", "target_coverage_p10_p90")
    return {k: meta[k] for k in keep}


def reset_cache() -> None:
    load_bundle.cache_clear()


def usable_groups(models_dir: str) -> List[Dict]:
    return [g for g in load_bundle(models_dir)["meta"]["backtest"]["groups"] if g.get("usable")]
