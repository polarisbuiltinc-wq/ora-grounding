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

### 1. Grounding check (deterministic)

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

# Extract + classify
claims = extract_claims(reply)
result = classify_claims(claims, canonical=canonical)

print(result)
# {'fabricated': ['redis_lock.py'], 'unverified': []}
```

**What it catches:**
- File paths not in your retrieval context
- Function/class names never mentioned
- Line numbers outside the ranges you fetched
- Shell commands you didn't run

**What it doesn't catch:**
- Logical errors ("this fixes the bug" when it doesn't)
- Misinterpretation of correct code
- Plausible-sounding claims with no specific anchor

For those, use the adversarial review below.

<br>

### 2. Adversarial review (LLM-based)

```python
from ora_grounding.review import adversarial_review

# Your agent's reply
reply = "The login flow is secure because we hash passwords with bcrypt."

# The actual code it read
context = """
# auth.py
def login(username, password):
    user = db.get_user(username)
    if user.password == password:  # ⚠️ plaintext comparison!
        return create_session(user)
"""

# Cross-family review (e.g. Claude reviews GPT's output)
flags = adversarial_review(
    reply=reply,
    context=context,
    reviewer_llm=your_claude_client,  # Different family than the generator
)

for flag in flags:
    print(f"{flag['severity']}: {flag['issue']}")
# CRITICAL: Claims bcrypt hashing but code does plaintext comparison
```

**Why cross-family?** GPT reviewing GPT shares blind spots. Claude/Gemini/Llama catch different failure modes.

**Deterministic guard:** The reviewer's own output is grounding-checked against the context — if the reviewer invents a file/function to justify a flag, that flag is auto-dropped.

<br>

## 🎯 Design principles

1. **Grounding check is cheap** — regex + set ops, no LLM in the hot path. Run it on every reply.
2. **Review is expensive** — only invoke when the reply claims to have fixed/changed something.
3. **Cross-family adversarial** — different model family = different failure modes caught.
4. **Reviewer is untrusted** — its flags are grounding-checked too.
5. **Zero deps** — bring your own LLM client, your own database, your own retrieval.

<br>

## 🆚 vs. the alternatives

| Approach | Pros | Cons |
|---|---|---|
| **Prompt engineering** | Free, fast | Doesn't prevent hallucination, just reduces frequency |
| **RAG with citations** | Shows sources | Doesn't catch when the model misreads the source |
| **Sibling-model review** | Catches some errors | Shares blind spots (GPT reviewing GPT) |
| **Human review** | Gold standard | Doesn't scale, slow |
| **ora-grounding** | Deterministic + adversarial, cross-family, zero deps | Requires you to track what was in context |

<br>

## 🗺️ Roadmap

- [x] Deterministic grounding check
- [x] Cross-family adversarial review
- [x] Zero dependencies
- [ ] Pre-built integrations (LangChain, LlamaIndex)
- [ ] Confidence scoring (how likely is this claim to be fabricated?)
- [ ] Auto-retry with corrected context when fabrication detected

<br>

## 📄 License

MIT — see [LICENSE](LICENSE).

<br>

## 🙋 FAQ

**Q: Does this replace prompt engineering?**  
No. Prompting reduces hallucination frequency. This catches the ones that slip through.

**Q: Can I use the same model for generation and review?**  
You can, but cross-family (GPT → Claude, Claude → Gemini) catches more.

**Q: What if my retrieval context is huge?**  
The grounding check only needs the *set* of paths/symbols/lines you fetched, not the full text. The adversarial review needs the full text but only runs on replies that claim to have changed something.

**Q: Does this work for non-code tasks?**  
The grounding check is code-focused (file paths, function names, line numbers). The adversarial review works for any domain — just pass the relevant context.

<br>

---

**Built by [Aurem](https://aurem.com)** — the AI CTO that ships code to your GitHub repo.  
Extracted from production. Battle-tested against real regressions.
