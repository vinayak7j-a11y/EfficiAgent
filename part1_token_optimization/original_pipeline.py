"""
ORIGINAL PIPELINE — the expensive version.

Simulates a multi-step research agent that answers a question about a codebase.
It works, but it is naive about context: every step re-sends everything.

Symptoms that make this expensive:
1. Full conversation history (including every prior tool call + raw tool output)
   is re-sent on every single LLM call in the loop.
2. Retrieved documents are stuffed in FULL, even when only a few paragraphs
   are relevant (no retrieval/ranking, just "grab 8 files and paste them").
3. The tool schema + a long few-shot example block is repeated in every call,
   because the agent framework rebuilds the system prompt each turn.
4. No caching — identical static content (system prompt, tool defs, few-shots)
   is retokenized and rebilled every call even though it never changes.

This file builds the exact strings that would be sent to the model, so we can
count real tokens with tiktoken instead of guessing.
"""

import random

# ---- Static scaffolding that gets repeated on EVERY call in the naive version ----

SYSTEM_PROMPT = """You are a senior engineering assistant embedded in a codebase.
You have access to tools: search_code, read_file, run_tests, get_git_blame, list_dir.
Always think step by step. Always explain your reasoning in detail before acting.
Never skip verification steps. Follow the coding style guide exactly as described below.
""" + ("Style rule: keep functions short, use descriptive names, avoid globals. " * 40)

FEW_SHOT_EXAMPLES = ("""
Example interaction:
User: Where is the rate limiter implemented?
Assistant: I will search the codebase for rate limiting logic.
[calls search_code(query="rate limit")]
Tool result: found matches in middleware/throttle.py, utils/limiter.py
Assistant: The rate limiter is implemented in middleware/throttle.py using a token
bucket algorithm, backed by Redis for distributed state...
""" * 6)

TOOL_SCHEMA_BLOCK = str({
    "tools": [
        {"name": "search_code", "params": {"query": "string"}},
        {"name": "read_file", "params": {"path": "string"}},
        {"name": "run_tests", "params": {"path": "string"}},
        {"name": "get_git_blame", "params": {"path": "string"}},
        {"name": "list_dir", "params": {"path": "string"}},
    ]
}) * 3  # naive frameworks often duplicate this in system + tool-choice + docs

# ---- Simulated "full file" tool outputs (raw, unfiltered) ----

def fake_file_contents(name, n_lines=400):
    random.seed(hash(name) % 1000)
    lines = [f"    line_{i} = do_something_with_{name}_{i}()  # noqa" for i in range(n_lines)]
    return f"# --- {name} ---\n" + "\n".join(lines)

RETRIEVED_FILES = [
    "auth/session.py", "auth/tokens.py", "billing/invoices.py",
    "billing/webhooks.py", "api/routes.py", "api/middleware.py",
    "db/models.py", "db/migrations/0042_add_index.py",
]

def build_naive_context(user_question: str, step: int, history: list) -> str:
    """Rebuilds the FULL context every step: system + few-shot + tool schema +
    every prior message + every raw file dump, all over again."""
    parts = [SYSTEM_PROMPT, FEW_SHOT_EXAMPLES, TOOL_SCHEMA_BLOCK]
    parts.append(f"User question: {user_question}")

    # naive: dump ALL retrieved files in full, every step, even ones from step 1
    for f in RETRIEVED_FILES:
        parts.append(fake_file_contents(f))

    # naive: replay entire raw history (including old tool outputs) verbatim
    for h in history:
        parts.append(h)

    parts.append(f"(Agent step {step}) Continue solving the task.")
    return "\n".join(parts)


if __name__ == "__main__":
    history = []
    q = "Why are webhook retries duplicating invoice charges in billing/webhooks.py?"
    total_ctx = ""
    for step in range(1, 4):
        ctx = build_naive_context(q, step, history)
        total_ctx = ctx  # last step's context is what we measure (worst case, cumulative)
        history.append(f"[step {step} raw tool output]\n" + fake_file_contents(f"scratch_{step}", 150))
    with open("/tmp/naive_context.txt", "w") as f:
        f.write(total_ctx)
    print("wrote /tmp/naive_context.txt, chars:", len(total_ctx))
