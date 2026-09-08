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

## 🚀 Quick start

```bash
pip install ora-grounding
```

```python
from ora_grounding.grounding import extract_claims, classify_claims
from ora_grounding.review import adversarial_review

# 1. Grounding check (deterministic, no LLM)
canonical = {
    "paths": {"src/auth.py", "src/db.py"},
    "basenames": {"auth.py", "db.py"},
    "defs": {"verify_token", "get_user"},
}
result = classify_claims(
    extract_claims("Fixed verify_token in auth.py and added redis_lock.py"),
    canonical=canonical,
)
print(result)  # {'fabricated': ['redis_lock.py'], 'unverified': []}

# 2. Adversarial review (cross-family LLM)
review = adversarial_review(
    draft="Added rate limiting to all endpoints",
    context="<your retrieval context>",
    llm_call=your_llm_function,  # bring your own LLM
)
if review["flags"]:
    print(f"Reviewer found issues: {review['flags']}")
```

<br>

## 📖 Usage

### Grounding check

The grounding check is **deterministic** — no LLM in the hot path. It extracts file paths, symbols, and line numbers from the agent's reply, then checks them against a canonical set you provide (from your retrieval context).

```python
from ora_grounding.grounding import extract_claims, classify_claims

# Build canonical set from your retrieval context
canonical = {
    "paths": {"backend/auth.py", "backend/db.py"},
    "basenames": {"auth.py", "db.py"},
    "defs": {"verify_token", "get_user", "hash_password"},
}

# Extract claims from agent reply
claims = extract_claims(
    "Fixed the bug in verify_token (auth.py:42) and added redis_lock.py"
)

# Classify: fabricated (not in canonical) vs unverified (plausible but not confirmed)
result = classify_claims(claims, canonical=canonical)
print(result)
# {'fabricated': ['redis_lock.py'], 'unverified': ['auth.py:42']}
```

**What counts as fabricated:**
- File paths not in `canonical["paths"]` or `canonical["basenames"]`
- Function/class names not in `canonical["defs"]`
- Line numbers (always unverified unless you pass line-level ground truth)

**What counts as unverified:**
- Claims that *could* be true but aren't in the canonical set (e.g. line numbers, commands)

<br>

### Adversarial review

The adversarial review uses a **different-family LLM** to hostile-read the draft. The reviewer is instructed to find overconfident claims, missing context, and fabricated specifics.

```python
from ora_grounding.review import adversarial_review

def my_llm_call(messages):
    # Your LLM integration (OpenAI, Anthropic, etc.)
    # Must return a string (the reviewer's response)
    return client.chat.completions.create(
        model="gpt-4",
        messages=messages,
    ).choices[0].message.content

review = adversarial_review(
    draft="Added rate limiting to all endpoints using Redis",
    context="<your retrieval context — the files/docs the agent had access to>",
    llm_call=my_llm_call,
)

if review["flags"]:
    print(f"Reviewer found {len(review['flags'])} issues:")
    for flag in review["flags"]:
        print(f"  - {flag}")
else:
    print("Draft passed review")
```

**The reviewer is instructed to:**
- Flag claims not supported by the context
- Flag overconfident synthesis ("this will reduce latency by 40%")
- Flag made-up file paths, line numbers, or function names

**Deterministic guard:** The review result is parsed with a strict regex. If the reviewer hallucinates flags (e.g. invents a file path that's not in the draft), those flags are dropped.

<br>

## 🆚 vs. the alternatives

| Approach | Speed | Accuracy | Cost |
|---|---|---|---|
| **Prompting alone** | Fast | Low | $ |
| **Sibling-model review** (GPT reviews GPT) | Slow | Medium | $$$ |
| **ora-grounding** (deterministic + cross-family) | Fast | High | $ |

**Why cross-family matters:** GPT-4 reviewing GPT-4 shares blind spots. A Claude reviewer catches different failure modes. The deterministic grounding check catches the rest.

<br>

## 🗺️ Roadmap

- [x] Deterministic grounding check
- [x] Cross-family adversarial review
- [ ] Line-level grounding (verify line numbers against actual file content)
- [ ] Multi-turn review (reviewer can request clarification)
- [ ] Confidence scoring (how likely is this claim to be fabricated?)

<br>

## 📜 License

MIT — see [LICENSE](LICENSE).

<br>

## 🙏 Credits

Extracted from [AUREM](https://aurem.com) — an AI-CTO assistant that reads your GitHub repo, fixes real issues, and ships as a commit. Built by the AUREM team.

---

**Questions? Issues?** Open an issue or PR — we're actively maintaining this.
