"""The integration tests' model: trained once, in a temporary directory, on the SAME synthetic prices as
tests/forecast (labelled SYNTHETIC; it is not market data). So the API is tested end to end on a clean clone, with
no model committed and none downloaded."""

import pytest

from tests.forecast.conftest import synthetic_prices


@pytest.fixture(scope="session")
def api_models(tmp_path_factory):
    from src.forecast.train import train
    models = tmp_path_factory.mktemp("api_models")
    meta = train(synthetic_prices(), [7, 30], "SYNTHETIC test data (not market data)", models, holdout_days=90,
                 step_days=5)
    return models, meta
