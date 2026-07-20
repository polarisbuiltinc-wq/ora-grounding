"""Decoupled tests for ora_grounding.review — no AUREM/OpenRouter deps.
The LLM is mocked via a caller-supplied async callable."""
from __future__ import annotations

import asyncio
import json

from ora_grounding.review import (
    trigger_reason,
    corrective_prompt,
    _parse_flags,
    verify_quotes,
    run_review,
    REVIEWER_SYSTEM,
    _HARD_TYPES,
)


# ─── trigger_reason ────────────────────────────────────────────────
def test_trigger_reason_high_stakes():
    assert trigger_reason(["HIGH_STAKES"], None) == "high_stakes_label"


def test_trigger_reason_grounding_unverified():
    assert trigger_reason([], {"unverified": ["x"]}) == "grounding_unverified"


def test_trigger_reason_routine_none():
    assert trigger_reason([], {"unverified": []}) is None
    assert trigger_reason(None, None) is None


# ─── corrective_prompt ─────────────────────────────────────────────
def test_corrective_prompt_with_claims():
    p = corrective_prompt([
        {"quote": "cost $4,200", "type": "FABRICATED", "reason": "no source"},
    ])
    assert "cost $4,200" in p
    assert "Rewrite the full answer." in p


def test_corrective_prompt_with_ignored_task():
    p = corrective_prompt([
        {"quote": "run a scan and paste output", "type": "IGNORED_TASK",
         "reason": "no scan"},
    ])
    assert "FAILED to address" in p
    assert "run a scan" in p


# ─── _parse_flags ──────────────────────────────────────────────────
def test_parse_flags_pass():
    flags, ok = _parse_flags('{"result":"PASS"}')
    assert ok and flags == []


def test_parse_flags_array():
    raw = json.dumps([
        {"quote": "the sky is green", "type": "FABRICATED", "reason": "no"},
        {"quote": "unclear scope", "type": "UNVERIFIED", "reason": "unclear"},
    ])
    flags, ok = _parse_flags(raw)
    assert ok
    assert len(flags) == 2
    assert flags[0]["type"] == "FABRICATED"


def test_parse_flags_wrapped_in_code_fence():
    raw = "```json\n" + json.dumps([
        {"quote": "x", "type": "OVERSTATED", "reason": "y"}
    ]) + "\n```"
    flags, ok = _parse_flags(raw)
    assert ok and len(flags) == 1


def test_parse_flags_junk_returns_parse_fail():
    flags, ok = _parse_flags("not json at all")
    assert not ok and flags == []


# ─── verify_quotes ─────────────────────────────────────────────────
def test_verify_quotes_keeps_matching_drops_fake():
    draft = "Sonic runs on M4 chip at 3.8 GHz."
    flags = [
        {"quote": "M4 chip at 3.8 GHz", "type": "OVERSTATED", "reason": "x"},
        {"quote": "runs at 10 THz",     "type": "FABRICATED",  "reason": "y"},
    ]
    kept, dropped = verify_quotes(flags, draft, "")
    assert [f["quote"] for f in kept]     == ["M4 chip at 3.8 GHz"]
    assert [f["quote"] for f in dropped]  == ["runs at 10 THz"]


def test_verify_quotes_ignored_task_uses_user_query():
    draft = "here's a fun fact instead"
    query = "run a security scan and paste output"
    flags = [{"quote": "run a security scan",
              "type": "IGNORED_TASK", "reason": "no scan"}]
    kept, dropped = verify_quotes(flags, draft, query)
    assert len(kept) == 1 and len(dropped) == 0


def test_verify_quotes_multiple_ignored_task_only_first_kept():
    draft = "irrelevant"
    query = "do X and also do Y"
    flags = [
        {"quote": "do X", "type": "IGNORED_TASK", "reason": "a"},
        {"quote": "do Y", "type": "IGNORED_TASK", "reason": "b"},
    ]
    kept, dropped = verify_quotes(flags, draft, query)
    assert len(kept) == 1 and len(dropped) == 1


# ─── run_review — end-to-end with mocked llm_call ───────────────────
def _make_llm(response_text: str, usage=None, err=None):
    async def _call(system: str, user: str):
        assert system == REVIEWER_SYSTEM
        assert "USER QUERY:" in user and "DRAFT TO REVIEW:" in user
        return response_text, usage or {}, err
    return _call


def test_run_review_pass_result_no_flags():
    llm = _make_llm('{"result":"PASS"}')
    r = asyncio.run(run_review(
        user_id="u", session_id="s", query="q",
        draft="a clean, defensible draft.",
        context="ctx", llm_call=llm))
    assert r["passed"] is True
    assert r["flags"] == []
    assert r["skipped"] is None


def test_run_review_returns_hard_and_soft_splits():
    payload = json.dumps([
        {"quote": "the sky is green here",  "type": "FABRICATED",  "reason": "no"},
        {"quote": "unclear scope of x",     "type": "UNVERIFIED",   "reason": "y"},
    ])
    llm = _make_llm(payload)
    draft = "Report: the sky is green here. Also, unclear scope of x remains."
    r = asyncio.run(run_review(
        user_id="u", session_id="s", query="?",
        draft=draft, context="", llm_call=llm))
    assert len(r["hard"]) == 1 and r["hard"][0]["type"] in _HARD_TYPES
    assert len(r["soft"]) == 1 and r["soft"][0]["type"] == "UNVERIFIED"
    assert r["passed"] is False


def test_run_review_drops_hallucinated_quotes_and_fires_hook():
    payload = json.dumps([
        {"quote": "quote that isnt in draft",
         "type": "FABRICATED", "reason": "made up"},
    ])
    llm = _make_llm(payload)
    hook_calls: list[dict] = []

    async def on_err(row: dict) -> None:
        hook_calls.append(row)

    r = asyncio.run(run_review(
        user_id="u", session_id="s", query="?",
        draft="Actual draft says nothing about quotes.",
        context="", llm_call=llm, on_reviewer_error=on_err))
    assert r["dropped"] == 1
    assert r["flags"] == []
    assert len(hook_calls) == 1
    assert hook_calls[0]["dropped_flags"][0]["quote"] == "quote that isnt in draft"


def test_run_review_empty_draft_short_circuits():
    llm = _make_llm("should never be called")
    r = asyncio.run(run_review(
        user_id="u", session_id="s", query="?", draft="",
        context="", llm_call=llm))
    assert r["skipped"] == "empty_draft"


def test_run_review_budget_check_skips():
    async def budget_over() -> bool:
        return True

    llm = _make_llm("should never be called")
    r = asyncio.run(run_review(
        user_id="u", session_id="s", query="?",
        draft="a real draft", context="", llm_call=llm,
        budget_check=budget_over))
    assert r["skipped"] == "review_skipped_budget"


def test_run_review_reviewer_error_never_raises():
    async def crashing_llm(system, user):
        raise ConnectionError("boom")

    r = asyncio.run(run_review(
        user_id="u", session_id="s", query="?",
        draft="draft", context="", llm_call=crashing_llm))
    assert r["skipped"] and r["skipped"].startswith("reviewer_error:")


def test_run_review_unparseable_reviewer_output():
    llm = _make_llm("not json — just prose")
    r = asyncio.run(run_review(
        user_id="u", session_id="s", query="?",
        draft="draft", context="", llm_call=llm))
    assert r["skipped"] == "reviewer_unparseable"
