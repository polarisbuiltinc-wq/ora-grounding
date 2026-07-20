# ora-grounding

> Deterministic post-response grounding checks + cross-family adversarial review for LLM chat agents.
> Zero framework opinions, zero database opinions -- bring your own persistence and your own LLM.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://github.com/polarisbuiltinc-wq/ora-grounding/actions/workflows/tests.yml/badge.svg)](https://github.com/polarisbuiltinc-wq/ora-grounding/actions/workflows/tests.yml)
[![Zero deps](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](./pyproject.toml)

**Status:** 0.1.0 -- early extraction from a production codebase. API may still evolve. 34 unit tests, no runtime dependencies.

---

## Why?

LLMs hallucinate confidently. Two failure modes hurt users the most:

1. **Made-up specifics** -- "Fix at `services/auth.py:42`" when the file doesn't exist.
2. **Overconfident synthesis** -- the model stitches together plausible-sounding claims that no source in its context actually supports.

Prompting alone doesn't fix this. Sibling-model review doesn't fix it either -- GPT reviewing GPT shares blind spots. This library adds two deterministic defences that sit *outside* the model:

- A **cheap grounding check** (regex + set-membership, no LLM in the hot path) that catches file/symbol/line-number/command claims not backed by the context you retrieved.
- An **adversarial review** by a *different-family* reviewer LLM, with a hard, deterministic guard against the reviewer itself hallucinating flags (every flag's quote must appear in the draft, verbatim).

Extracted from a production AI-CTO assistant serving real users. Battle-tested against actual regressions.

---

## Install

```bash
pip install -e .
```

*(PyPI package coming. For now install from source or as a git dependency.)*

## What it does

Two small, deterministic layers you can bolt on to any chat pipeline:

1. **Grounding check** -- after your model replies, scan the reply for specific claims (file paths, symbol names, line numbers, slash-commands) that weren't in the retrieval context. Split into `fabricated` (does not exist) and `unverified` (exists but not retrieved this turn).
2. **Adversarial review** -- for high-stakes turns, feed the draft to a *different-family* reviewer LLM. Every flag it emits is verified against the draft verbatim; hallucinated flags are dropped. Caller decides whether to regen once or attach caveats.

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
# returns: {"claims": [...], "fabricated": [...], "unverified": [...], "logged": True}
```

## Adversarial review (30 seconds)

```python
from ora_grounding.review import run_review, trigger_reason, corrective_prompt

async def call_reviewer(system, user):
    # Bring your own LLM client. Cross-family is strongly recommended
    # (e.g. Claude reviewing GPT, or Gemini reviewing DeepSeek). Sibling
    # models share blind spots.
    resp = await your_llm.chat(system=system, user=user, temperature=0.0)
    return resp.text, resp.usage, resp.error

reason = trigger_reason(labels, grounding_result)   # or your own trigger
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

- **Deterministic where possible.** Claim extraction is pure regex. Grounding classification is set-membership. No LLM calls in the grounding hot path.
- **The reviewer is not trusted.** Every flag has its `quote` matched verbatim against the draft. Fake quote = dropped + logged.
- **Never raises.** Both entry points return structured results even on failure. The review pipeline is a defence, not a single-point-of-failure.
- **No I/O opinions.** Mongo, Postgres, S3, JSON files, whatever. You pass a `Callable[[dict], Awaitable[None]]` and we call it.
- **No LLM opinions.** OpenAI, Anthropic, OpenRouter, self-hosted vLLM. You pass a `Callable[[str, str], Awaitable[tuple]]` and we call it.

## When you probably don't need this

- Your agent doesn't reference files, symbols, or specific commands (no verifiable claims, nothing to check).
- You're already running a heavy guardrails framework (NeMo Guardrails, Guardrails AI, LlamaIndex Correctness). This library is deliberately *tiny* -- about 500 lines, no deps. It complements, doesn't replace, those.
- You only ever run a single-model pipeline and can't afford a second LLM call. The grounding check works standalone; the review layer is optional.

## Comparison with alternatives

| Feature                                | ora-grounding                | LLM-as-Judge      | RAG-style retrieval        |
| -------------------------------------- | ---------------------------- | ----------------- | -------------------------- |
| Deterministic core                     | Yes (regex + set-membership) | No (LLM opinion)  | Partial (retrieval varies) |
| Catches file/symbol hallucinations     | Yes                          | Inconsistent      | No                         |
| Reviewer self-hallucination guard      | Yes (verbatim quote check)   | No                | n/a                        |
| Runtime dependencies                   | 0                            | LLM SDK           | Vector DB + embed model    |
| Lines of code                          | ~500                         | varies            | thousands                  |

## Tests

```bash
pip install -e ".[dev]"
pytest -q
```

34 tests. Runs in under 100 ms. No LLM calls in tests (reviewer is mocked via caller-supplied callable).

## Roadmap

- [ ] Publish to PyPI (`pip install ora-grounding`)
- [ ] Optional streaming variant of `run_review` for latency-sensitive pipelines
- [ ] JSON-schema claim extractor for structured tool-use replies
- [ ] Ready-made adapters for popular vector stores (`canonical_paths_provider` implementations)

Have a use-case that doesn't fit? Open an issue.

## Contributing

Contributions welcome, especially:

- Adapter implementations (Postgres, Redis, S3 loggers)
- Additional claim extractors (URL claims, package/version claims)
- Real-world reviewer-error patterns you've seen in production

Please add a test with any PR. Keep the "zero runtime deps" invariant intact.

## Credits

Extracted from the ORA Chat assistant powering [AUREM CTO](https://auremcto.com). The library is a distillation of about 5 iterations of dogfooding what it takes to make a chat agent stop making things up.

## License

MIT. See [LICENSE](./LICENSE).
