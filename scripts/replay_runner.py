"""
Replay runner for AIAIC ML Foundation.

Loads a previously recorded execution by request_id and re-submits
the exact same payload to the API. Compares the new result against
the recorded result to prove determinism.

Usage:
    # List all recorded executions
    python scripts/replay_runner.py --list

    # Replay a specific execution
    python scripts/replay_runner.py --request-id <uuid>

    # Replay the most recent execution
    python scripts/replay_runner.py --latest

Determinism is proven when:
    original predicted_modal_price == replayed predicted_modal_price
"""

import argparse
import json
import sys
from pathlib import Path

import requests

from src.observability.replay import load_execution, list_executions

API_BASE = "http://localhost:8000/v1"
REPLAY_OUTPUT = Path("evidence_packet/replay_logs/replay_result.json")


def replay_execution(request_id: str) -> None:
    print(f"\n--- REPLAY RUNNER ---")
    print(f"Request ID: {request_id}")

    try:
        recorded = load_execution(request_id)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print(f"Recorded at      : {recorded['recorded_at']}")
    print(f"Original status  : {recorded['status']}")
    print(f"Original result  : {recorded['result'].get('predicted_modal_price')}")
    print(f"Model file       : {recorded['model_file']}")

    payload = recorded["payload"]
    print(f"\nRe-submitting payload to {API_BASE}/predict ...")

    try:
        response = requests.post(f"{API_BASE}/predict", json=payload, timeout=10)
    except requests.ConnectionError:
        print("ERROR: Cannot connect to API. Is uvicorn running?")
        sys.exit(1)

    replayed = response.json()

    original_price = recorded["result"].get("predicted_modal_price")
    replayed_price = replayed.get("predicted_modal_price")

    print(f"\n--- DETERMINISM CHECK ---")
    print(f"Original prediction : {original_price}")
    print(f"Replayed prediction : {replayed_price}")

    if original_price == replayed_price:
        print("RESULT: DETERMINISTIC — predictions match exactly ✓")
        deterministic = True
    else:
        diff = abs((original_price or 0) - (replayed_price or 0))
        print(f"RESULT: MISMATCH — difference: {diff:.4f}")
        print("This may indicate a model was retrained between executions.")
        deterministic = False

    replay_record = {
        "original_request_id": request_id,
        "original_recorded_at": recorded["recorded_at"],
        "original_model_file": recorded["model_file"],
        "original_predicted_price": original_price,
        "replayed_request_id": replayed.get("request_id"),
        "replayed_model_file": replayed.get("model_file"),
        "replayed_predicted_price": replayed_price,
        "deterministic": deterministic,
        "payload": payload,
    }

    REPLAY_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    REPLAY_OUTPUT.write_text(json.dumps(replay_record, indent=2))
    print(f"\nReplay result saved to: {REPLAY_OUTPUT}")


def main():
    parser = argparse.ArgumentParser(description="AIAIC ML Foundation — Replay Runner")
    parser.add_argument("--request-id", type=str, help="Replay a specific execution by ID")
    parser.add_argument("--latest", action="store_true", help="Replay the most recent execution")
    parser.add_argument("--list", action="store_true", help="List all recorded executions")
    args = parser.parse_args()

    if args.list:
        executions = list_executions()
        if not executions:
            print("No recorded executions found.")
            print("Run: python scripts/producer.py")
        else:
            print(f"Recorded executions ({len(executions)}):")
            for ex in executions:
                print(f"  {ex}")
        return

    if args.latest:
        executions = list_executions()
        if not executions:
            print("No recorded executions. Run producer.py first.")
            sys.exit(1)
        request_id = executions[-1]
        print(f"Using latest execution: {request_id}")
    elif args.request_id:
        request_id = args.request_id
    else:
        # Default: replay latest
        executions = list_executions()
        if not executions:
            print("No recorded executions. Run producer.py first.")
            sys.exit(1)
        request_id = executions[-1]
        print(f"No --request-id given, using latest: {request_id}")

    replay_execution(request_id)


if __name__ == "__main__":
    main()