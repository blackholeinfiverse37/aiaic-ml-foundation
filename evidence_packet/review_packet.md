# Review branch verification

## Scope

Branch `review-2026-10-02` is based on `aiaic-forecast` at `efa3478`. The supplied
review patch was applied on that branch. The cleanup removes tracked copies,
bundled model/history files, the old backend-check notebook, and retired helper
scripts from the proposed commit. Ignored local data/model copies were not
deleted.

The review packet's `/v1/predict` metrics are now explicitly marked invalid:
the endpoint used same-day minimum and maximum prices to predict that same
day's modal price. The forecast-quality source of truth is the `/v1/forecast`
release backtest.

## Checks completed

- `python -m pytest tests -q -p no:cacheprovider`: **69 passed**, 7 warnings,
  on Windows with Python 3.10.11. The run did not modify `evidence_packet/`.
- `docker compose -f docker/docker-compose.yml config --quiet`: passed.
- A GitHub Actions workflow now runs `python -m pytest tests -q` on pushes and
  pull requests, using Python 3.11.
- The review patch redacts the tunnel URL and personal paths from the staged
  evidence files. Final staged-content scans found no tunnel URLs, personal
  paths, or common embedded credential patterns.

## Not yet verified / blocked

- No `models/release/` bundle is present. Docker is installed, but its Linux
  engine is not running, so image build, container health, and the live
  `/v1/ready` check could not be performed.
- The `pilot_v2` dataset described in `ARYAN_NEXT_TASK_2026-10-02.md` is not in
  this workspace. The separate MSP export script also requires AIAIC's proposed
  D-139 marketing-season relabel to be applied before it can run.
- Therefore pilot training, same-split experiments, release packaging/tagging,
  AIAIC integration verification, and forecast replay are not claimed complete.
- GitHub Actions has not run yet; the workflow must be exercised after the
  branch is pushed.