"""
ora_grounding.grounding — Post-response grounding check for LLM chat agents.

Cheap, deterministic detection of "specific claims" (file paths, symbols,
line numbers, slash-commands) in an assistant reply that aren't supported
by the retrieval context the model actually saw.

Design (deliberately conservative):
  - Pure regex extraction — NO LLM calls in the fast path.
  - Two-level classification:
      FABRICATED  — path/command doesn't exist in the canonical index AND
                    wasn't typed by the user → hard flag (user-facing).
      UNVERIFIED  — exists in the repo but wasn't retrieved this turn →
                    soft flag (log-only).
  - All I/O (Mongo write, canonical-paths lookup) is injectable — the
    library never imports a database or a specific ORM.

Public surface:
    extract_claims(text)                       → list[str]
    find_ungrounded(claims, contexts)          → list[str]
    extract_line_claims(reply)                 → list[(fname, lineno)]
    extract_unknown_commands(reply, known)     → list[str]
    classify_claims(claims, *, canonical, ...) → {"fabricated": [], "unverified": []}
    run_post_response_check(...)               → {"claims", "fabricated", "unverified", "logged"}

Adapters (all keyword-only, all optional):
    on_log: async callable(dict) -> None       — persist a hallucination row
    canonical_paths_provider: async callable() -> dict  — {paths, basenames, defs}
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Awaitable, Callable, Iterable, Optional

logger = logging.getLogger(__name__)

# ─── Claim extractors ────────────────────────────────────────────
_RE_PY_TEST      = re.compile(r"\btest_iter[0-9a-z_]+\.py\b")
_RE_PY_FILE      = re.compile(r"\b[A-Za-z_][A-Za-z0-9_/-]*\.(?:py|jsx|tsx|ts|js)\b")
_RE_SYMBOL_BT    = re.compile(r"`([A-Za-z_][A-Za-z0-9_]{2,})(?:\(\))?`")
_RE_CRON_LIKE    = re.compile(r"\b[a-z_]+_(?:cron|scheduler|watcher|worker)\.py\b")

_SYMBOL_STOP: frozenset = frozenset({
    "None", "True", "False", "Exception", "self", "cls",
    "async", "await", "yield", "return", "import", "from",
    "GET", "POST", "PUT", "DELETE", "PATCH", "HTTP",
    "JSON", "HTML", "URL", "API", "SDK", "DNS", "TLS",
})


def extract_claims(text: str) -> list[str]:
    """Extract concrete, verifiable claims (file paths, symbol names,
    test-file names) from a chat reply. Adjectives and plans are left
    alone."""
    if not text:
        return []
    claims: list[str] = []
    seen: set[str] = set()

    def _add(x: str) -> None:
        x = x.strip()
        if x and x not in seen:
            seen.add(x)
            claims.append(x)

    for m in _RE_PY_TEST.finditer(text):
        _add(m.group(0))
    for m in _RE_PY_FILE.finditer(text):
        _add(m.group(0))
    for m in _RE_CRON_LIKE.finditer(text):
        _add(m.group(0))
    for m in _RE_SYMBOL_BT.finditer(text):
        sym = m.group(1)
        if sym not in _SYMBOL_STOP and not sym.isupper():
            _add(sym)
    return claims


def find_ungrounded(claims: Iterable[str],
                    contexts: Iterable[str]) -> list[str]:
    """A claim is grounded iff its exact string is a substring of any
    of the provided contexts. Case-sensitive on purpose."""
    joined = "\n".join(c or "" for c in contexts)
    return [c for c in claims if c and c not in joined]


# ─── Line-number & slash-command extractors ───────────────────────
_LINE_CLAIM_RE = re.compile(
    r"([\w/.\-]+\.(?:py|jsx|tsx|ts|js))[^.\n]{0,40}?\bline\s+(\d+)|"
    r"\bline\s+(\d+)[^.\n]{0,40}?(?:of|in)\s+`?([\w/.\-]+\.(?:py|jsx|tsx|ts|js))",
    re.IGNORECASE)
_SLASH_CMD_RE = re.compile(r"(?<![\w/.])/([a-z][a-z0-9\-]{3,})(?![\w/\-])")


def extract_line_claims(reply: str) -> list[tuple[str, int]]:
    """`file.py ... line N` / `line N of file.py` pairs. A line-number
    claim is only trustworthy with a matching source-read this turn."""
    out: list[tuple[str, int]] = []
    for m in _LINE_CLAIM_RE.finditer(reply or ""):
        fname = m.group(1) or m.group(4)
        line = m.group(2) or m.group(3)
        if fname and line:
            out.append((fname, int(line)))
    return out[:10]


def extract_unknown_commands(reply: str,
                              known_commands: Iterable[str] = ()
                              ) -> list[str]:
    """Slash-command tokens in the reply that aren't in the caller-
    provided allowlist. `known_commands` accepts entries with or
    without a leading slash."""
    known = {c.lstrip("/") for c in known_commands}
    out: list[str] = []
    for m in _SLASH_CMD_RE.finditer(reply or ""):
        tok = m.group(1)
        if tok not in known and f"/{tok}" not in out:
            out.append(f"/{tok}")
    return out[:10]


# ─── Classification vs a canonical index ──────────────────────────
_PATH_EXTS = (".py", ".jsx", ".tsx", ".ts", ".js")


def _normalize_path(claim: str) -> str:
    c = claim.strip().lstrip("/")
    if c.startswith("app/"):
        c = c[4:]
    return c


def classify_claims(claims: Iterable[str], *, canonical: dict,
                    user_query: str = "",
                    turn_contexts: Optional[list] = None) -> dict:
    """Two-level split:
      FABRICATED  — path claim whose file does NOT exist anywhere in
                    the canonical index and wasn't typed by the user
                    → hard flag.
      UNVERIFIED  — path exists in the repo but wasn't retrieved this
                    turn → soft flag.

    `canonical` shape: {"paths": set[str], "basenames": set[str],
                        "defs": set[str]}. Missing keys default to
                        empty sets.
    """
    joined = "\n".join(c or "" for c in (turn_contexts or []))
    q = user_query or ""
    paths: set = canonical.get("paths") or set()
    basenames: set = canonical.get("basenames") or set()
    defs: set = canonical.get("defs") or set()
    fabricated: list[str] = []
    unverified: list[str] = []
    for c in claims:
        if not c or c in q:
            continue
        if c.endswith(_PATH_EXTS):
            n = _normalize_path(c)
            base = n.rsplit("/", 1)[-1]
            exists = (n in paths or base in basenames
                      or any(p.endswith("/" + n) for p in paths))
            if not exists:
                fabricated.append(c)
            elif c not in joined and n not in joined:
                unverified.append(c)
        else:
            if c not in joined and c not in defs:
                unverified.append(c)
    return {"fabricated": fabricated, "unverified": unverified}


# ─── Type aliases for adapters ────────────────────────────────────
LogHook = Callable[[dict], Awaitable[None]]
CanonicalProvider = Callable[[], Awaitable[dict]]


async def _default_log_hook(_row: dict) -> None:
    """No-op default so callers don't need a stub when they don't
    want persistence."""
    return None


async def run_post_response_check(*,
                                   user_id: str,
                                   session_id: str,
                                   query: str,
                                   reply: str,
                                   route: str,
                                   sources_fired: Optional[list[str]] = None,
                                   retrieved_context: Optional[str] = None,
                                   codebase_tree: Optional[str] = None,
                                   system_highlights: Optional[str] = None,
                                   canonical_paths_provider:
                                       Optional[CanonicalProvider] = None,
                                   known_commands: Iterable[str] = (),
                                   on_log: Optional[LogHook] = None
                                   ) -> dict:
    """Shared post-response hook. Never raises. Returns:
        {claims, fabricated, unverified, logged}
    """
    empty = {"claims": [], "fabricated": [], "unverified": [], "logged": False}
    log_hook = on_log or _default_log_hook
    try:
        claims = extract_claims(reply)
        line_claims = extract_line_claims(reply)
        unknown_cmds = extract_unknown_commands(reply, known_commands)
        if not claims and not line_claims and not unknown_cmds:
            return empty
        canonical: dict = {}
        if canonical_paths_provider is not None:
            try:
                canonical = await canonical_paths_provider()
            except Exception as e:                                # noqa: BLE001
                logger.warning("canonical index unavailable: %r", e)
                canonical = {}
        if claims and canonical.get("paths"):
            cls = classify_claims(
                claims, canonical=canonical, user_query=query,
                turn_contexts=[retrieved_context, codebase_tree,
                               system_highlights],
            )
        else:
            cls = {"fabricated": [], "unverified": []}
        joined_ctx = "\n".join(x or "" for x in (retrieved_context,
                                                  codebase_tree,
                                                  system_highlights))
        for fname, line in line_claims:
            base = fname.rsplit("/", 1)[-1]
            if base in (query or ""):
                continue
            tag = f"{fname}:L{line}"
            if base not in joined_ctx and tag not in cls["unverified"]:
                cls["unverified"].append(tag)
        for cmd in unknown_cmds:
            if cmd not in (query or "") and cmd not in cls["fabricated"]:
                cls["fabricated"].append(cmd)
        logged = False
        if cls["fabricated"] or cls["unverified"]:
            row = {
                "created_at":     datetime.now(timezone.utc).isoformat(),
                "user_id":        user_id,
                "session_id":     session_id,
                "query":          (query or "")[:2000],
                "reply":          (reply or "")[:6000],
                "ungrounded":     (cls["fabricated"] + cls["unverified"])[:20],
                "fabricated":     cls["fabricated"][:20],
                "unverified":     cls["unverified"][:20],
                "route":          route,
                "sources_fired":  sources_fired or [],
                "contexts_seen":  {
                    "retrieved":         (retrieved_context or "")[:2000],
                    "codebase_tree":     (codebase_tree or "")[:2000],
                    "system_highlights": (system_highlights or "")[:2000],
                },
                "reviewed":       False,
            }
            try:
                await log_hook(row)
                logged = True
            except Exception as e:                                # noqa: BLE001
                logger.warning("grounding log_hook failed: %r", e)
        return {"claims": claims, "fabricated": cls["fabricated"],
                "unverified": cls["unverified"], "logged": logged}
    except Exception as e:                                        # noqa: BLE001
        logger.warning("post-response grounding hook failed: %r", e)
        return empty
