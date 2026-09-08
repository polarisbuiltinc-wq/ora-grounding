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
reply = "Fixed auth.py line 42 and added redis_lock.py"

# 2. Build the canonical set from your retrieval context
canonical = {
    "paths": {"backend/auth.py"},  # redis_lock.py doesn't exist
    "basenames": {"auth.py"},
    "defs": set(),
}

# 3. Check
result = classify_claims(extract_claims(reply), canonical=canonical)
print(result)
# {'fabricated': ['redis_lock.py'], 'unverified': ['line 42']}
```

### Adversarial review

```python
from ora_grounding.review import adversarial_review

# Your agent's draft reply
draft = "Fixed the payment retry logic in payments_client.py"

# The retrieval context it had
context = """File: backend/services/payments.py
class PaymentService:
    def process_payment(self, amount): ...
"""

# Review with a different-family LLM
result = adversarial_review(
    draft=draft,
    context=context,
    reviewer_llm=your_llm_function,  # e.g. Anthropic Claude
)

if result["flags"]:
    print("Reviewer found issues:", result["flags"])
```

<br>

## 📊 vs. the alternatives

| Approach | Speed | Catches fabricated files | Catches overconfident synthesis | Cross-family |
|---|---|---|---|---|
| **Prompting alone** | Fast | ❌ | ❌ | N/A |
| **Same-family review** | Slow | ⚠️ | ⚠️ | ❌ |
| **ora-grounding** | Fast | ✅ | ✅ | ✅ |

- **Prompting alone** — "Be accurate. Don't hallucinate." — doesn't work. The model doesn't know when it's wrong.
- **Same-family review** — GPT-4 reviewing GPT-4 shares blind spots. Both models have the same training biases.
- **ora-grounding** — deterministic check + adversarial cross-family review. Different models, different failure modes.

<br>

## 🗺️ Roadmap

- [x] Deterministic grounding check
- [x] Cross-family adversarial review
- [ ] Pre-built reviewer configs (Claude, Gemini, Llama)
- [ ] Batch review API
- [ ] Confidence scoring
- [ ] Integration examples (LangChain, LlamaIndex)

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

**Built by [Polaris Built Inc.](https://polarisbuilt.com)** · Extracted from production AI-CTO assistant

</div>