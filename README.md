# ora-grounding

Post-response grounding checks + cross-family adversarial review for
LLM chat agents. Zero framework opinions, zero database opinions —
bring your own persistence and your own LLM.

**Status:** 0.1.0 — early extraction from a production codebase. API
may still evolve. 34 unit tests, no runtime dependencies.

## Install

```bash
pip install -e .
```

## What it does

Two small, deterministic layers you can bolt on to any chat pipeline:

1. **Grounding check** — after your model replies, scan the reply for
   specific claims (file paths, symbol names, line numbers,
   slash-commands) that weren't in the retrieval context. Split into
   `fabricated` (does not exist) and `unverified` (exists but not
   retrieved this turn).
2. **Adversarial review** — for high-stakes turns, feed the draft to
   a different-family reviewer LLM. Every flag it emits is verified
   against the draft verbatim; hallucinated flags are dropped. Caller
   decides whether to regen once or attach caveats.

## Grounding check (30 seconds)

```python
from ora_grounding.grounding import run_post_response_check

async def canonical():
    # Whatever set of files you consider "the repo"
    return {"paths": {"src/foo.py"}, "basenames": {"foo.py"}, "defs": set()}

async def persist(row):
    await your_db.hallucinations.insert_one(row)

result = await run_post_response_check(
    user_id="u1", session_id="s1",
    query=user_question, reply=model_reply, route="chat",
    canonical_paths_provider=canonical,
    known_commands={"/read", "/find"},
    on_log=persist,          # optional
)
# → {"claims": [...], "fabricated": [...], "unverified": [...], "logged": True}
```

## Adversarial review (30 seconds)

```python
from ora_grounding.review import run_review, trigger_reason, corrective_prompt

async def call_reviewer(system, user):
    # Bring your own LLM client. Cross-family is strongly recommended
    # (e.g. Claude reviewing GPT, or GLM reviewing DeepSeek). Sibling
    # models share blind spots.
    resp = await your_llm.chat(system=system, user=user, temperature=0.0)
    return resp.text, resp.usage, resp.error

reason = trigger_reason(labels, grounding_result)  # or your own trigger
if reason:
    review = await run_review(
        user_id="u1", session_id="s1", query=q,
        draft=draft_text, context=retrieved_context,
        llm_call=call_reviewer,
        reason=reason,
    )
    if review["hard"]:
        # Optional: one silent regen using the corrective prompt.
        final = await your_llm.chat(
            system=drafter_system,
            user=corrective_prompt(review["hard"]))
    caveats = [f["quote"] for f in review["soft"]]
```

## Design principles

- **Deterministic where possible.** Claim extraction is pure regex.
  Grounding classification is set-membership. No LLM calls in the
  grounding hot path.
- **The reviewer is not trusted.** Every flag has its `quote` matched
  verbatim against the draft. Fake quote = dropped + logged.
- **Never raises.** Both entry points return structured results even
  on failure — the review pipeline is a defence, not a
  single-point-of-failure.
- **No I/O opinions.** Mongo, Postgres, S3, JSON files, whatever —
  you pass a `Callable[[dict], Awaitable[None]]` and we call it.
- **No LLM opinions.** OpenAI, Anthropic, OpenRouter, self-hosted vLLM
  — you pass a `Callable[[str, str], Awaitable[tuple]]` and we call
  it.

## Tests

```bash
pip install -e ".[dev]"
pytest -q
```

## License

MIT.
