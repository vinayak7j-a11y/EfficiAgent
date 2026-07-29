# Part 3.2 & 3.3 — Secrets Handling and Rollback Plan

## Secrets / API keys in the pipeline

- **Never in the repo, never in the YAML, never in logs.** All secrets live
  in GitHub's encrypted secret stores, injected as env vars only at the
  step that needs them (`env:` block on the `deploy-staging` job, not a
  global env — least privilege at the job level).
- **Environment-scoped secrets**, not repo-wide. `STAGING_DEPLOY_TOKEN`
  lives under the `staging` GitHub Environment, not as a repo-level secret.
  This means: (a) it's literally not exposed to jobs that don't declare
  `environment: staging`, and (b) I can add required reviewers / wait
  timers on that environment so a merge to main doesn't auto-deploy without
  a human able to see it happen.
- **Prefer OIDC over long-lived keys** where the cloud provider supports it
  (AWS, GCP, Azure all do). GitHub Actions can mint a short-lived token via
  OIDC (`permissions: id-token: write` in the workflow) instead of storing
  a long-lived cloud credential as a secret at all. This is the single
  biggest secrets-hygiene upgrade available — no static key to leak,
  rotate, or accidentally log.
- **Rotation:** any secret that *does* have to be long-lived gets rotated on
  a schedule and immediately on any suspected exposure (e.g. an accidental
  echo in a log, a fork PR that could see it — note: `pull_request` from
  forks never gets secrets by default in GitHub Actions, which is a
  built-in protection, but I don't rely on that alone).
- **Never in PR builds from forks.** Secrets are only available to the
  `push`-triggered jobs on trusted branches, not to `pull_request` runs
  from external forks (GitHub's default, kept intact here) — otherwise
  anyone opening a PR could exfiltrate secrets via a modified workflow.
- **Masking:** anything that touches a secret is checked for accidental
  `echo`/`print` of the value; GitHub auto-masks known secret strings in
  logs, but I don't rely on that as the only safety net — code review
  catches `env` blocks that pass secrets somewhere they don't need to go.

## Rollback plan — first 5 minutes if a deploy breaks production

Order of operations, fastest-safe-action first:

1. **(0–1 min) Stop the bleeding, don't diagnose yet.** Roll back to the
   last known-good deployment immediately — re-deploy the previous
   artifact/image tag, or flip a feature flag off if the change was
   flag-gated. I do not spend the first 5 minutes reading logs to find
   root cause; that happens after traffic is safe. Most platforms
   (ECS, Fly, Vercel, k8s) support a one-command "redeploy previous
   revision" — that command is the first thing run.
2. **(1–2 min) Confirm the rollback actually worked.** Hit the health
   endpoint / run the same smoke test the CI/CD pipeline runs post-deploy.
   Don't assume the rollback succeeded — verify it the same way you'd
   verify a forward deploy.
3. **(2–3 min) Communicate.** Post in the incident channel: what broke,
   what was rolled back to, current status. This runs in parallel with
   step 1/2, not after — someone else can start pulling logs while I'm
   still confirming the rollback.
4. **(3–5 min) Freeze further deploys** (branch protection / manual hold on
   the `staging`→`main` promotion path) until root cause is understood, so
   a second, unrelated deploy doesn't land on top of an active incident and
   muddy the investigation.
5. **After the 5-minute mark:** root-cause with the actual logs/traces from
   the broken deploy (kept, not discarded, specifically for this), write
   up what let it reach production despite CI passing (missing test case?
   staging didn't match prod config? a secret/config diff between
   staging and prod?), and add the missing check to CI so this class of
   break can't repeat silently.

**Why rollback-first, not fix-forward-first:** a fix written under
incident pressure, deployed straight to broken prod, is itself a risky
deploy. Reverting to a version that was already verified good is strictly
lower-risk than shipping a new untested fix while production is on fire.
