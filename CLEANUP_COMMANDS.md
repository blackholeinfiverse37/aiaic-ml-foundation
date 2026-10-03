# Aryan: commands to apply the review in YOUR repository (`aiaic-ml-foundation`)

Run them from the repository root, on a new branch, then open a pull request into `aiaic-forecast`. Every step was
run in a copy of your commit `efa3478` (2026-10-03), and the final search printed nothing.

```bash
git checkout aiaic-forecast
git pull
git checkout -b review-2026-10-02

# 1. apply the replacement files AND stage them: --index also stages the deletions
#    (backend_checks.ipynb, scripts/check_aiaic_ngrok.py, scripts/package_forecast_backend_bundle.py),
#    which a plain `git apply` would leave in the commit
git apply --index --whitespace=nowarn /path/to/aryan_review_2026-10-02.patch

# 2. stop tracking data, copies and bundles (the files stay on your disk; .gitignore now keeps them out)
git rm -r --cached --quiet "aryan files" out aiaic_forecast.patch \
    evidence_packet/backend_integration_bundle_20261002.zip \
    evidence_packet/backend_integration_bundle/model \
    evidence_packet/backend_integration_bundle/history

# 3. before committing: nothing about to be committed may hold a tunnel address or a personal path.
#    Both commands must print NOTHING.
git grep -n --cached -E 'ngrok-free\.dev|ngrok\.io|ngrok\.app'
git grep -n --cached -E '[Cc]:[\\/]+Users[\\/]+[A-Za-z]'

# 4. prove it with NO model present (move models/forecast_* aside first if you have them)
pytest tests -q                       # expect: all passed; `git status` shows nothing new in evidence_packet/

# 5. commit (everything is already staged by --index; check that no data file is)
git status
git commit -m "Forecast is the served model: /v1/predict retired, deployable image with checksummed model, mandi/crop identity, clean-clone tests, no addresses in the repository"
git push -u origin review-2026-10-02
```

**What the patch changes in your evidence.** The two copies of
`official_validation_suite_20261002T063823Z.txt` (in `evidence_packet/runtime_logs/` and in the bundle's `proof/`)
and `data/versions/pipeline_report.json` keep their content. The tunnel address is replaced by
`<AIAIC laptop tunnel address, redacted 2026-10-03>`, and the Windows user name in paths by `<user>`.

Then, still in your repository:

- Keep the bundle's `proof/` files (they are evidence). The model and history go on the GitHub release, not in git.
- Optional: of the 81 committed files in `evidence_packet/replay_logs/`, most were written by test runs of the
  retired `/v1/predict`. Keep one or two real ones as Test 1 evidence and remove the rest.
- The address stays in the repository's **history** after these commits. Whether the tunnel itself is changed is
  Hemanth's decision. Do not rewrite history unless he asks.
- Correct the lines listed in finding A1 of `ARYAN_NEXT_TASK_2026-10-02.md` in `review_packet/`, and fill
  `evidence_packet/review_packet.md`.

## The first release, once the pilot model is trained (DEP.md section 4)

```bash
python scripts/package_forecast_release.py --from models/forecast_pilot     # writes models/release/ and checks it
docker compose -f docker/docker-compose.yml up --build -d
curl http://127.0.0.1:8040/v1/ready
gh release create forecast-v2026.10.XX models/release/* --title "Forecast pilot v1" \
    --notes-file models/release/RELEASE.json
```

Send Hemanth and Kaushlendra the tag.
