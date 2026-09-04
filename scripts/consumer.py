"""
Local integration consumer for AIAIC ML Foundation.

Reads the prediction result from the producer handoff file,
validates it, and produces a simple income assessment summary.

In a real AIAIC deployment, this consumer would be the reasoning
engine or downstream intelligence layer. Here it is a local script
that demonstrates the full producer → API → consumer flow.

Usage:
    python scripts/consumer.py
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

HANDOFF_PATH = Path("evidence_packet/api_samples/handoff.json")
OUTPUT_PATH = Path("evidence_packet/api_samples/consumer_output.json")


def assess_price(commodity: str, state: str, predicted_price: float) -> dict:
    """
    Simple income assessment based on predicted price.
    In production this would call AIAIC Core income assessment logic.
    Here it demonstrates the consumer receiving and acting on the result.
    """
    # Reference MSP values (publicly available 2024-25 values)
    MSP_REFERENCE = {
        "wheat": 2275,
        "rice": 2300,
        "onion": 800,   # indicative — onion has no official MSP
        "potato": 600,  # indicative
        "tomato": 800,  # indicative
    }

    msp = MSP_REFERENCE.get(commodity.lower())
    assessment = {}

    if msp:
        price_vs_msp = predicted_price - msp
        assessment["msp_reference"] = msp
        assessment["price_vs_msp"] = round(price_vs_msp, 2)
        if price_vs_msp >= 0:
            assessment["income_signal"] = "ABOVE_MSP"
            assessment["recommendation"] = (
                f"Predicted price ({predicted_price:.0f}) is above MSP ({msp}). "
                f"Market conditions appear favourable for {commodity} in {state}."
            )
        else:
            assessment["income_signal"] = "BELOW_MSP"
            assessment["recommendation"] = (
                f"Predicted price ({predicted_price:.0f}) is below MSP ({msp}). "
                f"Farmer may benefit from checking scheme eligibility "
                f"(e.g. price deficiency schemes) for {commodity} in {state}."
            )
    else:
        assessment["income_signal"] = "NO_MSP_REFERENCE"
        assessment["recommendation"] = (
            f"No MSP reference available for {commodity}. "
            f"Predicted mandi price: {predicted_price:.0f} INR/quintal."
        )

    return assessment


def main():
    if not HANDOFF_PATH.exists():
        print("ERROR: No handoff file found. Run producer.py first.")
        print(f"Expected: {HANDOFF_PATH}")
        sys.exit(1)

    handoff = json.loads(HANDOFF_PATH.read_text())
    request_id = handoff.get("request_id")
    predicted_price = handoff.get("predicted_modal_price")
    commodity = handoff.get("commodity")
    state = handoff.get("state")

    print("\n--- CONSUMER: Processing prediction result ---")
    print(f"Request ID       : {request_id}")
    print(f"Commodity        : {commodity}")
    print(f"State            : {state}")
    print(f"Predicted Price  : {predicted_price} INR/quintal")

    assessment = assess_price(commodity, state, predicted_price)

    output = {
        "request_id": request_id,
        "consumed_at": datetime.now(timezone.utc).isoformat(),
        "commodity": commodity,
        "state": state,
        "predicted_modal_price": predicted_price,
        "income_assessment": assessment,
    }

    print("\n--- INCOME ASSESSMENT ---")
    print(json.dumps(assessment, indent=2))

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2))
    print(f"\nConsumer output saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()