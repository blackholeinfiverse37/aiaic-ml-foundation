"""Daily price series per mandi, and the features known on a given day.

A "series" is one (commodity, state, market): one modal price per date (the median when a mandi reports a crop
more than once on a day, e.g. several varieties). Everything here works on DATES, never on row positions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

KEYS = ["commodity", "state", "market"]

#: How far back a "price N days ago" may reach for the last quote on or before that day. Mandis do not report
#: every day (holidays, no arrivals); beyond this the feature is missing, not borrowed from further back.
ASOF_TOLERANCE_DAYS = 7

#: A target (the price `horizon` days ahead) counts only if the mandi quoted within this many days AFTER the target
#: date; otherwise that training sample is dropped rather than paired with a far-off price.
TARGET_TOLERANCE_DAYS = 3

LAG_DAYS = (7, 14, 30)
WINDOW_DAYS = 30

#: Features the model reads. None of them is dated after `as_of`, and none is a min/max price.
NUMERIC_FEATURES = [
    "last_price", "days_since_last", "price_lag_7", "price_lag_14", "price_lag_30",
    "roll_mean_30", "roll_std_30", "roll_n_30", "change_7_pct", "change_30_pct",
    "horizon_days", "target_month_sin", "target_month_cos",
]
CATEGORICAL_FEATURES = ["commodity", "state", "market"]
FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES


def daily_series(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (commodity, state, market, date): the median modal price that day. Input columns: commodity,
    state, market, date, modal_price (any others are ignored). Rows without a market are dropped: a state-wide
    'series' mixes mandis hundreds of km apart."""
    need = {"commodity", "state", "market", "date", "modal_price"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(f"daily_series needs columns {sorted(missing)}")
    d = df[list(need)].copy()
    d = d.dropna(subset=["market", "modal_price", "date"])
    d["date"] = pd.to_datetime(d["date"]).dt.normalize()
    for k in KEYS:
        d[k] = d[k].astype(str).str.strip()
    d = d[d["modal_price"] > 0]
    out = (d.groupby(KEYS + ["date"], observed=True)["modal_price"].median().reset_index()
           .sort_values(KEYS + ["date"]).reset_index(drop=True))
    return out


@dataclass(frozen=True)
class Series:
    """One mandi's dated prices, for as-of lookups."""
    dates: np.ndarray    # datetime64[D], sorted ascending
    prices: np.ndarray   # float

    @classmethod
    def from_frame(cls, g: pd.DataFrame) -> "Series":
        g = g.sort_values("date")
        return cls(g["date"].values.astype("datetime64[D]"), g["modal_price"].to_numpy(dtype=float))

    def asof(self, day: np.datetime64, tolerance_days: int = ASOF_TOLERANCE_DAYS) -> Tuple[Optional[float], Optional[int]]:
        """(price, age in days) of the last quote on or before `day`, within the tolerance; (None, None) otherwise."""
        i = int(np.searchsorted(self.dates, day, side="right")) - 1
        if i < 0:
            return None, None
        age = int((day - self.dates[i]).astype(int))
        if age > tolerance_days:
            return None, None
        return float(self.prices[i]), age

    def first_on_or_after(self, day: np.datetime64, tolerance_days: int = TARGET_TOLERANCE_DAYS) -> Optional[float]:
        i = int(np.searchsorted(self.dates, day, side="left"))
        if i >= len(self.dates):
            return None
        if int((self.dates[i] - day).astype(int)) > tolerance_days:
            return None
        return float(self.prices[i])

    def window(self, end: np.datetime64, days: int) -> np.ndarray:
        """Prices dated in (end - days, end]: strictly the past, the end day included."""
        lo = int(np.searchsorted(self.dates, end - np.timedelta64(days, "D"), side="right"))
        hi = int(np.searchsorted(self.dates, end, side="right"))
        return self.prices[lo:hi]


def features_as_of(key: Tuple[str, str, str], s: Series, as_of: np.datetime64, horizon_days: int) -> Optional[Dict]:
    """The feature row for asking, on `as_of`, about `as_of + horizon_days`. None when the mandi has no quote in the
    last ASOF_TOLERANCE_DAYS days (nothing current to forecast from)."""
    last, age = s.asof(as_of)
    if last is None:
        return None
    lag = {k: s.asof(as_of - np.timedelta64(k, "D"))[0] for k in LAG_DAYS}
    win = s.window(as_of, WINDOW_DAYS)
    target_day = pd.Timestamp(as_of + np.timedelta64(horizon_days, "D"))
    month = target_day.month
    row = {
        "commodity": key[0], "state": key[1], "market": key[2],
        "last_price": last, "days_since_last": float(age),
        "price_lag_7": lag[7], "price_lag_14": lag[14], "price_lag_30": lag[30],
        "roll_mean_30": float(win.mean()) if len(win) else None,
        "roll_std_30": float(win.std(ddof=1)) if len(win) > 1 else None,
        "roll_n_30": float(len(win)),
        "change_7_pct": (100.0 * (last / lag[7] - 1.0)) if lag[7] else None,
        "change_30_pct": (100.0 * (last / lag[30] - 1.0)) if lag[30] else None,
        "horizon_days": float(horizon_days),
        "target_month_sin": math.sin(2 * math.pi * month / 12.0),
        "target_month_cos": math.cos(2 * math.pi * month / 12.0),
    }
    return row


def training_samples(daily: pd.DataFrame, horizons: Iterable[int], step_days: int = 7) -> pd.DataFrame:
    """(features, target) pairs: for each mandi, an `as_of` every `step_days` days, and for each horizon the first
    quote within TARGET_TOLERANCE_DAYS after `as_of + horizon`. Columns: FEATURES + as_of, target_date, target."""
    rows: List[Dict] = []
    for key, g in daily.groupby(KEYS, observed=True, sort=True):
        s = Series.from_frame(g)
        if len(s.dates) < 10:
            continue
        start, end = s.dates[0] + np.timedelta64(WINDOW_DAYS, "D"), s.dates[-1]
        for as_of in np.arange(start, end + np.timedelta64(1, "D"), np.timedelta64(step_days, "D")):
            for h in horizons:
                target_day = as_of + np.timedelta64(h, "D")
                y = s.first_on_or_after(target_day)
                if y is None:
                    continue
                f = features_as_of(key, s, as_of, h)
                if f is None:
                    continue
                f.update({"as_of": pd.Timestamp(as_of), "target_date": pd.Timestamp(target_day), "target": y})
                rows.append(f)
    return pd.DataFrame(rows)
