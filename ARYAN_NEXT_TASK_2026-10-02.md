# Aryan: review of the 2026-10-02 integration, your next task, the data, and how a model reaches AIAIC

From: Hemanth (AIAIC backend), 2 October 2026.
Repository reviewed: `blackholeinfiverse37/aiaic-ml-foundation`, branch `aiaic-forecast`, commit `efa3478`
("feat: package and integrate official forecast model"), plus the `backend_integration_bundle` you sent.

---

## 1. In short

1. **The integration works.** AIAIC's backend called your service with today's bundle and got labelled,
   experimental ranges. All 9 checks of AIAIC's integration check pass. The model is reproducible: your official
   backtest comparison agrees.
2. **The model does not yet beat "the price stays where it is" overall** (skill -0.157). 4 of its 12
   crop/state/horizon groups are usable. Soybean is much worse than persistence in both states. Onion in Maharashtra
   (the Nashik pilot) is not usable at either horizon.
3. **Two data problems hit the pilot directly, and both are fixed in the new dataset:**
   - Agmarknet renamed about 700 mandis from "X" to "X APMC" in November 2025, the month its portal was upgraded
     to "Agmarknet 2.0" (Government of India press release, PIB id 2204750, as seen in search results: the page
     could not be opened automatically, and it does not mention the renames, which are seen in the data). Your
     model's mandi lists hold 2,646 crop-state entries; keyed on AIAIC's identity they are 1,525 (1,391 distinct
     published names are 772 mandis). It refuses every question about an old name ("Indore" ends 2025-11-04;
     "Indore APMC" starts 2025-11-01).
   - Agmarknet also spelled whole tur three ways. Selected by its old name, tur stops on 2025-11-04.
4. **Some files in the repository are wrong or unsafe:**
   - the retired `/v1/predict` metrics are still quoted as model quality;
   - a public tunnel address is committed;
   - the Docker image would start with no model and still report healthy;
   - MongoDB is published on all interfaces with no password;
   - 16 tests fail on a clean clone;
   - about 50 MB of data and copies are committed.

   Every one has a replacement file in this folder (section 7).
5. **When a model is built, you do not send files to me, and the repositories are not connected.** You publish a
   tagged release with checksums. Kaushlendra's pipeline runs it as its own container beside AIAIC. AIAIC already
   calls it over HTTP (section 4).

---

## 2. What was checked, and the evidence

| Check | Result |
|---|---|
| Your tests on a **clean clone** of `efa3478` | **70 passed, 16 failed.** All 16 are `/v1/predict` integration tests that need a `price_predictor_*.joblib`, which is gitignored. "86 passed" holds only on a machine that has that file. |
| A clean-clone test run's side effects | It writes **21 replay files into `evidence_packet/replay_logs/`**: the evidence folder changes every time someone runs the tests. |
| Your service with the bundle (`AIAIC_MODELS_DIR` = bundle files) | `/v1/forecast/meta` and `/v1/forecast` answer. `/v1/health` says **`degraded`, `model_loaded: false`**: it checks only the retired `/v1/predict` model. |
| AIAIC's integration check (`/ml/price-model`, `/ml/price-range` against your service) | **9/9 PASS.** Ranges for Indore APMC: onion 7 days, wheat 7 and 30 days. An untrained crop is refused (`not_trained_for`). A crisis message gets the helpline first. |
| The bundle's files (sha256) | model `652ddeb0…5ee51`, metadata `2a5480b3…80a5eb5`, history `d7878738…0ebc2` |

The current model's backtest, read from its metadata (`forecast_20261002T064450Z_9595e12e.json`). Skill =
1 − MAE(p50) / MAE(persistence). Usable = at least 20 cases, skill above 0, and the p10-p90 range held at least 70%
of outcomes.

| Crop | State | Days | Cases | p50 error (Rs/q) | Persistence error | Skill | p10-p90 held | Usable |
|---|---|---|---|---|---|---|---|---|
| Onion | Madhya Pradesh | 7 | 765 | 306 | 320 | +0.042 | 70% | yes |
| Onion | Madhya Pradesh | 30 | 528 | 501 | 543 | +0.079 | 65% | no |
| Onion | Maharashtra | 7 | 1,041 | 304 | 292 | -0.043 | 71% | no |
| Onion | Maharashtra | 30 | 741 | 624 | 635 | +0.018 | 52% | no |
| Soyabean | Madhya Pradesh | 7 | 1,667 | 522 | 388 | -0.345 | 81% | no |
| Soyabean | Madhya Pradesh | 30 | 1,147 | 683 | 507 | -0.347 | 85% | no |
| Soyabean | Maharashtra | 7 | 1,223 | 535 | 360 | -0.485 | 80% | no |
| Soyabean | Maharashtra | 30 | 896 | 695 | 501 | -0.386 | 81% | no |
| Wheat | Madhya Pradesh | 7 | 3,075 | 69 | 74 | +0.074 | 85% | yes |
| Wheat | Madhya Pradesh | 30 | 2,176 | 90 | 128 | +0.300 | 94% | yes |
| Wheat | Maharashtra | 7 | 1,504 | 85 | 82 | -0.041 | 83% | no |
| Wheat | Maharashtra | 30 | 1,109 | 123 | 146 | +0.157 | 90% | yes |

### A verification run on your code (by AIAIC; it is NOT your release)

To check the replacement files end to end, AIAIC ran your trainer with the same settings as your official run
(2016-2026; onion, soybean, wheat; horizons 7 and 30; holdout 180; step 7; seed 42). The only change: series keyed
on the new `mandi` and `crop` columns.

| Crop | State | Days | Your model: skill, held | Keyed on mandi and crop: skill, held |
|---|---|---|---|---|
| onion | Madhya Pradesh | 7 | +0.042, 70% (usable) | +0.021, 71% (usable) |
| onion | Madhya Pradesh | 30 | +0.079, 65% | +0.039, 67% |
| onion | Maharashtra | 7 | -0.043, 71% | -0.002, 72% |
| onion | Maharashtra | 30 | +0.018, 52% | +0.061, 55% |
| soybean | Madhya Pradesh | 7 | -0.345, 81% | -0.316, 82% |
| soybean | Madhya Pradesh | 30 | -0.347, 85% | -0.317, 82% |
| soybean | Maharashtra | 7 | -0.485, 80% | -0.519, 83% |
| soybean | Maharashtra | 30 | -0.386, 81% | -0.371, 78% |
| wheat | Madhya Pradesh | 7 | +0.074, 85% (usable) | +0.135, 83% (usable) |
| wheat | Madhya Pradesh | 30 | +0.300, 94% (usable) | +0.327, 93% (usable) |
| wheat | Maharashtra | 7 | -0.041, 83% | **+0.053, 86% (usable)** |
| wheat | Maharashtra | 30 | +0.157, 90% (usable) | +0.190, 90% (usable) |

- **Overall:** skill -0.157 → **-0.140**. Usable groups 4 → **5**. Crop-state mandi entries listed: 2,646 →
  **1,525** (distinct: 1,391 published names → 772 mandis).
  This is one run, so a difference of a few hundredths may be noise. **The identity fix is needed for
  correctness. It does not fix accuracy.**
- **Packaged and served:** the run was packaged with the new `scripts/package_forecast_release.py` and built with
  the new `docker/Dockerfile` (image 794 MB).
  - The container reports healthy only with its model loaded, and `/v1/predict` answers 410.
  - **AIAIC's check passes 9/9 against the container**, now at plain "Indore".
  - A deliberately wrong checksum made the image build fail at the verify step, as intended.

### Why soybean fails (a hypothesis for you to test, not a finding)

Soybean's monthly median price moved like this:
- Maharashtra: about Rs 4,000-4,300 in Oct-Dec 2025, Rs 5,129 in Feb 2026, Rs 6,600-6,800 in May-Jul 2026;
- Madhya Pradesh: about the same.

The scored period (from 2026-05-23) sits entirely in that jump. A model that predicts the price LEVEL tends to pull
back toward history in a trending market, while "the price stays where it is" rides the trend. Tree ensembles also
predict roughly within the range of targets they were trained on (Peter Ellis, "Extrapolation is tough for trees!",
2016, https://freerangestats.info/blog/2016/12/10/extrapolation). Predicting the
CHANGE from the last price (for example `log(target / last_price)`, turned back into a level afterwards) anchors the
model to persistence. That is the first experiment in section 5.

---

## 3. What is wrong in the repository, and the fix

| # | Severity | What | Where | Fix |
|---|---|---|---|---|
| A1 | High | `/v1/predict` reads the SAME day's min and max price to predict that day's modal price. Its R² 0.9946, MAPE 4.52% and "10x better than baseline" measure that leak, not forecasting. The model metadata confirms `min_price` and `max_price` in its features. | `models/price_predictor_20260928T091607Z_78d16a7e.json`; quoted in `README.md`, `DEP.md:77`, `review_packet/REVIEW_PACKET.md:17-18,51-53`, `review_packet/Executive_Assessment.md:14,33`, `review_packet/architecture_summary.md:111-116` | Retire it: `/v1/predict` answers 410 Gone and points to `/v1/forecast` (new `src/api/routes.py`). New `README.md` and `DEP.md`. **Correct the review-packet lines yourself:** it is your assessment. |
| A2 | High | A public tunnel address (the ngrok tunnel to Hemanth's laptop) is committed in a public repository. | `.env.example`, `scripts/check_aiaic_ngrok.py`, `backend_checks.ipynb`, two copies of `official_validation_suite_20261002T063823Z.txt` | New `.env.example` with no address. New `scripts/check_aiaic_backend.py`, which takes the address when you run it. Delete the notebook (it also carries a personal local path) and the ngrok script. The patch redacts the address in the two logs, and a Windows user name in three files' paths. `git apply --index` stages the deletions; the final `git grep` in `CLEANUP_COMMANDS.md` proves nothing is left (rehearsed on a copy of `efa3478`). |
| A3 | High | A CI-built image has **no model**: `COPY models/` copies only JSON (the joblib files are gitignored). The HEALTHCHECK passes on HTTP 200 even when health says `degraded`. | `docker/Dockerfile` | New Dockerfile: copies `models/release/`, **fails the build** unless `sha256sum -c SHA256SUMS` passes, and its HEALTHCHECK calls `/v1/ready` (503 without a model). |
| A4 | High | MongoDB is published on `27017` on all interfaces with **no authentication**. The API waits for it. `env_file: ../.env` makes `docker compose up` fail on a clean clone. Mongo is never needed to serve, and a second database beside AIAIC's is a parallel store the unified task rules out. | `docker/docker-compose.yml` | New compose: the forecast service only, bound to `127.0.0.1:8040`. Mongo is behind `--profile mongo`, on `127.0.0.1` only. No `env_file`. |
| A5 | Medium | `/v1/health` and `/v1/ready` describe the retired predictor, so a running forecast reports `degraded`. | `src/api/routes.py`, `src/api/schemas.py` | Both describe the forecast model (file, version, trained-through date, data hash). |
| A6 | Medium | 16 tests fail on a clean clone, and test runs write into `evidence_packet/`. | `tests/integration/`, `tests/api/` | New tests train on the existing SYNTHETIC fixture in a temporary folder. Nothing is written to `evidence_packet/`. **Review branch, no model present: 69 passed, 0 failed, 0 files changed in `evidence_packet/`** (`final_suite.txt`). |
| A7 | Medium | Mandi and crop identity (section 1): dead mandi names are offered, renamed series split in two, and tur breaks on 2025-11-04. | the training data | New export with `mandi` and `crop` columns. New trainer options `--market-column mandi --commodity-column crop`. The metadata now carries `market_last_quote` (the last day each mandi quoted) and `market_identity`. |
| A8 | Medium | About 50 MB of data and copies committed: `out/` (24 MB), `aryan files/` (a second 24 MB copy plus a copy of AIAIC's handoff), `aiaic_forecast.patch`, `evidence_packet/backend_integration_bundle_20261002.zip`, and the bundle's model and history. | repository | Commands in section 7. Model files belong on a release (section 4), data on a shared drive. |
| A9 | Medium | `scripts/package_forecast_backend_bundle.py` is hard-wired to one model file and one date, and writes into `evidence_packet/`. | `scripts/` | Replaced by `scripts/package_forecast_release.py --from <models dir>`. It writes `models/release/` (the 3 files, `SHA256SUMS` with LF line endings, `RELEASE.json`) and proves the release answers. |
| A10 | Low | `README.md` is UTF-16, which shows as binary in diffs and in several tools. | `README.md` | New UTF-8 README. |
| A11 | Low | `evidence_packet/review_packet.md` is **empty**. Your task makes the evidence packet mandatory ("Missing Evidence Packet will result in Revision Required"). | `evidence_packet/` | Write it (section 5, step D). |
| A12 | Low | Forecast calls are not recorded for replay. Test 1's replay covered only `/v1/predict`. | `src/forecast/` | Section 5, step E. |
| A13 | Low | The image installs everything in `requirements.txt` (xgboost, pymongo, pytest…). | `docker/Dockerfile` | New `requirements-serve.txt` with only what serving needs, at the same pins (a joblib model must load with the versions that wrote it). |
| A14 | Low | The 503 answer without a model names the server's absolute models path. | `src/forecast/service.py` | Says "No trained forecast is loaded" and how to train, without the path. |

---

## 4. How a model reaches AIAIC (the decision)

**Decision: your forecast runs as its own container on the AIAIC VM, and AIAIC calls it over HTTP.** You do not
send model files to Hemanth. Neither repository imports the other.

```
your repo ── tag forecast-vYYYY.MM.DD ──> GitHub release assets:
             forecast_*.joblib, forecast_*.json, forecast_*_history.csv.gz, SHA256SUMS, RELEASE.json
                     │
                     ▼  (Kaushlendra's pipeline: download assets, sha256sum -c, pytest, docker build, push)
             image  bhiv/aiaic-ml:<tag>   (pinned tag, never "latest")
                     │
                     ▼  (VM: docker compose, same network as AIAIC, NO published port)
             service aiaic-ml:8000  <── AIAIC  ML_PRICE_API_URL=http://aiaic-ml:8000
                                            GET /ml/price-model   -> your /v1/forecast/meta
                                            POST /ml/price-range  -> your /v1/forecast
                                            (dashboard "Price model" page, labelled experimental)
```

Why this, and not the alternatives:

- **AIAIC is already built for it** (AIAIC decision D-124):
  - its `/ml/price-model` and `/ml/price-range` call your `/v1/forecast/meta` and `/v1/forecast`;
  - **it re-checks your backtest rules itself** (at least 20 cases, skill above 0, range held at least 70%,
    p10 ≤ p50 ≤ p90);
  - it labels every range "experimental; not used in decisions";
  - it never feeds a range into a farmer's decision.

  A new model needs **no AIAIC code change** while the contract holds.
- **Copying model files into AIAIC** would put binaries in AIAIC's git and your library pins in AIAIC's image. It
  would also run inference inside AIAIC's single-worker server, and rolling back would mean rolling back AIAIC.
- **A repository connection** (submodule or package import) has the same problems, plus dependency conflicts. It
  would also make your capability a copy inside AIAIC, which the unified task rules out ("No parallel runtime or
  duplicate capability").
- **It is the pattern AIAIC already runs** for the plant service. Rollback is the previous tag. The checksums tie
  image to release to dataset manifest. With no public port, nothing outside the VM can call it.

Who does what:

| Who | Does |
|---|---|
| **Aryan** | trains, packages (`scripts/package_forecast_release.py`), publishes the tagged release with honest release notes, checks the image locally, tells Hemanth and Kaushlendra the tag |
| **Kaushlendra** | pipeline that builds and pushes the image from the release, the `aiaic-ml` service in the VM's production compose, `ML_PRICE_API_URL` set to `http://aiaic-ml:8000` (the GitHub variable is already passed to AIAIC), health and rollback |
| **Hemanth** | sends datasets with manifests, runs AIAIC's integration check against each release, keeps AIAIC's own re-check of the rules |
| **Owner / agronomist** | decides if and when any forecast may go beyond the operator dashboard |

**MasterDB.** When its details arrive, the dataset manifest (sha256) and each `RELEASE.json` become provenance
records there. Until then they live on the release and with the dataset.

---

## 5. Your next task (in order), with acceptance criteria

**A. Make the repository clean and deployable** (half a day).
- Apply the replacement files (section 7) and remove the committed data and copies.
- Add a small CI workflow in your repository that runs `pytest tests -q` on every push.
- Accept when:
  - a clean clone passes `pytest tests -q` with no model present;
  - `docker compose -f docker/docker-compose.yml up --build` is healthy only with a model in `models/release/`;
  - no address, key or data file is committed;
  - `/v1/predict` answers 410.

**B. Train the pilot model on the new dataset.**
- Use `--market-column mandi --commodity-column crop --crops onion soybean tur wheat` from 2001.
- Name the dataset's sha256 (from its `MANIFEST.json`) in `--source`.
- Accept when:
  - all 16 groups (4 crops × 2 states × 7 and 30 days) are in the metadata;
  - the release notes carry the full table, good or bad;
  - tur answers or abstains with a reason;
  - the table is compared with the two tables in section 2.

**C. Experiments for skill**, each on the SAME walk-forward split and cutoff, each reported as a full table:
1. Predict the change from the last price (`log(target / last_price)`), then convert back to a level.
2. One model per crop against the pooled model.
3. Stronger baselines next to persistence: the same week last year scaled by the recent ratio, and the 4-week
   mean.
4. MSP features for soybean, tur and wheat (the distance of the last price from the season's MSP; the file is in
   the dataset).
5. History from 2001 against history from 2016.

Rules and acceptance:
- Do not tune on the scored half: use the calibration half or an earlier fold.
- Adopt a change only if it improves skill on the untouched scored half.
- Accept when there is a written experiment log with every variant's table. Soybean must either stop being worse
  than persistence or stay abstained, never shown.

**D. Release and evidence.**
- Package and tag the release; build and run the image; run the request in section 6 and save the response.
- Send Hemanth and Kaushlendra the tag.
- Fill `evidence_packet/review_packet.md` and `runtime_logs/`, and correct the review-packet lines listed in A1.
- Accept when the release has its assets and notes, and Hemanth's integration check passes against your image.

**E. Replay for forecasts.**
- Record every `/v1/forecast` call (request id, model file, data hash, request, response) in a runtime folder, not
  `evidence_packet/`.
- Add a replay runner that re-asks and compares.
- Accept when a replay reproduces p10, p50 and p90 exactly.

**Not in scope:** any change to the AIAIC repository, a database on the VM, anything shown to farmers.

---

## 6. The data (sent separately: it is not committed anywhere)

**First, now: `pilot_v2/` (about 38 MB),** exported by AIAIC on 2026-10-02 from the official Agmarknet daily
prices (data.gov.in "Variety-wise Daily Market Prices", Government Open Data Licence - India). The numbers below
come from its `MANIFEST.json`.

| File | What |
|---|---|
| `agmarknet_pilot_mh_mp_2001_2026.csv.gz` | 3,563,963 rows, 2001-02-08 to 2026-08-26; onion, soybean, tur, wheat; Maharashtra and Madhya Pradesh. Every published row is kept with its source file and line (Agmarknet publishes several lots per mandi and day; none is a copy). |
| `mandi_identity.csv` | every (state, published market, district label) → `mandi`, `mandi_district`, and the rule used: 792 as published, 673 "X APMC" names folded, 1 name that is two mandis |
| `sources.csv` | the raw file behind each `source_file_id`, with its sha256 |
| `MANIFEST.json` | counts per state and crop, the spellings folded into each crop, column meanings, limits, the sha256 of each file |
| `msp_pilot_crops.csv` + `MSP_MANIFEST.json` | CACP MSP by marketing season. Wheat: Rabi Marketing Seasons 2019-20 to 2026-27, complete. Soybean and tur: 2018-19 to 2023-24 and 2025-26 (**2024-25 and 2026-27 missing**). Onion has no MSP |

Rows per state and crop (from the manifest):

| State | Crop | Rows | First | Last | Published names → mandis |
|---|---|---|---|---|---|
| Madhya Pradesh | onion | 159,345 | 2002-02-26 | 2026-08-26 | 369 → 258 |
| Madhya Pradesh | soybean | 695,271 | 2001-03-27 | 2026-08-26 | 505 → 284 |
| Madhya Pradesh | tur | 263,520 | 2001-05-21 | 2026-08-26 | 395 → 253 |
| Madhya Pradesh | wheat | 1,114,018 | 2001-03-27 | 2026-08-26 | 576 → 304 |
| Maharashtra | onion | 240,767 | 2001-02-08 | 2026-08-26 | 285 → 186 |
| Maharashtra | soybean | 353,310 | 2001-05-26 | 2026-08-26 | 555 → 346 |
| Maharashtra | tur | 320,028 | 2001-12-30 | 2026-08-26 | 555 → 339 |
| Maharashtra | wheat | 417,704 | 2001-03-30 | 2026-08-26 | 565 → 350 |

Read before training:
- Key series on `mandi` and `crop`. Never sum or count rows per day: in a renaming week the same quote is
  published under both names. Take one price per crop, mandi and day; your trainer already takes the median.
- "Red Gram" (Madhya Pradesh 2001-2016; Maharashtra 1,199 rows 2001-2008) is **not** in tur. Botanically red gram
  is tur, but at the same mandi on the same day the two names' prices are a median 0.99 apart and range 0.70 to 1.54
  times (p10 to p90): two series reported side by side, not the identical quotes the other spellings show. It waits
  for an agronomist's or the publisher's answer. The dals are excluded too.
- Wheat's MSP rows are Rabi Marketing Seasons: AIAIC's older MSP source filed rabi crops by crop year (its "2023-24",
  Rs 2,275, is RMS 2024-25). Your file is labelled by marketing season. Join an MSP to a price date by the season
  the date falls in.
- Coverage is thin in the early years. Prices are nominal rupees.

**Not available yet:** arrivals (tonnes traded). AIAIC holds no arrivals history: the daily price files carry no
arrivals column, and the only arrivals data on disk is one raw report for 30 Aug 2026 (about 19 rows, none for
Nashik), not ingested. Getting the Agmarknet price-and-arrival history for the pilot mandis is planned as a data
acquisition item. When it lands it will come with its own manifest, and you can test it as a feature.

---

## 7. The files in this folder

| Path | What to do |
|---|---|
| `aryan_review_2026-10-02.patch` | Apply with `git apply --index --whitespace=nowarn` (the `--index` stages the 3 deletions; see `CLEANUP_COMMANDS.md`) on `aiaic-forecast` at `efa3478`. Checked: it applies cleanly, and the rehearsed commands leave no address, notebook or data file in the commit. It contains everything in `replace/` plus the 3 deletions. |
| `replace/` | the same changes as plain files at their repository paths, if you prefer to copy |
| `final_suite.txt` | the full test run on the review branch with no model present |
| `CLEANUP_COMMANDS.md` | the exact commands, in your repository |

Files replaced or added:
- `.env.example`, `.gitignore`, `.dockerignore`
- `DEP.md`, `README.md`
- `docker/Dockerfile`, `docker/docker-compose.yml`, `requirements-serve.txt`
- `scripts/check_aiaic_backend.py`, `scripts/package_forecast_release.py`
- `src/api/{routes,schemas,main,forecast_routes}.py`, `src/forecast/{train,service}.py`
- redacted (address and user name): both `official_validation_suite_20261002T063823Z.txt`,
  `data/versions/pipeline_report.json`
- `tests/api/test_routes.py`, `tests/integration/{conftest,test_api_integration}.py`,
  `tests/forecast/test_one_mandi_is_one_series_across_a_rename.py`

Files deleted: `backend_checks.ipynb`, `scripts/check_aiaic_ngrok.py`, `scripts/package_forecast_backend_bundle.py`.
