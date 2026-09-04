"""
Replay mechanism for the AIAIC ML Foundation service.

Every prediction request + response is recorded as a JSON file in
evidence_packet/replay_logs/. Any recorded execution can be replayed
exactly by re-submitting the same payload to the same model version
and comparing the result.

Replay proves determinism: same input + same model = same output.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

REPLAY_LOG_DIR = Path("evidence_packet/replay_logs")


def record_execution(
    request_id: str,
    payload: Dict[str, Any],
    result: Dict[str, Any],
    status: str,
    error: Optional[str] = None,
) -> Path:
    """
    Records a full prediction execution to disk.
    Returns the path of the written replay file.
    """
    REPLAY_LOG_DIR.mkdir(parents=True, exist_ok=True)

    record = {
        "request_id": request_id,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "payload": payload,
        "result": result,
        "error": error,
        "model_file": result.get("model_file") if result else None,
        "data_hash": result.get("data_hash") if result else None,
    }

    file_path = REPLAY_LOG_DIR / f"{request_id}.json"
    file_path.write_text(json.dumps(record, indent=2))
    logger.info(
        "Execution recorded",
        extra={"request_id": request_id, "replay_file": str(file_path)}
    )
    return file_path


def load_execution(request_id: str) -> Dict[str, Any]:
    """
    Loads a previously recorded execution by request_id.
    Raises FileNotFoundError if not found.
    """
    file_path = REPLAY_LOG_DIR / f"{request_id}.json"
    if not file_path.exists():
        raise FileNotFoundError(
            f"No recorded execution found for request_id={request_id}. "
            f"Available: {[f.stem for f in REPLAY_LOG_DIR.glob('*.json')]}"
        )
    return json.loads(file_path.read_text())


def list_executions() -> list:
    """Lists all recorded execution IDs."""
    REPLAY_LOG_DIR.mkdir(parents=True, exist_ok=True)
    return [f.stem for f in sorted(REPLAY_LOG_DIR.glob("*.json"))]