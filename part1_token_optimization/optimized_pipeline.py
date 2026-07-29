"""
OPTIMIZED PIPELINE — same task, four concrete changes applied.

Change 1: PROMPT CACHING for static scaffolding
    System prompt, few-shot block, and tool schema are IDENTICAL every call.
    Mark them as a cached prefix (Anthropic prompt caching: cache_control on
    that content block). First call pays full price; every subsequent call in
    the loop pays ~10% of input-token price for that block instead of 100%.
    This alone doesn't shrink the token COUNT, but it changes the effective
    cost — noted separately in results.md. The token counts below still show
    the raw count so you can see both effects independently.

Change 2: RETRIEVAL INSTEAD OF FULL-FILE STUFFING
    Instead of dumping 8 full files (~400 lines each) into every step, run a
    cheap retrieval pass (embedding search or grep) and only pass the ~20-40
    line window around the relevant match, per file, and only for files
    actually relevant to the question. This is the single biggest lever.

Change 3: SUMMARIZE / DROP STALE HISTORY
    Don't replay raw tool outputs from prior steps. Keep a running, compact
    summary of what's been learned so far ("step 1: searched for retry logic,
    found duplicate charge happens when webhook handler doesn't check an
    idempotency key") instead of the full raw dump. Old raw outputs are
    discarded once their conclusion is folded into the summary.

Change 4: FEW-SHOT TRIMMING
    Six repeated few-shot examples -> one tight example. The model doesn't
    need 6 near-duplicate demonstrations of the same tool-call pattern.
"""

import re

SYSTEM_PROMPT_COMPACT = """You are a senior engineering assistant embedded in a codebase.
Tools: search_code, read_file, run_tests, get_git_blame, list_dir.
Think step by step, explain reasoning briefly, verify before concluding.
Style: short functions, descriptive names, no globals."""

FEW_SHOT_COMPACT = """
Example: User asks where rate limiting lives -> call search_code("rate limit") ->
found in middleware/throttle.py (token bucket + Redis) -> answer citing that file."""

TOOL_SCHEMA_COMPACT = (
    "Tools: search_code(query), read_file(path), run_tests(path), "
    "get_git_blame(path), list_dir(path)."
)


def fake_file_contents(name, n_lines=400):
    import random
    random.seed(hash(name) % 1000)
    lines = [f"    line_{i} = do_something_with_{name}_{i}()  # noqa" for i in range(n_lines)]
    return f"# --- {name} ---\n" + "\n".join(lines)


def retrieve_relevant_snippet(name: str, query_terms, window=15):
    """Simulates a real retrieval step: grep/embedding search for the relevant
    region of a file instead of returning the whole thing."""
    full = fake_file_contents(name)
    lines = full.split("\n")
    # naive relevance: pretend line ~ hash-derived "hit" index exists
    hit = (hash(name + "".join(query_terms)) % (len(lines) - window)) + 1
    snippet = lines[max(0, hit - window // 2): hit + window // 2]
    return f"# --- {name} (relevant excerpt, lines ~{hit}) ---\n" + "\n".join(snippet)


def is_relevant(filename: str, query: str) -> bool:
    """Cheap relevance filter — only files plausibly related to the question
    get included at all, instead of all 8 every time."""
    keywords = re.findall(r"[a-zA-Z]+", query.lower())
    return any(k in filename.lower() for k in keywords) or "webhook" in filename or "billing" in filename


RETRIEVED_FILES = [
    "auth/session.py", "auth/tokens.py", "billing/invoices.py",
    "billing/webhooks.py", "api/routes.py", "api/middleware.py",
    "db/models.py", "db/migrations/0042_add_index.py",
]


def build_optimized_context(user_question: str, step: int, running_summary: str) -> str:
    parts = [SYSTEM_PROMPT_COMPACT, FEW_SHOT_COMPACT, TOOL_SCHEMA_COMPACT]
    parts.append(f"User question: {user_question}")

    relevant = [f for f in RETRIEVED_FILES if is_relevant(f, user_question)]
    for f in relevant:
        parts.append(retrieve_relevant_snippet(f, user_question.split()))

    if running_summary:
        parts.append(f"Summary of progress so far: {running_summary}")

    parts.append(f"(Agent step {step}) Continue solving the task.")
    return "\n".join(parts)


if __name__ == "__main__":
    q = "Why are webhook retries duplicating invoice charges in billing/webhooks.py?"
    summary = ""
    final_ctx = ""
    for step in range(1, 4):
        ctx = build_optimized_context(q, step, summary)
        final_ctx = ctx
        # instead of appending raw tool output, we fold the conclusion into a
        # short running summary (this is what step N+1 will see, not the raw dump)
        summary += f" Step {step}: checked webhook handler, no idempotency key on retry."
    with open("/tmp/optimized_context.txt", "w") as f:
        f.write(final_ctx)
    print("wrote /tmp/optimized_context.txt, chars:", len(final_ctx))
