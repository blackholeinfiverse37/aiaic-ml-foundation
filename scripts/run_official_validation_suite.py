from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests

REPO = Path(__file__).resolve().parents[1]
LOG_DIR = REPO / 'evidence_packet' / 'runtime_logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)
RUN_STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
LOG_PATH = LOG_DIR / f'official_validation_suite_{RUN_STAMP}.txt'


def load_env() -> None:
    env_path = REPO / '.env'
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip())


def emit(message: str, stream) -> None:
    print(message, flush=True)
    stream.write(message + '\n')
    stream.flush()


def run_command(label: str, command: list[str], cwd: Path, stream) -> tuple[int, float, str]:
    emit(f'\n=== {label} ===', stream)
    emit('COMMAND: ' + subprocess.list2cmdline(command), stream)
    started = time.perf_counter()
    result = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True)
    elapsed = time.perf_counter() - started
    if result.stdout:
        emit('STDOUT:\n' + result.stdout.rstrip(), stream)
    if result.stderr:
        emit('STDERR:\n' + result.stderr.rstrip(), stream)
    emit(f'EXIT_CODE: {result.returncode}', stream)
    emit(f'ELAPSED_SECONDS: {elapsed:.2f}', stream)
    return result.returncode, elapsed, result.stdout + result.stderr


def run_backend_probes(stream) -> tuple[bool, float]:
    base = os.getenv('AIAIC_API_BASE', os.getenv('VITE_AQIAIC_BASE_URL', '')).rstrip('/')
    emit('\n=== BACKEND HEALTH AND CATALOG ===', stream)
    emit('BASE_URL: ' + (base or '(unset)'), stream)
    if not base:
        emit('BACKEND_STATUS: FAIL (base URL is unset)', stream)
        return False, 0.0
    started = time.perf_counter()
    passed = True
    for path in ('health', 'catalog?state=maharashtra'):
        label = path.split('?', 1)[0]
        try:
            response = requests.get(urljoin(base + '/', path), timeout=20)
            content_type = response.headers.get('content-type', '')
            body = response.text[:500].replace('\n', ' ')
            is_interstitial = 'You are about to visit' in response.text or 'ngrok' in response.text.lower() and '<html' in response.text.lower()
            is_api_response = response.ok and not is_interstitial and ('json' in content_type.lower() or response.text.lstrip().startswith(('{', '[')))
            passed = passed and is_api_response
            emit(f'{label.upper()}: HTTP {response.status_code}; content-type={content_type}; api_response={is_api_response}; body={body}', stream)
        except Exception as exc:
            passed = False
            emit(f'{label.upper()}: ERROR {type(exc).__name__}: {exc}', stream)
    elapsed = time.perf_counter() - started
    emit(f'BACKEND_STATUS: {"PASS" if passed else "FAIL"}', stream)
    emit(f'ELAPSED_SECONDS: {elapsed:.2f}', stream)
    return passed, elapsed


def main() -> int:
    os.chdir(REPO)
    load_env()
    results: dict[str, tuple[bool, float]] = {}
    suite_started = time.perf_counter()
    with LOG_PATH.open('w', encoding='utf-8') as stream:
        emit(f'OFFICIAL VALIDATION SUITE | UTC {RUN_STAMP}', stream)
        emit(f'REPOSITORY: {REPO}', stream)
        emit(f'PYTHON: {sys.executable}', stream)
        backend_ok, backend_seconds = run_backend_probes(stream)
        results['backend'] = (backend_ok, backend_seconds)

        training_started_at = time.time()
        train_command = [
            sys.executable, '-m', 'src.forecast.train',
            '--input', 'data/raw/agmarknet_mh_mp_2016_2026.csv.gz',
            '--crops', 'Onion', 'Soyabean', 'Wheat',
            '--horizons', '7', '30',
            '--holdout-days', '180',
            '--step-days', '7',
            '--seed', '42',
            '--models-dir', 'models/forecast_official',
            '--source', 'Agmarknet via data.gov.in (Variety-wise Daily Market Prices), AIAIC export 2016-2026',
        ]
        train_code, train_seconds, train_output = run_command('OFFICIAL DATA TRAINING', train_command, REPO, stream)
        model_files = sorted(
            (REPO / 'models' / 'forecast_official').glob('forecast_*.json'),
            key=lambda path: path.stat().st_mtime,
        )
        new_models = [path for path in model_files if path.stat().st_mtime >= training_started_at - 1]
        model_json = new_models[-1] if train_code == 0 and new_models else None
        if model_json:
            emit('MODEL_METADATA: ' + str(model_json.relative_to(REPO)), stream)
        elif train_code == 0:
            emit('MODEL_METADATA: no newly generated metadata file found', stream)
        results['training'] = (train_code == 0 and model_json is not None, train_seconds)

        compare_ok = False
        compare_seconds = 0.0
        if model_json:
            compare_script = REPO / 'aryan files' / 'compare_with_official_backtest.py'
            compare_code, compare_seconds, _ = run_command(
                'OFFICIAL BACKTEST COMPARISON',
                [sys.executable, str(compare_script), str(model_json)],
                compare_script.parent,
                stream,
            )
            compare_ok = compare_code == 0
        else:
            emit('\n=== OFFICIAL BACKTEST COMPARISON ===\nSKIPPED: training did not produce a new model metadata file.', stream)
        results['comparison'] = (compare_ok, compare_seconds)

        test_code, test_seconds, _ = run_command(
            'FULL PYTEST SUITE', [sys.executable, '-m', 'pytest', 'tests', '-q'], REPO, stream
        )
        results['tests'] = (test_code == 0, test_seconds)

        total_seconds = time.perf_counter() - suite_started
        emit('\n=== SUITE SUMMARY ===', stream)
        for name, (passed, elapsed) in results.items():
            emit(f'{name.upper()}: {"PASS" if passed else "FAIL"}; elapsed={elapsed:.2f}s', stream)
        emit(f'TOTAL_ELAPSED_SECONDS: {total_seconds:.2f}', stream)
        emit(f'TOTAL_ELAPSED_MINUTES: {total_seconds / 60:.2f}', stream)
        emit('LOG_FILE: ' + str(LOG_PATH.relative_to(REPO)), stream)
        suite_ok = all(passed for passed, _ in results.values())
        emit('SUITE_STATUS: ' + ('PASS' if suite_ok else 'FAIL'), stream)
    return 0 if all(passed for passed, _ in results.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
