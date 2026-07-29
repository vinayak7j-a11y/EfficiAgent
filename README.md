# EfficiAgent — Cost, Debugging, Deployment

This repo covers all three parts of the assignment. Each part has its own
detailed doc; this README is the map + the "why."

## Part 1 — Token/Cost Optimization
`part1_token_optimization/`
- `original_pipeline.py` — simulates the naive 100K-token agent context
  (full file dumps, replayed raw history, repeated few-shot/tool scaffolding)
- `optimized_pipeline.py` — same task, four concrete fixes applied:
  retrieval instead of full-file stuffing, summarized history instead of
  raw replay, trimmed few-shot examples, and prompt caching for static
  scaffolding
- `token_comparison.py` — run this to get real before/after counts
- `results.md` — the actual numbers, and an honest writeup of the quality
  tradeoff each optimization introduces (not "free lunch" framing)

Run it:
```
cd part1_token_optimization && python3 token_comparison.py
```

## Part 2 — Debugging
`part2_debugging/`
- `DEBUGGING.md` — the step-by-step process: bucket failures by symptom
  (timeout / malformed / silent-wrong-data) before assuming one root
  cause, what logs/tools I pull, how I isolate each symptom specifically
- `broken_pipeline.py` — a small pipeline that actually reproduces all
  three symptoms (unbounded retry/no timeout, unvalidated output, errors
  silently treated as valid data)
- `fixed_pipeline.py` — same pipeline with targeted fixes for each symptom
  plus structured per-run logging (`RunLogger`), because "intermittent"
  bugs are undebuggable without correlation IDs and per-step logs in the
  first place

Run it:
```
cd part2_debugging && python3 broken_pipeline.py   # can hang/produce bad data
python3 fixed_pipeline.py                          # fails loud & logged instead
```

## Part 3 — CI/CD and Deployment
- `.github/workflows/ci-cd.yml` — lint + test on every push; deploy to a
  `staging` GitHub Environment on merge to `main`, gated behind the test
  job passing, with a post-deploy smoke test before the job is allowed
  to go green
- `app.py`, `test_app.py`, `requirements.txt`, `pyproject.toml` — the
  small sample app the pipeline builds/tests/lints/deploys
- `DEPLOYMENT.md` — secrets handling (Environment-scoped secrets, OIDC
  preference over long-lived keys, why forked PRs never see secrets) and
  the rollback plan for the first 5 minutes after a bad prod deploy

Run tests/lint locally exactly as CI does:
```
pip install -r requirements.txt
ruff check .
pytest -v
```

## Honest scope notes
- The "provided repo" for Part 3 didn't exist as a file, so I built a
  minimal Flask app to give the pipeline something real to lint/test/deploy
  against, rather than writing YAML against nothing.
- The deploy step in `ci-cd.yml` is intentionally generic (no specific
  cloud target was specified) — swap the placeholder deploy command for
  your actual platform's CLI (Fly, ECS, Railway, k8s, etc.); the
  structure (test gate → environment-scoped secret → deploy → smoke test)
  stays the same regardless of target.
- Part 1's "before" numbers use a deliberately extreme synthetic example
  so each optimization's individual effect is visible in isolation —
  `results.md` is explicit that real-world gains will be smaller than the
  raw percentage shown here, and says what I'd actually measure
  (task success rate, not just token count) before shipping this.
