"""SYNTHETIC price data for the forecast tests. It is NOT market data and must never be shown as such: a seasonal
curve, a slow trend, noise, and gaps where a mandi did not report, for two crops at three mandis each."""

import numpy as np
import pandas as pd
import pytest


def synthetic_prices(days: int = 730, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2023-01-01", periods=days, freq="D")
    rows = []
    for commodity, level in (("Onion", 1800.0), ("Wheat", 2400.0)):
        for market, offset in (("Lasalgaon", 0.0), ("Pimpalgaon", 60.0), ("Nashik", -40.0)):
            season = 1.0 + 0.25 * np.sin(2 * np.pi * (dates.dayofyear.values - 80) / 365.0)
            trend = 1.0 + 0.10 * np.arange(days) / days
            price = (level + offset) * season * trend * (1.0 + rng.normal(0, 0.03, days))
            reported = rng.random(days) > 0.2          # about one day in five has no quote
            for d, p, ok in zip(dates, price, reported):
                if ok:
                    rows.append({"commodity": commodity, "state": "Maharashtra", "district": "Nashik",
                                 "market": market, "date": d, "min_price": p * 0.8, "max_price": p * 1.2,
                                 "modal_price": round(float(p), 2)})
    return pd.DataFrame(rows)


@pytest.fixture(scope="session")
def synthetic() -> pd.DataFrame:
    return synthetic_prices()


@pytest.fixture(scope="session")
def trained(tmp_path_factory, synthetic):
    from src.forecast.train import train
    models = tmp_path_factory.mktemp("forecast_models")
    meta = train(synthetic, [7, 30], "SYNTHETIC test data (not market data)", models, holdout_days=90, step_days=5)
    return models, meta
