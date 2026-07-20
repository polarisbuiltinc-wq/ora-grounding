"""Decoupled tests for ora_grounding.grounding — no AUREM/Mongo deps."""
from __future__ import annotations

import asyncio

import pytest

from ora_grounding.grounding import (
    extract_claims,
    find_ungrounded,
    extract_line_claims,
    extract_unknown_commands,
    classify_claims,
    run_post_response_check,
)


# ─── extract_claims ────────────────────────────────────────────────
def test_extract_claims_picks_paths_and_symbols():
    text = "Fix in `handle_request()` at services/foo.py — see test_iter42_bar.py."
    claims = extract_claims(text)
    assert "handle_request" in claims
    assert "services/foo.py" in claims
    assert "test_iter42_bar.py" in claims


def test_extract_claims_ignores_stopwords_and_all_caps_symbols():
    text = "`None` and `HTTP` and `POST` should not be flagged."
    assert extract_claims(text) == []


def test_extract_claims_empty_input():
    assert extract_claims("") == []
    assert extract_claims(None) == []  # type: ignore[arg-type]


# ─── find_ungrounded ───────────────────────────────────────────────
def test_find_ungrounded_pure():
    claims = ["a.py", "b.py"]
    contexts = ["file listing: a.py, c.py"]
    assert find_ungrounded(claims, contexts) == ["b.py"]


def test_find_ungrounded_no_claims_returns_empty():
    assert find_ungrounded([], ["anything"]) == []


# ─── extract_line_claims ───────────────────────────────────────────
def test_extract_line_claims_forward_pattern():
    reply = "Bug is at services/foo.py line 42 in the handler."
    assert extract_line_claims(reply) == [("services/foo.py", 42)]


def test_extract_line_claims_reverse_pattern():
    reply = "See line 123 of routers/bar.py"
    assert extract_line_claims(reply) == [("routers/bar.py", 123)]


# ─── extract_unknown_commands ──────────────────────────────────────
def test_extract_unknown_commands_flags_unknowns():
    reply = "Try /deploy-production or /read and /nope-cmd."
    known = {"/read", "/find", "/repo-tree"}
    unknown = extract_unknown_commands(reply, known)
    assert "/deploy-production" in unknown
    assert "/nope-cmd" in unknown
    assert "/read" not in unknown


def test_extract_unknown_commands_dedupes():
    reply = "/xyz-cmd and /xyz-cmd again"
    assert extract_unknown_commands(reply, ()) == ["/xyz-cmd"]


# ─── classify_claims ───────────────────────────────────────────────
def test_classify_fabricated_and_unverified():
    canonical = {
        "paths":     {"services/real.py", "routers/api.py"},
        "basenames": {"real.py", "api.py"},
        "defs":      set(),
    }
    claims = ["services/real.py", "services/fake.py", "routers/api.py"]
    # `real.py` was retrieved this turn; `api.py` was not.
    ctx = ["retrieved: services/real.py content..."]
    r = classify_claims(claims, canonical=canonical,
                        user_query="", turn_contexts=ctx)
    assert r["fabricated"] == ["services/fake.py"]
    assert "routers/api.py" in r["unverified"]
    assert "services/real.py" not in r["unverified"]


def test_classify_user_typed_claims_are_free():
    """If the user typed the path, the model may discuss it freely."""
    canonical = {"paths": set(), "basenames": set(), "defs": set()}
    r = classify_claims(["fake.py"], canonical=canonical,
                        user_query="what does fake.py do?",
                        turn_contexts=[])
    assert r["fabricated"] == []


# ─── run_post_response_check ───────────────────────────────────────
def test_run_post_response_returns_empty_on_clean_reply():
    r = asyncio.run(run_post_response_check(
        user_id="u1", session_id="s1", query="hi",
        reply="Hello there.", route="chat",
    ))
    assert r == {"claims": [], "fabricated": [], "unverified": [],
                 "logged": False}


def test_run_post_response_flags_fabrication_and_calls_log_hook():
    log_rows: list[dict] = []

    async def on_log(row: dict) -> None:
        log_rows.append(row)

    async def canonical() -> dict:
        return {"paths": {"real.py"}, "basenames": {"real.py"}, "defs": set()}

    r = asyncio.run(run_post_response_check(
        user_id="u1", session_id="s1",
        query="does this exist?",
        reply="Yes, see fake_module.py for details.",
        route="chat",
        canonical_paths_provider=canonical,
        on_log=on_log,
    ))
    assert "fake_module.py" in r["fabricated"]
    assert r["logged"] is True
    assert len(log_rows) == 1
    assert log_rows[0]["fabricated"] == ["fake_module.py"]


def test_run_post_response_unknown_slash_command_is_fabrication():
    async def canonical() -> dict:
        return {"paths": {"real.py"}, "basenames": {"real.py"}, "defs": set()}

    r = asyncio.run(run_post_response_check(
        user_id="u1", session_id="s1", query="how do I deploy?",
        reply="Just run /deploy-production and you're done.",
        route="chat",
        canonical_paths_provider=canonical,
        known_commands={"/read", "/find"},
    ))
    assert "/deploy-production" in r["fabricated"]


def test_run_post_response_never_raises_even_if_hook_fails():
    async def bad_hook(_row: dict) -> None:
        raise RuntimeError("db exploded")

    async def canonical() -> dict:
        return {"paths": {"real.py"}, "basenames": {"real.py"}, "defs": set()}

    r = asyncio.run(run_post_response_check(
        user_id="u1", session_id="s1", query="?",
        reply="See fake.py at line 5.", route="chat",
        canonical_paths_provider=canonical,
        on_log=bad_hook,
    ))
    # fabricated is still detected; logged is False because hook failed.
    assert "fake.py" in r["fabricated"]
    assert r["logged"] is False
