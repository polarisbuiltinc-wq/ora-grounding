<div align="center">

# ora-grounding

### Your LLM agent is lying to you with confidence. This catches it.

Deterministic post-response grounding checks + cross-family adversarial review for LLM chat agents — zero deps, bring your own LLM and your own database.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow?style=flat-square)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/github/actions/workflow/status/polarisbuiltinc-wq/ora-grounding/tests.yml?style=flat-square&label=tests)](https://github.com/polarisbuiltinc-wq/ora-grounding/actions/workflows/tests.yml)
[![Zero deps](https://img.shields.io/badge/dependencies-zero-brightgreen?style=flat-square)](pyproject.toml)
[![~500 LOC](https://img.shields.io/badge/size-~500%20LOC-informational?style=flat-square)](src/ora_grounding)

**[Quick start](#-30-second-demo) · [Why](#-why-this-exists) · [Docs](#-usage) · [Compare](#-vs-the-alternatives) · [Roadmap](#-roadmap)**

</div>

<br>

## 🔍 30-second demo

This is an **anonymized real production case** — a chat agent claimed a
file existed that didn't. Here's `ora-grounding` catching it, deterministically, with zero LLM calls in the check itself:

```python
>>> from ora_grounding.grounding import extract_claims, classify_claims
>>>
>>> reply = "Fixed the retry logic in payments_client.py — added dedup via redis_lock.py"
>>>
>>> canonical = {
...     "paths": {"src/payments_client.py"},   # redis_lock.py does NOT exist
...     "basenames": {"payments_client.py"},
...     "defs": set(),
... }
>>>
>>> classify_claims(extract_claims(reply), canonical=canonical)
{'fabricated': ['redis_lock.py'], 'unverified': []}
```

**One real file. One invented file. Caught instantly.** That's the whole pitch — everything below is detail.

<br>

## 💥 Why this exists

LLMs hallucinate *confidently*. Two failure modes hurt users the most:

| Failure mode | What it looks like |
|---|---|
| **Made-up specifics** | "Fix at `services/auth.py:42`" — the file doesn't exist. |
| **Overconfident synthesis** | The model stitches together plausible claims nothing in its context supports. |

Prompting alone doesn't fix this. **Sibling-model review doesn't fix it either** — GPT reviewing GPT shares blind spots. `ora-grounding` adds two deterministic defences that sit *outside* the model:

- 🧮 **Cheap grounding check** — regex + set-membership, **no LLM in the hot path**. Catches file/symbol/line-number/command claims the retrieval context never supported.
- 🥊 **Adversarial review** — a *different-family* reviewer LLM hostile-reads the draft, with a hard deterministic guard against the reviewer itself hallucinating flags.

> Extracted from a production AI-CTO assistant serving real users. Battle-tested against actual regressions — including the one above.

<br>

## 📦 Install

```bash
pip install -e .
```
> PyPI package coming. For now: install from source or as a git dependency.

<br>

## 🧩 What it does

<table>
<tr>
<td width="50%" valign="top">

### 1️⃣ Grounding check
After your model replies, scan it for specific, checkable claims — file paths, symbols, line numbers, slash-commands — that weren't in the retrieval context.

Splits results into:
- `fabricated` — doesn't exist anywhere
- `unverified` — exists, just wasn't retrieved this turn

</td>
<td width="50%" valign="top">

### 2️⃣ Adversarial review
For high-stakes turns, a **different-family** reviewer LLM hostile-reads the draft.

Every flag it raises must quote the draft **verbatim** — a flag whose quote doesn't match gets dropped as a reviewer hallucination.

</td>
</tr>
</table>

<br>

## 🚀 Usage

### Grounding check

```python
from ora_grounding.grounding import run_post_response_check

async def canonical():
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

### Adversarial review

```python
from ora_grounding.review import run_review, trigger_reason, corrective_prompt

async def call_reviewer(system, user):
    # Bring your own client. Cross-family strongly recommended —
    # Claude reviewing GPT, Gemini reviewing DeepSeek. Siblings share blind spots.
    resp = await your_llm.chat(system=system, user=user, temperature=0.0)
    return resp.text, resp.usage, resp.error

reason = trigger_reason(labels, grounding_result)
if reason:
    review = await run_review(
        user_id="u1", session_id="s1", query=q,
        draft=draft_text, context=retrieved_context,
        llm_call=call_reviewer, reason=reason,
    )
    if review["hard"]:
        final = await your_llm.chat(
            system=drafter_system,
            user=corrective_prompt(review["hard"]))
    caveats = [f["quote"] for f in review["soft"]]
```

<br>

## ⚙️ Design principles

- 🎯 **Deterministic where possible** — pure regex + set-membership. No LLM calls in the grounding hot path.
- 🚫 **The reviewer is not trusted** — every flag's quote is verified verbatim against the draft. Fake quote = dropped + logged.
- 🛡️ **Never raises** — both entry points return structured results even on internal failure.
- 🔌 **Zero I/O opinions** — Mongo, Postgres, S3, flat files, whatever. Pass a callable, we call it.
- 🔌 **Zero LLM opinions** — OpenAI, Anthropic, OpenRouter, self-hosted. Pass a callable, we call it.

<br>

## 🆚 vs. the alternatives

| | `ora-grounding` | LLM-as-Judge | RAG-style retrieval |
|---|:---:|:---:|:---:|
| Deterministic core | ✅ | ❌ | ⚠️ Partial |
| Catches file/symbol hallucinations | ✅ | ⚠️ Inconsistent | ❌ |
| Reviewer self-hallucination guard | ✅ | ❌ | n/a |
| Runtime dependencies | **0** | LLM SDK | Vector DB + embed model |
| Lines of code | **~500** | Varies | Thousands |

<br>

## 🙅 When you probably don't need this

- Your agent never references files, symbols, or commands — nothing verifiable to check.
- You already run a heavyweight guardrails framework (NeMo Guardrails, Guardrails AI). This is deliberately *tiny* — it complements those, doesn't replace them.
- You can't afford a second LLM call at all. The grounding check works fully standalone; review is optional.

<br>

## 🧪 Tests

```bash
pip install -e ".[dev]"
pytest -q
```
**34 tests. Under 100ms. Zero LLM calls in the test suite** — the reviewer is mocked via your own injected callable.

<br>

## 🗺️ Roadmap

- [ ] Publish to PyPI (`pip install ora-grounding`)
- [ ] Streaming variant of `run_review` for latency-sensitive pipelines
- [ ] JSON-schema claim extractor for structured tool-use replies
- [ ] Ready-made adapters for popular vector stores

Have a use-case that doesn't fit? [Open an issue](../../issues).

<br>

## 🤝 Contributing

Especially welcome:
- Adapter implementations (Postgres, Redis, S3 loggers)
- New claim extractors (URLs, package/version claims)
- Real-world reviewer-error patterns you've hit in production

Add a test with any PR. Keep the zero-runtime-deps invariant intact.

<br>

<div align="center">

---

Extracted from the ORA Chat assistant powering **[AUREM CTO](https://auremcto.com)** — a distillation of ~5 iterations of dogfooding what it actually takes to make a chat agent stop making things up.

**MIT Licensed** · [LICENSE](LICENSE)

</div>
