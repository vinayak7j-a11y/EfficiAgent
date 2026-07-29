# Part 2 — Debugging an Intermittently Failing Multi-Step Agent Pipeline

Symptoms given: sometimes times out, sometimes returns malformed output,
sometimes silently succeeds with wrong data. Three different symptoms
usually means **more than one root cause** — I don't try to find "the" bug,
I isolate per-symptom.

## Step 0 — Before touching code: can I even see what happened?
If there's no structured logging / tracing, that's the first fix, before
any further debugging, because otherwise every subsequent step is guessing.
Minimum bar per run: a **correlation/run ID**, and for every step: which
step, input, output, latency, token usage, model/tool version, timestamp.
Without this, "intermittent" bugs are nearly undebuggable — you're trying
to reproduce a race condition from vibes.

`fixed_pipeline.py` in this folder adds exactly this (see `RunLogger`).

## Step 1 — Reproduce, or bucket by frequency
- Pull the last ~50-100 failing runs from logs/traces (not just the one
  someone reported). Bucket them: timeout vs malformed vs wrong-data.
  These are almost certainly three different bugs with different fixes.
- Check if failures correlate with anything: time of day (rate limits?),
  specific input shape (long inputs? specific user?), specific step in the
  pipeline (always step 3? or random?). This alone often points straight
  at the cause.

## Step 2 — Isolate: TIMEOUTS
- Check: is the timeout constant across failures, or does it grow with
  input size? Constant -> likely a hung dependency (network call, tool,
  DB) with no timeout of its own, or a retry loop with no backoff cap.
  Grows with input -> likely a real latency problem (context too large,
  see Part 1) hitting a fixed client-side timeout.
- Pull: per-step latency from logs. If one step is consistently the slow
  one, look at *that* step's external dependency (is it calling a flaky
  third-party API with no timeout set on the HTTP client itself?).
- Common root cause I check for first: a tool/API call with **no explicit
  timeout set**, so it inherits an OS-level default (or none), and the
  pipeline's own timeout fires from *outside* without ever cancelling the
  underlying call — so it also leaks connections, making it worse over time.

## Step 3 — Isolate: MALFORMED OUTPUT
- Check: is it malformed JSON (parsing fails outright) or malformed
  *shape* (parses, but missing/extra fields)? Different causes.
- Parsing fails: almost always the model's output got truncated
  (hit max_tokens mid-JSON) or wrapped in markdown fences an unstrict
  parser didn't expect, or a prior step's error message leaked into what
  should have been pure structured output.
- Shape wrong: usually a prompt/schema drift — someone changed the schema
  in code but not in the prompt (or vice versa), or the model was given an
  example that doesn't match the current schema.
- Fix pattern I reach for: **strict schema validation immediately after
  each step**, fail loud right there (not three steps later where the
  original cause is gone from context), and log the raw pre-parse output
  so you can see exactly what the model actually returned.

## Step 4 — Isolate: SILENT WRONG DATA (the dangerous one)
This is the worst of the three because nothing *fails* — no alert fires.
- Check: was there a step where the model was asked to do something
  underspecified, and it filled the gap with a plausible-but-wrong
  guess? Silent wrong data in agent pipelines is very often not a "bug"
  in the traditional sense — it's the model doing exactly what a loose
  prompt/schema allowed it to do.
- Pull: a few known-good vs known-bad runs side by side, diff the full
  context sent at each step. Look specifically for: was an earlier step's
  *error* silently treated as data (e.g. a tool call failed, returned an
  empty/error string, and downstream steps happily used that empty string
  as if it were a valid result)?
- Fix pattern: add **invariant checks / assertions between steps**, not
  just at the very end — e.g. "if search_code returned 0 results, that is
  not the same as 'no relevant code exists,' don't let the next step treat
  it as such." Also add idempotency/consistency checks where possible
  (checksums, "does this output reference IDs that actually exist").

## Step 5 — Isolate whether it's non-determinism vs. environment
- Re-run the exact same input 10x with logged intermediate state. If it's
  flaky on identical input -> model non-determinism or a race condition
  (e.g. shared mutable state across concurrent agent runs, a cache being
  read before it's written). If it's consistent on identical input but
  flaky across different inputs -> input-dependent bug, go back to Step 1's
  bucketing and look at what's different about the failing inputs
  specifically (length? special characters? a particular tool being
  invoked?).

## Tools/logs I'd actually pull, concretely
1. Structured per-step logs with correlation ID (see `RunLogger` below)
2. Raw request/response payloads for the LLM calls on failing runs
   (not just the parsed/processed result — the exact bytes sent and received)
3. Timing breakdown per step (to separate "slow model call" from "slow tool
   call" from "slow retry loop")
4. A small repro harness that replays a captured failing input outside the
   full system, to rule out infra noise (queueing, autoscaling, etc.)
5. If available: tracing (OpenTelemetry-style spans per step) so I can see
   nested calls, not just top-level pipeline duration

## Concrete fixes applied in `fixed_pipeline.py`
- Explicit timeout + bounded retry with backoff on every external call
  (was previously unbounded / relying on defaults)
- Strict output schema validation right after each step, fail fast with
  the raw output logged, instead of letting bad data flow downstream
- Errors from a step are never silently treated as valid data by the next
  step — an error result is a distinct type, not an empty success
- `RunLogger` gives every run a correlation ID and logs input/output/latency
  per step, so the next "intermittent" bug is debuggable from logs alone
