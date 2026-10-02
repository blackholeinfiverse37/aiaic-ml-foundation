from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

REPO = Path(__file__).resolve().parents[1]
BASE_URL = 'http://127.0.0.1:8100'
MODEL_FILE = 'forecast_20261002T064450Z_9595e12e.joblib'
OUTPUT = REPO / 'evidence_packet' / 'runtime_logs' / 'forecast_api_http_smoke_20261002.json'


def fetch_json(url: str, body: dict | None = None) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode('utf-8')
    request = Request(url, data=data, headers={'Content-Type': 'application/json'}, method='GET' if body is None else 'POST')
    with urlopen(request, timeout=20) as response:
        return response.status, json.loads(response.read().decode('utf-8'))


def main() -> None:
    meta_status, meta = fetch_json(BASE_URL + '/v1/forecast/meta')
    if meta.get('model_file') != MODEL_FILE:
        raise RuntimeError(f'Unexpected model loaded: {meta.get("model_file")}')

    request_body = {
        'commodity': 'Wheat',
        'state': 'Madhya Pradesh',
        'market': 'Satna APMC',
        'as_of': '2026-08-26',
        'horizon_days': 30,
    }
    forecast_status, result = fetch_json(BASE_URL + '/v1/forecast', request_body)
    if forecast_status != 200 or result.get('abstain') is not False:
        raise RuntimeError(f'Forecast request failed or abstained: HTTP {forecast_status}, {result}')

    proof = {
        'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'base_url': BASE_URL,
        'meta_status': meta_status,
        'forecast_status': forecast_status,
        'model_loaded': meta['model_file'],
        'request': request_body,
        'caller_history_supplied': False,
        'result': result,
        'status': 'PASS',
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(proof, indent=2), encoding='utf-8')
    print(json.dumps({
        'status': proof['status'],
        'proof_file': str(OUTPUT),
        'meta_status': meta_status,
        'forecast_status': forecast_status,
        'model_loaded': meta['model_file'],
        'abstain': result['abstain'],
        'p10': result['p10'],
        'p50': result['p50'],
        'p90': result['p90'],
    }, indent=2))


if __name__ == '__main__':
    main()
