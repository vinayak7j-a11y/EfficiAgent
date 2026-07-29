"""
BROKEN multi-step pipeline — intentionally reproduces the three symptoms
described in the brief, so the fixes in fixed_pipeline.py are demonstrably
targeting real problems, not strawmen.

Symptom 1 (timeout): step_call_external_api has no timeout at all, and no
    bound on retries -- a slow/hung dependency hangs the whole pipeline.
Symptom 2 (malformed output): step_generate_summary sometimes returns output
    that isn't parsed/validated, so a truncated or off-schema response
    passes straight through.
Symptom 3 (silent wrong data): step_aggregate treats a failed/empty upstream
    result as if it were valid data, instead of distinguishing "no result"
    from "empty but valid result".
"""
import random
import time


def step_call_external_api(query: str) -> str:
    # BUG: no timeout, no retry cap. A "flaky" dependency here hangs forever
    # or retries indefinitely, which is what causes the intermittent timeouts.
    if random.random() < 0.15:
        time.sleep(999)  # simulates a hung dependency
    return f"raw_api_result_for::{query}"


def step_generate_summary(raw_result: str) -> dict:
    # BUG: no schema validation. Sometimes "the model" (simulated here)
    # returns a truncated/malformed structure, and we don't check before
    # handing it downstream.
    if random.random() < 0.2:
        return {"summary": None}  # malformed / incomplete, unvalidated
    return {"summary": f"summary of {raw_result}", "confidence": 0.9}


def step_aggregate(summary_obj: dict) -> dict:
    # BUG: treats a failed/empty step as valid data instead of raising.
    # This is the "silent wrong data" case -- nothing crashes, nothing
    # alerts, the pipeline just returns a wrong-but-plausible-looking result.
    summary = summary_obj.get("summary") or "no data found"
    return {"final_answer": summary, "status": "success"}  # always "success"!


def run_pipeline(query: str) -> dict:
    raw = step_call_external_api(query)
    summary_obj = step_generate_summary(raw)
    return step_aggregate(summary_obj)


if __name__ == "__main__":
    for i in range(5):
        print(run_pipeline(f"query_{i}"))
