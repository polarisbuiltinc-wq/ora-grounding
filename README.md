// double-click race test v5
// QA regression test marker
# aurem qa countdown proof
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

## 🚀 Usage

### Install

```bash
pip install ora-grounding
```

Zero dependencies. Python 3.10+.

### Quick start

```python
from ora_grounding.grounding import extract_claims, classify_claims

# 1. Your agent generates a reply
reply = "Fixed auth in backend/routers/auth.py line 42"

# 2. Build the canonical set from your retrieval context
canonical = {
    "paths": {"backend/routers/auth.py"},
    "basenames": {"auth.py"},
    "defs": {"verify_token", "login"},
}

# 3. Check
claims = extract_claims(reply)
result = classify_claims(claims, canonical=canonical)

if result["fabricated"]:
    print(f"⚠️  Fabricated: {result['fabricated']}")
```

### Adversarial review

```python
from ora_grounding.review import adversarial_review

# After the grounding check passes, run a cross-family review
review_result = adversarial_review(
    draft_reply=reply,
    retrieval_context=your_rag_chunks,
    reviewer_llm=your_llm_client,  # Different family from the drafter
)

if review_result["flags"]:
    print(f"🚩 Review flags: {review_result['flags']}")
```

<br>

## 📊 Vs. the alternatives

| Approach | Speed | Catches fabricated paths | Catches overconfident synthesis | Cross-family |
|---|---|---|---|---|
| **Prompting alone** | Fast | ❌ | ❌ | N/A |
| **Sibling-model review** | Slow | ⚠️ | ⚠️ | ❌ |
| **ora-grounding** | Fast (grounding) + Slow (review) | ✅ | ✅ | ✅ |

- **Prompting alone** — "Be accurate. Don't hallucinate." — doesn't work. The model doesn't *know* it's hallucinating.
- **Sibling-model review** — GPT-4 reviewing GPT-4 shares blind spots. Same training data, same failure modes.
- **ora-grounding** — Deterministic check (fast) + adversarial review (slow, opt-in) with a different-family reviewer.

<br>

## 🗺️ Roadmap

- [x] Deterministic grounding check
- [x] Adversarial review with cross-family LLM
- [ ] Structured output validation (Pydantic models)
- [ ] Multi-turn conversation grounding
- [ ] Benchmark suite (public dataset)

<br>

## 📄 License

MIT — see [LICENSE](LICENSE).

<br>

## 🙏 Credits

Extracted from [AUREM](https://aurem.com) — an AI-CTO assistant that reads your GitHub repo and ships code. Built by the AUREM team.

---

**Questions?** Open an issue or reach out at [support@aurem.com](mailto:support@aurem.com).