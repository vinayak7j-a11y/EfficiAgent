# Part 1 — Token Optimization Results

## How to reproduce
```
cd part1_token_optimization
python3 token_comparison.py
```

## Measured numbers (this repo's synthetic scenario)

| | tokens (final agent step) |
|---|---|
| Before (naive) | ~57,800 |
| After (optimized) | ~2,100 |
| Reduction | ~96% |

Note on measurement: this sandbox has no network egress to tiktoken's blob
store, so the script falls back to the standard `chars/4` estimator when
`tiktoken` can't download its BPE file. On a machine with normal internet
access, `token_comparison.py` will automatically use exact `cl100k_base`
token counts instead — the code already handles both, no changes needed.

The 96% number is inflated by how extreme I made the synthetic "before" case
(8 full 400-line files re-dumped every step, 6 near-duplicate few-shot
examples, full raw history replay) to make each optimization's effect
visible in isolation. On a real pipeline burning 100K tokens/query, I'd
expect realistic gains in the **40–70%** range per optimization layer,
compounding — not because the technique is weaker, but because a real
system already has *some* discipline and less pure waste to cut.

## The four changes, and their tradeoffs

### 1. Retrieval instead of full-file stuffing (biggest lever)
Instead of dumping entire files into context, run a cheap retrieval pass
(grep, embedding search, or symbol lookup) and only pass the relevant
window (~15–40 lines) plus a `is_relevant()` filter so files unrelated to
the question aren't included at all.
- **Tradeoff:** if retrieval misses the truly relevant chunk (bad query,
  bad embedding), the agent can miss context it would've had before. This
  is a *recall* risk, not a formatting risk — output can be confidently
  wrong rather than obviously broken. Mitigate with: a fallback "expand
  window" tool call the agent can trigger if it says it needs more, and
  eval against a labeled set of "what should have been retrieved" cases.

### 2. Summarize/drop stale history instead of replaying raw tool outputs
Once a tool call's result has been "used" (its conclusion folded into
reasoning), don't keep re-sending the raw output on every subsequent step —
replace it with a one-line summary in a running scratchpad.
- **Tradeoff:** lossy compression. If step 5 needs a precise detail from
  step 1's raw output (an exact line number, an exact stack trace), the
  summary might not have preserved it. Mitigate with: summarize with an
  explicit "preserve exact identifiers/errors verbatim" instruction, or
  keep raw output addressable by ID so the agent can re-fetch it on demand
  instead of it living in context by default.

### 3. Trim redundant few-shot examples
6 near-duplicate examples of the same tool-call pattern -> 1 tight example.
- **Tradeoff:** near-zero for well-covered patterns. Real risk is if those
  extra examples were quietly covering edge cases (e.g. handling a tool
  error, handling an empty result) — cutting them can regress behavior on
  exactly those edge cases. Mitigate with: keep one example per *distinct*
  behavior you need, not per repetition of the same behavior.

### 4. Prompt caching for static scaffolding (cost, not token-count)
System prompt, tool schema, and the trimmed few-shot block are byte-identical
across every step of a run. Marked as a cached prefix, the first call pays
full input price; every following call in that agent loop pays roughly 10%
of input-token price for that cached span (Anthropic's prompt caching).
- **This doesn't reduce token *count*** — it reduces the effective *cost*
  per token for the reused portion. Complementary to changes 1–3, not a
  substitute. No quality tradeoff: content is byte-identical, just billed
  differently. The only "cost" is a bit of engineering discipline to keep
  the cached prefix stable (any edit to system prompt/tools invalidates the
  cache for that turn).

## What I'd measure in production before shipping this
- Token count before/after (this repo shows the mechanism)
- **Task success rate** before/after on a held-out eval set — retrieval and
  summarization are the two changes with real quality risk; caching and
  few-shot trimming are close to free.
- p50/p95 latency (fewer tokens in = faster time-to-first-token, and less
  reprocessing on multi-turn loops)
- $ per successful query, not just $ per query — a cheaper-but-more-often-wrong
  pipeline is not actually cheaper once you count retries/escalations to a human.
