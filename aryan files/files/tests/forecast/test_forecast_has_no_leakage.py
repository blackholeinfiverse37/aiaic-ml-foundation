"""The forecast can only see what was known on the day it is asked (the defects this package exists to remove).

`/v1/predict` reads the same day's min and max price, and its "lags" shift ROWS across every mandi in a state, so
its R² of 0.99 describes a day already known. These tests fail if either comes back into the forecast.
"""

import numpy as np
import pandas as pd

from src.forecast.series import FEATURES, Series, daily_series, features_as_of, training_samples
from src.forecast.train import walk_forward_split


def test_no_same_day_range_or_future_column_is_a_feature():
    for banned in ("min_price", "max_price", "modal_price", "target", "target_date"):
        assert banned not in FEATURES


def test_a_feature_does_not_change_when_every_later_price_changes(synthetic):
    daily = daily_series(synthetic)
    g = daily[(daily.commodity == "Onion") & (daily.market == "Lasalgaon")]
    as_of = np.datetime64("2024-03-15", "D")
    before = features_as_of(("Onion", "Maharashtra", "Lasalgaon"), Series.from_frame(g), as_of, 30)
    future = g.copy()
    future.loc[future["date"] > pd.Timestamp(as_of), "modal_price"] *= 50      # the future changes completely
    after = features_as_of(("Onion", "Maharashtra", "Lasalgaon"), Series.from_frame(future), as_of, 30)
    assert before == after


def test_a_lag_is_the_same_mandi_a_week_earlier_never_another_mandi_that_day():
    rows = []
    for d in pd.date_range("2024-01-01", "2024-02-29"):
        rows.append({"commodity": "Onion", "state": "Maharashtra", "market": "A", "date": d, "modal_price": 1000.0 + d.day})
        rows.append({"commodity": "Onion", "state": "Maharashtra", "market": "B", "date": d, "modal_price": 5000.0})
    daily = daily_series(pd.DataFrame(rows))
    a = daily[daily.market == "A"]
    f = features_as_of(("Onion", "Maharashtra", "A"), Series.from_frame(a), np.datetime64("2024-02-20", "D"), 7)
    assert f["last_price"] == 1020.0
    assert f["price_lag_7"] == 1013.0          # A on 13 February, not B (5000) on any day


def test_several_varieties_on_one_day_are_one_price_not_a_lag():
    rows = [{"commodity": "Onion", "state": "Maharashtra", "market": "A", "date": "2024-01-10", "modal_price": p}
            for p in (1000.0, 1200.0, 1400.0)]
    daily = daily_series(pd.DataFrame(rows))
    assert len(daily) == 1 and daily["modal_price"].iloc[0] == 1200.0


def test_no_scored_target_or_its_prices_reach_training(synthetic):
    samples = training_samples(daily_series(synthetic), [7, 30], step_days=5)
    train_s, test_s, cutoff = walk_forward_split(samples, holdout_days=90)
    assert len(train_s) and len(test_s)
    assert train_s["target_date"].max() <= cutoff < test_s["as_of"].min()
