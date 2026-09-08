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

## 📦 Install

```bash
pip install ora-grounding
```

Zero dependencies. Python 3.10+.

<br>

## 🚀 Usage

### 1. Grounding check (deterministic, no LLM)

```python
from ora_grounding.grounding import extract_claims, classify_claims

# Your agent's reply
reply = "Fixed auth.py line 42 and added redis_lock.py"

# What your retrieval context ACTUALLY contained
canonical = {
    "paths": {"backend/auth.py"},           # redis_lock.py wasn't in context
    "basenames": {"auth.py"},
    "defs": {"verify_token", "hash_password"},
    "line_ranges": {("backend/auth.py", 1, 100)},  # line 42 is valid
}

claims = extract_claims(reply)
result = classify_claims(claims, canonical=canonical)

print(result)
# {'fabricated': ['redis_lock.py'], 'unverified': []}
```

**What it catches:**
- Files/symbols the retrieval context never mentioned
- Line numbers outside the ranges you fetched
- Commands you didn't run

**What it doesn't catch:**
- Plausible-sounding synthesis ("this improves performance by 40%")
- Misinterpreted code logic

For those, use adversarial review ↓

<br>

### 2. Adversarial review (cross-family LLM)

```python
from ora_grounding.review import adversarial_review

# Your agent's draft reply
draft = """Fixed the auth bug by adding rate limiting.
The issue was in verify_token() — it wasn't checking
expiry. Now it does."""

# The retrieval context it had
context = """File: backend/auth.py
def verify_token(token):
    # TODO: add expiry check
    return decode_jwt(token)
"""

# Review with a DIFFERENT model family
review_result = adversarial_review(
    draft=draft,
    context=context,
    reviewer_llm=your_claude_client,  # if draft was GPT
    min_severity="medium",
)

if review_result["flags"]:
    print("Reviewer found issues:")
    for flag in review_result["flags"]:
        print(f"  [{flag['severity']}] {flag['claim']} — {flag['reason']}")
else:
    print("Draft passed review")
```

**Why cross-family?** GPT reviewing GPT shares blind spots. Claude/Gemini/Llama catch different failure modes.

**Deterministic guard:** The reviewer's own output is grounding-checked against the context — if the reviewer invents a file/line to justify a flag, that flag is auto-dropped.

<br>

## 🎯 When to use what

| Scenario | Tool | Why |
|---|---|---|
| Agent cited a file you didn't fetch | Grounding check | Deterministic, instant |
| Agent's logic sounds off but cites real files | Adversarial review | Catches synthesis errors |
| Agent wrote code you want to verify | Both | Grounding first (cheap), review second |
| Agent gave a generic answer | Neither | Not a hallucination, just lazy |

<br>

## 🆚 vs. the alternatives

| Approach | Pros | Cons |
|---|---|---|
| **Prompting** ("be accurate") | Free | Doesn't work |
| **Sibling review** (GPT reviews GPT) | Easy | Shares blind spots |
| **Fact-checking LLM** | Catches some errors | Slow, expensive, can hallucinate flags |
| **ora-grounding** | Fast, deterministic base + adversarial layer | Requires you to track retrieval context |

<br>

## 🛠️ Roadmap

- [x] Deterministic grounding check
- [x] Cross-family adversarial review
- [ ] Auto-retry with context expansion on fabrication
- [ ] Confidence scoring per claim
- [ ] Integration examples (LangChain, LlamaIndex)

<br>

## 📄 License

MIT — ship it in prod, no strings attached.

<br>

## 🤝 Contributing

PRs welcome. This is extracted from a production system — if you hit a real-world edge case, open an issue with the anonymized example.

<br>

---

**Built by [Polaris Built Inc.](https://github.com/polarisbuiltinc-wq)** — the team behind AUREM, the AI-CTO assistant this was extracted from.