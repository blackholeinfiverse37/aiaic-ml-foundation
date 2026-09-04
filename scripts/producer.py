"""
Local integration producer for AIAIC ML Foundation.

Simulates a data producer that reads from the processed features CSV,
picks a real row, and sends it to the ML API as a prediction request.

Usage:
    python scripts/producer.py
    python scripts/producer.py --commodity Onion --state Maharashtra
    python scripts/producer.py --random   # picks a random row from features.csv

Output:
    Prints the API response JSON and saves it to
    evidence_packet/api_samples/producer_response.json
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import requests

API_BASE = "http://localhost:8000/v1"
FEATURES_CSV = Path("data/processed/features.csv")
OUTPUT_PATH = Path("evidence_packet/api_samples/producer_response.json")

FEATURE_COLUMNS = [
    "commodity", "state", "grade", "min_price", "max_price",
    "month", "day_of_week", "is_weekend", "season",
    "month_sin", "month_cos",
    "modal_price_lag_1", "modal_price_lag_7", "modal_price_lag_14",
    "modal_price_roll_mean_7", "modal_price_roll_std_7",
    "modal_price_roll_mean_14", "modal_price_roll_std_14",
    "modal_price_roll_mean_30", "modal_price_roll_std_30",
]


def load_sample_row(commodity: str = None, state: str = None, random: bool = False) -> dict:
    """
    Loads a real row from the feature-engineered dataset as the
    prediction payload. This is real data, not synthetic.
    """
    if not FEATURES_CSV.exists():
        print(f"ERROR: features.csv not found at {FEATURES_CSV}")
        print("Run: python run_pipeline.py --stage features")
        sys.exit(1)

    df = pd.read_csv(FEATURES_CSV, low_memory=False, nrows=50000)

    if random:
        row = df.sample(1, random_state=None).iloc[0]
    elif commodity or state:
        mask = pd.Series([True] * len(df))
        if commodity:
            mask &= df["commodity"].str.lower() == commodity.lower()
        if state:
            mask &= df["state"].str.lower() == state.lower()
        filtered = df[mask]
        if filtered.empty:
            print(f"No rows found for commodity={commodity}, state={state}")
            sys.exit(1)
        row = filtered.iloc[0]
    else:
        # Default: first Onion + Maharashtra row
        mask = (df["commodity"].str.lower() == "onion") & \
               (df["state"].str.lower() == "maharashtra")
        filtered = df[mask]
        row = filtered.iloc[0] if not filtered.empty else df.iloc[0]

    payload = {}
    for col in FEATURE_COLUMNS:
        if col in row.index:
            val = row[col]
            if pd.isna(val):
                payload[col] = None
            elif col in ("commodity", "state", "grade", "season"):
                payload[col] = str(val)
            elif col in ("month", "day_of_week", "is_weekend"):
                payload[col] = int(val)
            else:
                payload[col] = float(val)

    return payload


def send_prediction(payload: dict) -> dict:
    """Sends prediction request to the ML API."""
    print("\n--- PRODUCER: Sending prediction request ---")
    print(f"Endpoint : {API_BASE}/predict")
    print(f"Commodity: {payload.get('commodity')}")
    print(f"State    : {payload.get('state')}")
    print(f"Month    : {payload.get('month')}")
    print()

    try:
        response = requests.post(f"{API_BASE}/predict", json=payload, timeout=10)
    except requests.ConnectionError:
        print("ERROR: Cannot connect to API. Is uvicorn running?")
        print("Run: uvicorn src.api.main:app --port 8000")
        sys.exit(1)

    print(f"Status Code: {response.status_code}")
    result = response.json()
    print(json.dumps(result, indent=2))

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps({
        "payload": payload,
        "response": result,
        "status_code": response.status_code,
    }, indent=2))
    print(f"\nSaved to: {OUTPUT_PATH}")

    return result


def main():
    parser = argparse.ArgumentParser(description="AIAIC ML Foundation — Local Producer")
    parser.add_argument("--commodity", type=str, default=None)
    parser.add_argument("--state", type=str, default=None)
    parser.add_argument("--random", action="store_true")
    args = parser.parse_args()

    payload = load_sample_row(
        commodity=args.commodity,
        state=args.state,
        random=args.random,
    )
    result = send_prediction(payload)

    # Pass request_id to consumer via a handoff file
    handoff_path = Path("evidence_packet/api_samples/handoff.json")
    handoff_path.write_text(json.dumps({
        "request_id": result.get("request_id"),
        "predicted_modal_price": result.get("predicted_modal_price"),
        "commodity": payload.get("commodity"),
        "state": payload.get("state"),
    }, indent=2))
    print(f"Handoff written for consumer: {handoff_path}")


if __name__ == "__main__":
    main()