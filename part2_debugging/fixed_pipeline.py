"""
FIXED multi-step pipeline. Same steps as broken_pipeline.py, with targeted
fixes for each symptom, plus the structured logging that made isolating
these bugs possible in the first place.
"""
import random
import time
import uuid
import logging
from dataclasses import dataclass, field

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("pipeline")


class StepError(Exception):
    """A distinct error type -- a failed step is NEVER just an empty string
    or None flowing downstream. Fixes symptom 3 (silent wrong data)."""


@dataclass
class RunLogger:
    """Structured per-step logging with a correlation ID. This is what makes
    an 'intermittent' failure debuggable from logs alone instead of needing
    to catch it live."""
    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def step(self, name, **kv):
        parts = " ".join(f"{k}={v}" for k, v in kv.items())
        log.info(f"[run={self.run_id}] step={name} {parts}")


def call_with_timeout_and_backoff(fn, *args, timeout_s=2.0, max_retries=3):
    """Fixes symptom 1: every external call gets an explicit timeout AND a
    bounded retry count with backoff, instead of hanging or retrying forever."""
    last_exc = None
    for attempt in range(1, max_retries + 1):
        start = time.time()
        try:
            # In real code this would be e.g. requests.get(url, timeout=timeout_s)
            # or asyncio.wait_for(coro, timeout=timeout_s). Simulated here:
            if random.random() < 0.15 and attempt == 1:
                raise TimeoutError("simulated hung dependency")
            return fn(*args)
        except TimeoutError as e:
            last_exc = e
            wait = 0.1 * (2 ** (attempt - 1))
            time.sleep(min(wait, timeout_s))
    raise StepError(f"external call failed after {max_retries} attempts: {last_exc}")


def step_call_external_api(query: str) -> str:
    def _call(q):
        return f"raw_api_result_for::{q}"
    return call_with_timeout_and_backoff(_call, query)


def validate_summary_schema(obj: dict) -> dict:
    """Fixes symptom 2: strict validation right after generation, fail loud
    with the raw payload logged, instead of letting malformed output flow
    three steps downstream where the cause is no longer visible."""
    if not isinstance(obj, dict) or not obj.get("summary"):
        raise StepError(f"malformed summary output, raw={obj!r}")
    if "confidence" not in obj:
        raise StepError(f"summary missing required field 'confidence', raw={obj!r}")
    return obj


def step_generate_summary(raw_result: str) -> dict:
    if random.random() < 0.2:
        candidate = {"summary": None}  # simulated malformed model output
    else:
        candidate = {"summary": f"summary of {raw_result}", "confidence": 0.9}
    return validate_summary_schema(candidate)


def step_aggregate(summary_obj: dict) -> dict:
    # Fixes symptom 3: a validated summary is guaranteed non-empty by this
    # point (validate_summary_schema already raised otherwise), so there is
    # no "treat empty as valid" branch left to silently produce wrong data.
    return {"final_answer": summary_obj["summary"], "status": "success"}


def run_pipeline(query: str, logger: RunLogger = None) -> dict:
    logger = logger or RunLogger()
    try:
        t0 = time.time()
        raw = step_call_external_api(query)
        logger.step("call_external_api", latency_s=round(time.time() - t0, 3), ok=True)

        t0 = time.time()
        summary_obj = step_generate_summary(raw)
        logger.step("generate_summary", latency_s=round(time.time() - t0, 3), ok=True)

        result = step_aggregate(summary_obj)
        logger.step("aggregate", status=result["status"])
        return result

    except StepError as e:
        # Fail loud and traceable, not silently, and not generically --
        # the correlation ID ties this straight back to the per-step logs above.
        logger.step("PIPELINE_FAILED", error=str(e))
        return {"final_answer": None, "status": "error", "error": str(e), "run_id": logger.run_id}


if __name__ == "__main__":
    for i in range(8):
        print(run_pipeline(f"query_{i}"))
