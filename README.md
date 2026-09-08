// double-click race test v3
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

# 1. Build the canonical set from your retrieval context
canonical = {
    "paths": {"src/auth.py", "src/db.py"},
    "basenames": {"auth.py", "db.py"},
    "defs": {"verify_token", "get_user"},
}

# 2. Extract claims from the LLM's reply
reply = "Fixed verify_token in auth.py and updated config.py"
claims = extract_claims(reply)

# 3. Classify
result = classify_claims(claims, canonical=canonical)
print(result)
# {'fabricated': ['config.py'], 'unverified': []}
```

### Adversarial review

```python
from ora_grounding.review import adversarial_review

# Bring your own LLM client
def call_llm(messages):
    # Your LLM API call here
    return "response text"

result = adversarial_review(
    draft="Fixed the bug in auth.py line 42",
    context="<your retrieval context>",
    llm_client=call_llm,
    model="gpt-4o",  # or claude-3-5-sonnet-20241022
)

if result["status"] == "approved":
    print("Draft passed review")
else:
    print(f"Blocked: {result['reason']}")
```

<br>

## 📊 vs. the alternatives

| Approach | Latency | Cost | Catches fabricated files | Catches overconfident synthesis |
|---|---|---|---|---|
| **Prompting alone** | 0 ms | $0 | ❌ | ❌ |
| **Same-family review** (GPT→GPT) | +2-5s | +$0.01 | ⚠️ partial | ⚠️ partial |
| **ora-grounding (grounding only)** | <1 ms | $0 | ✅ | ❌ |
| **ora-grounding (grounding + review)** | +2-5s | +$0.01 | ✅ | ✅ |

**Key insight:** Grounding catches *specifics* (files, symbols, lines). Review catches *synthesis* (overconfident claims). You need both.

<br>

## 🎯 Design principles

1. **Deterministic first** — regex + set-membership before LLM review. Cheaper, faster, zero false positives.
2. **Cross-family review** — GPT reviews Claude, Claude reviews GPT. Breaks shared blind spots.
3. **Zero deps** — stdlib only. Bring your own LLM client.
4. **Production-ready** — extracted from a real AI-CTO assistant serving users.

<br>

## 🗺️ Roadmap

- [x] Grounding check (v0.1.0)
- [x] Adversarial review (v0.1.0)
- [ ] Structured output validation (v0.2.0)
- [ ] Multi-turn conversation grounding (v0.3.0)
- [ ] Benchmark suite (v0.4.0)

<br>

## 📄 License

MIT — see [LICENSE](LICENSE).

<br>

## 🤝 Contributing

PRs welcome. Run tests:

```bash
pip install -e ".[dev]"
pytest
```

<br>

---

<div align="center">

**Built by [Aurem](https://aurem.com) — the AI engineer that ships code to your GitHub repo.**

</div>
