"""Agmarknet renamed about 700 mandis "X" -> "X APMC" in November 2025 ("Indore" ends 2025-11-04, "Indore APMC"
starts 2025-11-01). Keyed on the published name, one mandi becomes two short series, and the dead name is listed as
a mandi the model can forecast (it then refuses every question about it). `--market-column mandi` keys on AIAIC's
identity instead. SYNTHETIC data (tests/forecast/conftest.py); no figure here describes a real market."""

import json

import pandas as pd
import pytest

from src.forecast.train import main


def _renamed(synthetic):
    """The same synthetic prices, published under "<name>" before the midpoint and "<name> APMC" after it, with the
    identity column AIAIC's export carries."""
    df = synthetic.copy()
    mid = df["date"].sort_values().iloc[len(df) // 2]
    df["mandi"] = df["market"]
    df.loc[df["date"] >= mid, "market"] = df.loc[df["date"] >= mid, "market"] + " APMC"
    return df


def test_the_identity_column_keeps_a_renamed_mandi_one_series(tmp_path, synthetic):
    csv = tmp_path / "renamed.csv"
    _renamed(synthetic).to_csv(csv, index=False)
    out = tmp_path / "m"
    main(["--input", str(csv), "--market-column", "mandi", "--horizons", "7", "30", "--holdout-days", "90",
          "--step-days", "5", "--models-dir", str(out), "--source", "SYNTHETIC test data (not market data)"])
    meta = json.loads(next(out.glob("forecast_*.json")).read_text())
    assert meta["markets"]["Onion|Maharashtra"] == ["Lasalgaon", "Nashik", "Pimpalgaon"]
    assert "'mandi' for the market" in meta["market_identity"]
    last = meta["market_last_quote"]["Onion|Maharashtra"]
    end = pd.Timestamp(meta["trained_through"])
    assert set(last) == {"Lasalgaon", "Nashik", "Pimpalgaon"}
    assert all(0 <= (end - pd.Timestamp(d)).days <= 10 for d in last.values())     # every mandi still reports


def test_without_it_the_rename_splits_the_mandi_and_the_meta_shows_the_dead_name(tmp_path, synthetic):
    csv = tmp_path / "renamed.csv"
    _renamed(synthetic).drop(columns=["mandi"]).to_csv(csv, index=False)
    out = tmp_path / "m"
    main(["--input", str(csv), "--horizons", "7", "30", "--holdout-days", "90", "--step-days", "5",
          "--models-dir", str(out), "--source", "SYNTHETIC test data (not market data)"])
    meta = json.loads(next(out.glob("forecast_*.json")).read_text())
    names = meta["markets"]["Onion|Maharashtra"]
    assert "Lasalgaon" in names and "Lasalgaon APMC" in names
    last = meta["market_last_quote"]["Onion|Maharashtra"]
    assert last["Lasalgaon"] < last["Lasalgaon APMC"]          # the old name stopped: the meta now says when


def test_a_renamed_crop_stays_one_crop_with_the_crop_column(tmp_path, synthetic):
    """Agmarknet spelled whole tur three ways; `--commodity-column crop` keeps one crop, and --crops takes its key."""
    df = _renamed(synthetic)
    df["crop"] = df["commodity"].str.lower()
    late = df["date"] >= df["date"].sort_values().iloc[len(df) // 2]
    df.loc[late & (df["commodity"] == "Onion"), "commodity"] = "Onion(New spelling)"
    csv = tmp_path / "renamed.csv"
    df.to_csv(csv, index=False)
    out = tmp_path / "m"
    main(["--input", str(csv), "--market-column", "mandi", "--commodity-column", "crop", "--crops", "onion",
          "--horizons", "7", "30", "--holdout-days", "90", "--step-days", "5", "--models-dir", str(out),
          "--source", "SYNTHETIC test data (not market data)"])
    meta = json.loads(next(out.glob("forecast_*.json")).read_text())
    assert meta["commodities"] == ["onion"]
    assert "'crop' for the commodity" in meta["market_identity"]


def test_a_missing_identity_column_is_refused_not_ignored(tmp_path, synthetic):
    csv = tmp_path / "plain.csv"
    synthetic.to_csv(csv, index=False)
    with pytest.raises(SystemExit) as e:
        main(["--input", str(csv), "--market-column", "mandi", "--models-dir", str(tmp_path / "m")])
    assert "no column 'mandi'" in str(e.value)
