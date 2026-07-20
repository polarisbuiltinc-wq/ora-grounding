"""
ora_grounding.review — Adversarial (hostile) review pass for LLM drafts.

Draft-then-review on high-stakes turns. Uses a caller-provided LLM
callable (typically a different model family than the drafter) to find
what's wrong, unverified, or overstated in the draft.

Cross-family review beats sibling review — sibling models share blind
spots. Flag-only: the reviewer never rewrites; caller decides whether
to regen once or attach caveats.

Deterministic guard on the reviewer itself: every flag's `quote` is
string-checked verbatim against the draft. A fake quote = reviewer
hallucinated the flag = that flag is dropped and reported to
`dropped`.

Public surface:
    REVIEWER_SYSTEM               — system prompt (str)
    trigger_reason(labels, grd)   → "high_stakes_label" | "grounding_unverified" | None
    corrective_prompt(hard_flags) → str  (feed as user turn for regen)
    _parse_flags(text)            → (flags: list, parse_ok: bool)
    verify_quotes(flags, draft, q)→ (kept, dropped)
    run_review(...)               → dict {flags, hard, soft, dropped, ...}

Adapters (all keyword-only, all optional except llm_call):
    llm_call:      async callable(system: str, user: str) -> (text, usage, err)
                   REQUIRED. Returns the reviewer's raw output plus
                   whatever usage/error metadata the caller wants
                   surfaced. `usage` and `err` may be None/{}.
    budget_check:  async callable() -> bool
                   Return True to skip review (over budget). Optional.
    on_reviewer_error: async callable(dict) -> None
                   Fires with `{user_id, session_id, dropped_flags,
                   raw_head, created_at}` whenever the reviewer's
                   quotes fail verbatim-check. Optional.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

_FLAG_TYPES = ("FABRICATED", "UNVERIFIED", "OVERSTATED",
               "CONTRADICTS_CONTEXT", "IGNORED_TASK")
_HARD_TYPES = ("FABRICATED", "CONTRADICTS_CONTEXT", "IGNORED_TASK")

REVIEWER_SYSTEM = (
    "You are a hostile reviewer. Your only job is to find what is wrong, "
    "unverified, or overstated in the draft below. You get credit for "
    "finding real problems. You get zero credit for approving.\n\n"
    "For each problem output an object:\n"
    '  { "quote": "<exact sentence copied verbatim from the draft>",\n'
    '    "type": "FABRICATED | UNVERIFIED | OVERSTATED | '
    'CONTRADICTS_CONTEXT | IGNORED_TASK",\n'
    '    "reason": "<one line>" }\n\n'
    "Rules:\n"
    "- Any specific claim (number, file, date, capability) not supported "
    "by the provided context must be flagged. No benefit of the doubt.\n"
    "- IGNORED_TASK: the draft failed to do something the user "
    "EXPLICITLY asked for (e.g. asked for a scan but no scan output is "
    "present). For this type only, \"quote\" should be the ignored "
    "request copied from the USER QUERY. Max ONE such flag.\n"
    "- The \"quote\" field MUST be copied character-for-character from "
    "the draft — never paraphrase, never trim mid-word.\n"
    "- Do NOT suggest rewrites. Do NOT add new claims. Do NOT summarize.\n"
    '- If genuinely nothing is flaggable, output exactly: {"result":"PASS"}\n'
    "Output a JSON array of flag objects (or the PASS object). JSON only."
)


def trigger_reason(labels: Optional[list],
                   grounding: Optional[dict]) -> Optional[str]:
    """Which turns get reviewed. Everything else stays single-pass."""
    if "HIGH_STAKES" in (labels or []):
        return "high_stakes_label"
    if grounding and grounding.get("unverified"):
        return "grounding_unverified"
    return None


def corrective_prompt(hard_flags: list[dict]) -> str:
    """Build the user turn that asks the drafter to rewrite while
    removing (or explicitly marking unverified) the flagged claims."""
    ignored = [f for f in hard_flags if f["type"] == "IGNORED_TASK"]
    claims = [f for f in hard_flags if f["type"] != "IGNORED_TASK"]
    parts: list[str] = []
    if claims:
        quotes = "; ".join(f'"{f["quote"]}"' for f in claims[:6])
        parts.append("Your previous draft contained these unsupported "
                     f"claims: {quotes}. Remove them or explicitly mark "
                     "them unverified. Do not defend them.")
    if ignored:
        parts.append("Your draft also FAILED to address what the user "
                     f"explicitly asked: \"{ignored[0]['quote'][:200]}\" — "
                     "answer what was asked, or state clearly why you "
                     "cannot.")
    parts.append("Rewrite the full answer.")
    return " ".join(parts)


def _parse_flags(text: str) -> tuple[list[dict], bool]:
    """Returns (flags, parse_ok). PASS → ([], True)."""
    s = (text or "").strip()
    s = s.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(s)
    except ValueError:
        return [], False
    if isinstance(data, dict):
        if data.get("result") == "PASS":
            return [], True
        data = data.get("flags") or []
    if not isinstance(data, list):
        return [], False
    out: list[dict] = []
    for f in data:
        if isinstance(f, dict) and f.get("quote") \
                and f.get("type") in _FLAG_TYPES:
            out.append({"quote":  str(f["quote"])[:400],
                        "type":   f["type"],
                        "reason": str(f.get("reason") or "")[:200]})
    return out, True


def verify_quotes(flags: list[dict], draft: str,
                  query: str = "") -> tuple[list, list]:
    """Deterministic reviewer-hallucination guard: quote not found
    verbatim in the draft = drop. IGNORED_TASK quotes come from the
    USER QUERY instead — at most one kept."""
    kept, dropped = [], []
    d = draft or ""
    q = query or ""
    seen_ignored = False
    for f in flags:
        if f["type"] == "IGNORED_TASK":
            if not seen_ignored and (not f["quote"] or f["quote"] in q
                                     or f["quote"] in d):
                kept.append(f)
                seen_ignored = True
            else:
                dropped.append(f)
            continue
        (kept if f["quote"] in d else dropped).append(f)
    return kept, dropped


# ─── Type aliases for adapters ────────────────────────────────────
LlmCall = Callable[[str, str], Awaitable[tuple]]
BudgetCheck = Callable[[], Awaitable[bool]]
ReviewerErrorHook = Callable[[dict], Awaitable[None]]


async def run_review(*, user_id: str, session_id: str, query: str,
                     draft: str, context: str,
                     llm_call: LlmCall,
                     reason: str = "",
                     budget_check: Optional[BudgetCheck] = None,
                     on_reviewer_error: Optional[ReviewerErrorHook] = None
                     ) -> dict:
    """One hostile-review pass. Never raises.

    Args:
      llm_call: async (system, user) → (text, usage, err). Caller
                picks the model — cross-family is strongly recommended.
                `usage` and `err` may be None/{}.
      budget_check: return True to skip review (over budget).
      on_reviewer_error: fires when the reviewer hallucinates quotes.

    Returns:
      {flags, hard, soft, dropped, latency_s, usage, skipped, passed}
    """
    empty = {"flags": [], "hard": [], "soft": [], "dropped": 0,
             "latency_s": 0.0, "usage": {},
             "skipped": None, "passed": True}
    if not (draft or "").strip():
        return {**empty, "skipped": "empty_draft"}

    if budget_check is not None:
        try:
            if await budget_check():
                logger.info("review skipped: budget hook returned True")
                return {**empty, "skipped": "review_skipped_budget"}
        except Exception as e:                                    # noqa: BLE001
            logger.warning("review budget check failed: %r", e)

    user_prompt = (
        f"USER QUERY:\n{(query or '')[:2000]}\n\n"
        "GROUNDING CONTEXT the drafter saw (judge the draft ONLY against "
        "this — is the draft supported by what the drafter actually "
        f"saw?):\n{(context or '(none — no retrieved context this turn)')[:8000]}\n\n"
        f"DRAFT TO REVIEW:\n{draft[:8000]}"
    )
    t0 = time.time()
    try:
        text, usage, err = await llm_call(REVIEWER_SYSTEM, user_prompt)
    except Exception as e:                                        # noqa: BLE001
        return {**empty, "skipped": f"reviewer_error:{type(e).__name__}",
                "latency_s": round(time.time() - t0, 2)}
    latency = round(time.time() - t0, 2)
    if err or not text:
        return {**empty, "skipped": f"reviewer_error:{err or 'empty'}",
                "latency_s": latency, "usage": usage or {}}
    flags, parse_ok = _parse_flags(text)
    if not parse_ok:
        return {**empty, "skipped": "reviewer_unparseable",
                "latency_s": latency, "usage": usage or {}}
    kept, dropped = verify_quotes(flags, draft, query)
    if dropped and on_reviewer_error is not None:
        try:
            await on_reviewer_error({
                "user_id": user_id, "session_id": session_id,
                "dropped_flags": dropped[:10],
                "raw_head": (text or "")[:2000],
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:                                    # noqa: BLE001
            logger.warning("reviewer_error hook failed: %r", e)
    hard = [f for f in kept if f["type"] in _HARD_TYPES]
    soft = [f for f in kept if f["type"] not in _HARD_TYPES]
    return {"flags": kept, "hard": hard, "soft": soft,
            "dropped": len(dropped), "latency_s": latency,
            "usage": usage or {},
            "skipped": None, "passed": not kept}
