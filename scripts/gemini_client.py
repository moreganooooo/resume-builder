"""
gemini_client.py — Shared Gemini REST client.

Imported by both orchestrator.py and rewrite_bullets.py to break
the circular import between them.
"""

import base64
import copy
import hashlib
import json
import os
import random
import re
import sys
import threading
import time

import cli_art
import profile_paths
import requests
import theme
from dotenv import load_dotenv

# Resolved via profile_paths.env_path() -- each profile carries its own
# .env (GEMINI_API_KEY, JOBRIGHT_COOKIE_STRING), not one shared project-
# root file. override=True is the important part -- without it, a
# GEMINI_API_KEY already exported in the shell (e.g. from an earlier
# manual export while juggling API keys) silently wins over whatever's
# actually in .env, since dotenv's default behavior is to never overwrite
# an existing environment variable.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

# --- API key pool ----------------------------------------------------------
# A profile's .env may hold several keys: GEMINI_API_KEY, GEMINI_API_KEY_2,
# GEMINI_API_KEY_3 (any number), and/or a comma-separated GEMINI_API_KEYS.
# Free-tier quota is per Google Cloud PROJECT and per model, so extra keys
# only add quota when each comes from a different project.
#
# When a key 429s on a model, it is cooled down for that model only and the
# next call picks the first key still fresh for it -- a bulk run switches
# keys immediately instead of sleeping out a backoff on a spent one. Keys are
# tried in their listed order, so the primary key is used whenever it can be.
_KEY_COOLDOWNS: dict[tuple[str, str], float] = {}
DEFAULT_KEY_COOLDOWN_SECS = 60.0


def _numbered_key_suffix(name: str) -> int:
    tail = name[len("GEMINI_API_KEY_"):]
    return int(tail) if tail.isdigit() else 10**6


def _pool_limited_under_test() -> bool:
    import sys

    return "unittest" in sys.modules


def api_keys() -> list[str]:
    """Every configured key, primary first, deduplicated. Re-reads .env each
    call so a key added or swapped mid-run is picked up."""
    load_dotenv(profile_paths.env_path(), override=True)
    ordered = [os.environ.get("GEMINI_API_KEY", "")]
    numbered = sorted(
        (n for n in os.environ if n.startswith("GEMINI_API_KEY_")),
        key=_numbered_key_suffix,
    )
    ordered += [os.environ[n] for n in numbered]
    ordered += (os.environ.get("GEMINI_API_KEYS") or "").split(",")
    ordered.append(os.environ.get("GOOGLE_API_KEY", ""))
    keys: list[str] = []
    for k in ordered:
        k = k.strip()
        if k and k not in keys:
            keys.append(k)
    # Under tests the pool is just the primary key: otherwise how many
    # backup keys the operator happens to have changes every retry count
    # a test asserts on (3 failures on a machine with GEMINI_API_KEY_2 set).
    if _pool_limited_under_test():
        return keys[:1]
    return keys


def _get_api_key(model: str = "") -> str:
    """The first key not cooling down for `model`; if all are, the one whose
    cooldown ends soonest."""
    keys = api_keys()
    if not keys:
        return ""
    now = time.time()
    for k in keys:
        if _KEY_COOLDOWNS.get((k, model), 0) <= now:
            return k
    return min(keys, key=lambda k: _KEY_COOLDOWNS.get((k, model), 0))


def mark_key_rate_limited(key: str, model: str = "", secs: float | None = None) -> bool:
    """Cools `key` down for `model`. Returns True when another key is fresh
    for that model right now, i.e. an immediate retry is worth making."""
    if not key:
        return False
    _KEY_COOLDOWNS[(key, model)] = time.time() + (secs or DEFAULT_KEY_COOLDOWN_SECS)
    return _get_api_key(model) != key and _KEY_COOLDOWNS.get(
        (_get_api_key(model), model), 0
    ) <= time.time()


def rotate_api_key(model: str = "") -> str:
    """Back-compat: cool the current key and return the next one."""
    mark_key_rate_limited(_get_api_key(model), model)
    return _get_api_key(model)


def key_label(key: str) -> str:
    """Safe-to-print identifier for a key: its position and last 4 chars."""
    keys = api_keys()
    pos = keys.index(key) + 1 if key in keys else 0
    return f"key {pos}/{len(keys)} (…{key[-4:]})"


# Tests that genuinely mean to hit the live API set RESUME_ALLOW_TEST_NETWORK=1.
# Everything else fails closed. Same guard shape as websearch_ddg.py's
# _TEST_NETWORK_ENV and liveness._gather_db_candidates -- see CLAUDE.md.
_TEST_NETWORK_ENV = "RESUME_ALLOW_TEST_NETWORK"


class TestNetworkBlockedError(RuntimeError):
    """Raised when a test reaches the live Gemini API without opting in."""


def _blocked_under_test() -> bool:
    import sys

    return "unittest" in sys.modules and not os.environ.get(_TEST_NETWORK_ENV)


def _get_auth_headers(model: str = "") -> dict:
    """Builds the per-call auth header -- and is the single chokepoint
    where a test can be stopped from reaching the real API.

    Every requests.post() in this module goes through here, which is why
    the guard lives at this level rather than being repeated at each call
    site. Without it the suite made 78 live calls to
    generativelanguage.googleapis.com on every full run: real spend, real
    429s, and a wall-clock that swung between 127s and 274s depending on
    rate limiting.

    Fails CLOSED (raises) rather than returning a canned response. A guard
    that silently handed back an empty result would leave those tests
    green while asserting nothing at all, which is worse than the
    original bug -- the same reasoning behind db._is_unisolated_test_write
    dropping the write instead of faking one."""
    if _blocked_under_test():
        raise TestNetworkBlockedError(
            "A test tried to call the live Gemini API. Mock the client for this "
            f"test, or set {_TEST_NETWORK_ENV}=1 if it genuinely needs the network."
        )
    return {"x-goog-api-key": _get_api_key(model)}


def generate_grounded(
    model: str,
    prompt: str,
    tools: list,
    tool_config: dict = None,
    max_retries: int = 3,
) -> tuple[str | None, dict]:
    """One grounded call, returning (text, groundingMetadata).

    GeminiClient.generate() returns only text and token usage, but a
    grounded caller must SEE the grounding to trust the answer -- and, for
    Google Maps, to keep the Place ID and source link its terms require.
    Thought parts are dropped from the text. Returns (None, {}) after
    retrying 429/5xx, or on any other failure; under tests the auth header
    raises TestNetworkBlockedError, the same fail-closed rule as every other
    call in this module."""
    url = f"{BASE_URL}/{model}:generateContent"
    body = {"contents": [{"parts": [{"text": prompt}]}], "tools": tools}
    if tool_config:
        body["toolConfig"] = tool_config
    fallbacks = grounded_fallbacks(tools)
    failures = 0
    key_switches = 0
    for attempt in range(max_retries + len(api_keys())):
        if attempt - key_switches >= max_retries:
            break
        # Two failures on one model -> its same-quota-family backup.
        if failures >= 2 and model in fallbacks:
            model = fallbacks[model]
            url = f"{BASE_URL}/{model}:generateContent"
            failures = 0
        headers = {**_get_auth_headers(model), "Content-Type": "application/json"}
        try:
            response = requests.post(
                url,
                headers=headers,
                json=body,
                timeout=90,
            )
        except requests.exceptions.RequestException:
            response = None
        if response is not None and response.status_code == 200:
            try:
                candidate = (response.json().get("candidates") or [{}])[0]
            except ValueError:
                return None, {}
            parts = (candidate.get("content") or {}).get("parts") or []
            text = "".join(
                p.get("text", "")
                for p in parts
                if isinstance(p, dict) and not p.get("thought")
            )
            return (text.strip() or None), (candidate.get("groundingMetadata") or {})
        if response is not None and response.status_code not in (429, 500, 502, 503, 504):
            return None, {}
        if response is not None and response.status_code == 429:
            if mark_key_rate_limited(
                headers["x-goog-api-key"], model, _server_retry_delay_secs(response)
            ):
                key_switches += 1
                continue  # a fresh key: retry now, no backoff, no fallback
        failures += 1
        time.sleep(min(5 * 2**attempt, 30))
    return None, {}


class TokenBucketRateLimiter:
    """Thread-safe token-bucket rate limiter for API requests.

    Default rate is 12.0 requests per minute (0.2 tokens/sec) with a burst
    capacity of 4.0 tokens (D11). Configurable via GEMINI_RPM_LIMIT or
    RESUME_API_RPM env vars.
    """

    def __init__(self, rpm: float = 12.0, capacity: float = 4.0):
        self.rpm = float(rpm)
        self.capacity = float(capacity)
        self.tokens = float(capacity)
        self.refill_rate = self.rpm / 60.0  # tokens per second
        self.last_refill_ts = time.monotonic()
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls) -> "TokenBucketRateLimiter":
        env_val = os.environ.get("GEMINI_RPM_LIMIT") or os.environ.get("RESUME_API_RPM")
        try:
            rpm = float(env_val) if env_val else 12.0
        except ValueError:
            rpm = 12.0
        return cls(rpm=rpm, capacity=max(1.0, rpm / 3.0))

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill_ts
        if elapsed > 0:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_refill_ts = now

    def acquire(self, tokens: float = 1.0, block: bool = True) -> float:
        """Acquires the requested tokens. Returns the wait duration in seconds.
        If block=True and wait > 0, sleeps for that duration (unless in test mode).
        """
        with self._lock:
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return 0.0

            deficit = tokens - self.tokens
            wait_time = deficit / self.refill_rate if self.refill_rate > 0 else 0.0

            if not block:
                return wait_time

            self.tokens -= tokens

        if wait_time > 0 and block:
            is_under_test = (
                "unittest" in sys.modules
                or "pytest" in sys.modules
                or _blocked_under_test()
                or os.environ.get("CI") == "true"
                or os.environ.get("RESUME_BUILDER_TESTING") == "1"
            )
            if not is_under_test:
                time.sleep(wait_time)
        return wait_time


rate_limiter = TokenBucketRateLimiter.from_env()


AUTH_HEADERS = None

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

RETRYABLE = {429, 500, 502, 503, 504}
SERVER_ERRORS = {500, 502, 503, 504}
HIGH_DEMAND_STATUS = 503

# A model that just failed outright is benched for a while, so the NEXT
# bullet starts on its fallback instead of paying the failing model's
# pacing and retry ladder again. One shared bench, so the resume builder and
# the Bullet Bank stages agree on whether Gemma is currently usable. Probed
# 2026-09-16: both flash-lites answering in <1s while gemma-4-31b-it took
# 21s, 500'd, then took 59s -- and every Gemma call also waits 65s first.
MODEL_BENCH_SECS = 15 * 60
_benched_until: dict = {}


def bench_model(model: str, seconds: float = MODEL_BENCH_SECS) -> None:
    _benched_until[model] = time.monotonic() + seconds


def is_benched(model: str) -> bool:
    return time.monotonic() < _benched_until.get(model, 0.0)
BASE_BACKOFF_SECS = 8
MAX_BACKOFF_SECS = 90

# Fallback model used when primary fails repeatedly
REWRITE_FALLBACK_MODEL = "gemini-3.5-flash-lite"


def _server_retry_delay_secs(resp) -> float | None:
    """Reads the server's own cooldown hint off a 429/503, when it sends
    one -- a free-tier RPM cap (e.g. Gemma's) can be tighter than our
    guessed BASE_BACKOFF_SECS exponential curve accounts for, especially
    once per-call prompt/cache size grows. Google's quota errors carry a
    google.rpc.RetryInfo block in error.details with the real wait time
    ("19s"); honoring that beats blind exponential backoff that retries
    well before the quota window actually resets. Returns None (falls
    back to the exponential curve) if the response has no such hint --
    plain server errors (500/502/504) don't carry one."""
    try:
        details = resp.json().get("error", {}).get("details", [])
    except (ValueError, AttributeError):
        return None
    for d in details:
        if not isinstance(d, dict):
            continue
        if "RetryInfo" not in d.get("@type", ""):
            continue
        delay = d.get("retryDelay", "")
        if isinstance(delay, str) and delay.endswith("s"):
            try:
                return float(delay[:-1])
            except ValueError:
                return None
    return None

# Per-model fallback targets: after failure_streak reaches 2 within one
# generate() call, switch to the mapped model rather than continuing to
# retry the one that's struggling. gemini-3.1-flash-lite has a 250k TPM
# cap and is the model builder/fix/trim calls use directly (with nowhere
# to fall back to previously, since REWRITE_FALLBACK_MODEL pointed at
# itself) -- gemma-4-31b-it has TPM Unlimited on this account's quota
# tiers, making it a real rescue path when flash-lite is under high
# demand, not just a same-model retry with backoff.
# gemini-3.5-flash-lite sits between them (2026-09-15): the old pair was
# each other's only rescue, and a probe that day found flash-lite 503ing and
# gemma-4-31b-it 500ing on every call while 3.5-flash-lite answered in <1s
# with the same schema + minimal-thinking config -- so the fallback just
# bounced between two failing models until the retries ran out. The swap
# resets the failure streak, so one call can walk more than one hop.
# 3.5-flash-lite became the default the same day (identical free-tier
# limits: 15 RPM / 250k TPM / 500 RPD), with 3.1 as its first rescue.
MODEL_FALLBACKS = {
    "gemini-3.5-flash-lite": "gemini-3.1-flash-lite",
    "gemini-3.1-flash-lite": "gemma-4-31b-it",
    "gemma-4-31b-it": "gemini-3.5-flash-lite",
}

# Scoring calls (fit evaluation, bullet scoring) must never land on
# gemini-3.5-flash-lite: re-scoring the same roles on it moved composite
# scores well past run-to-run noise (2026-09-15), so it has no scoring role
# at all. A 503 streak falls back to Gemma instead, which has its own quota;
# a call that exhausts both fails and the role is retried on a later run.
SCORING_FALLBACKS = {
    "gemini-3.1-flash-lite": "gemma-4-31b-it",
    "gemma-4-31b-it": "gemini-3.1-flash-lite",
}

# Grounded calls fall back only WITHIN the family that has quota for their
# tool -- MODEL_FALLBACKS would cross into a family with none (Search
# grounding is zero for every Gemini 3 model on the free tier; the 2.5
# models 404 for newer projects). Probed live 2026-09-15: gemma-4-31b-it
# 500ing on every Search call while gemma-4-26b-a4b-it grounded fine; both
# flash-lites return Maps chunks (500 RPD each).
GROUNDED_FALLBACKS = {
    "google_search": {
        "gemma-4-31b-it": "gemma-4-26b-a4b-it",
        "gemma-4-26b-a4b-it": "gemma-4-31b-it",
    },
    "google_maps": {
        "gemini-3.5-flash-lite": "gemini-3.1-flash-lite",
        "gemini-3.1-flash-lite": "gemini-3.5-flash-lite",
    },
}


def grounded_fallbacks(tools) -> dict:
    """The fallback map for a call using `tools` -- empty (no swap) unless it
    uses exactly one known grounding tool."""
    names = {name for tool in tools or [] if isinstance(tool, dict) for name in tool}
    if len(names) != 1:
        return {}
    return GROUNDED_FALLBACKS.get(names.pop(), {})

# Embedding model + dimension (matches orchestrator.py constants)
EMBED_MODEL = "gemini-embedding-2"
EMBED_DIM = 768  # gemini-embedding-2 native dimension


# Gemini reports a refusal as a `finishReason` on an otherwise-successful
# 200 response -- there is no exception to catch, so this never reaches
# cli_art's exception classifier and needs its own plain-language map.
# Codes are Google's; the wording is ours. An unmapped code falls through
# to _FINISH_REASON_DEFAULT rather than being printed raw, so a value
# Google adds later still reads as a sentence.
_FINISH_REASON_EXPLANATIONS = {
    "SAFETY": "Gemini's safety filter blocked its own answer to this request.",
    "PROHIBITED_CONTENT": "Gemini's safety filter blocked its own answer to this request.",
    "BLOCKLIST": "Gemini's safety filter blocked its own answer to this request.",
    "SPII": "Gemini stopped because its answer looked like it contained personal identifying information.",
    "RECITATION": "Gemini stopped because its answer was reproducing copyrighted text too closely.",
    "MALFORMED_FUNCTION_CALL": "Gemini returned a malformed response that couldn't be read.",
    "LANGUAGE": "Gemini stopped because the request was in a language it won't answer in.",
    "OTHER": "Gemini stopped early without saying why.",
}
_FINISH_REASON_DEFAULT = "Gemini stopped before finishing its answer."


class SustainedFailureError(RuntimeError):
    """Raised when GeminiClient.generate() has exhausted retries and the
    model fallback on SUSTAINED_FAILURE_THRESHOLD consecutive calls --
    a signal this is a quota-level issue, not a transient blip."""


_CONSECUTIVE_FAILURES_STATE = [0]


class _ConsecutiveFailuresDescriptor:

    def __get__(self, obj, cls=None):
        return _CONSECUTIVE_FAILURES_STATE[0]

    def __set__(self, obj, value):
        _CONSECUTIVE_FAILURES_STATE[0] = int(value)


class GeminiClient:

    _cache_map = {}
    # Models where a cache-creation call has already come back with a
    # permanent "this API key's tier allows zero cache storage" error
    # (TotalCachedContentStorageTokensPerModelFreeTier limit=0) -- as
    # opposed to an ordinary transient 429. That's a property of the
    # account/tier, not the request, so it won't succeed on retry within
    # this process. Without this, every call with a >=15k-char system
    # instruction re-attempts cache creation, eating a 30s timeout and
    # printing a warning, even though the outcome is already known.
    _cache_unavailable_models = set()

    @classmethod
    def _get_or_create_cache(cls, model: str, system_instruction: str) -> str | None:
        """
        Intercepts large system instructions, creates a cachedContent block
        on the Gemini REST API, and caches the returned cache handle for 20 minutes
        to prevent redundant transmissions and reduce tokens cost by up to 90%.
        """
        if "gemini" not in model.lower():
            return None

        # Explicit context caching on Gemini (1.5 / 2.0 / Flash / Pro) requires a minimum of
        # 32,768 tokens (roughly 131,072 characters in English at ~4 chars/token).
        # Calls under this limit are rejected by the REST API with HTTP 400.
        min_chars = int(os.environ.get("GEMINI_CACHE_MIN_CHARS", "131072"))
        if len(system_instruction) < min_chars:
            return None

        # Clean model name (caching needs models/ prefix)
        base_model = model.split(":")[0]
        if not base_model.startswith("models/"):
            base_model = f"models/{base_model}"

        if base_model in cls._cache_unavailable_models:
            return None

        # A cachedContent belongs to the Cloud project of the key that made
        # it, so each pooled key gets its own cache entry.
        api_key = _get_api_key(model)
        key = hashlib.sha256(
            f"{api_key}:{base_model}:{system_instruction}".encode("utf-8")
        ).hexdigest()
        now = time.time()

        if key in cls._cache_map:
            entry = cls._cache_map[key]
            if entry["expiry"] > now + 30:
                return entry["cache_name"]

        cache_url = "https://generativelanguage.googleapis.com/v1beta/cachedContents"
        payload = {
            "model": base_model,
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "ttl": "1200s",  # 20 minutes
        }
        try:
            req_headers = {**_get_auth_headers(model), "Content-Type": "application/json"}
            resp = requests.post(
                cache_url, json=payload, headers=req_headers, timeout=30
            )
            if resp.status_code == 200:
                data = resp.json()
                cache_name = data.get("name")
                expire_str = data.get("expireTime")
                expiry = now + 1150  # Default fallback expiry
                if expire_str:
                    try:
                        m = re.match(
                            r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})",
                            expire_str,
                        )
                        if m:
                            from datetime import datetime, timezone

                            dt = datetime(
                                int(m.group(1)),
                                int(m.group(2)),
                                int(m.group(3)),
                                int(m.group(4)),
                                int(m.group(5)),
                                int(m.group(6)),
                                tzinfo=timezone.utc,
                            )
                            expiry = dt.timestamp()
                    except Exception:
                        pass
                cls._cache_map[key] = {"cache_name": cache_name, "expiry": expiry}
                cli_art.console.print(
                    f"    {theme.colorize_icon('success')} Explicit Context Cache created: [dim]{cache_name}[/dim] (size: {len(system_instruction)} chars)",
                    soft_wrap=True,
                )
                return cache_name
            else:
                if "CachedContentStorageTokensPerModelFreeTier" in resp.text:
                    cls._cache_unavailable_models.add(base_model)
                    cli_art.console.print(
                        f"    {cli_art.WARNING} {base_model} is on a tier with no context-cache "
                        "storage quota -- disabling cache attempts for this model for the rest "
                        "of the run (falling back to full-prompt sends).",
                        soft_wrap=True,
                    )
                else:
                    cli_art.console.print(
                        f"    {cli_art.WARNING} Context cache creation failed (HTTP {resp.status_code}): {resp.text[:200]}",
                        soft_wrap=True,
                    )
                return None
        except Exception as e:
            cli_art.console.print(
                f"    {cli_art.WARNING} Context cache exception: {e}", soft_wrap=True
            )
            return None

    # Was 90 -- verified live (2026-07-16) that large-context calls to
    # gemini-3.1-flash-lite can genuinely take 100-140+s to respond right
    # now (confirmed by re-running an identical payload with a 180s cap,
    # which succeeded at 138s). 90s was cutting off requests that would
    # otherwise have completed, not detecting genuinely stuck ones.
    _timeout = 180
    _consecutive_full_failures = _ConsecutiveFailuresDescriptor()
    SUSTAINED_FAILURE_THRESHOLD = 2

    # gemma-4-31b-it's TPM cap is 16k tokens/minute (confirmed 2026-07-16),
    # and a single call's context now regularly runs 12k-17k tokens even
    # after slimming -- close enough to the full budget that two Gemma
    # calls landing in the same rolling minute can collide even though
    # each one alone would have fit. Spacing successive Gemma calls this
    # far apart lets the token bucket clear before the next one arrives,
    # rather than gambling on retry/backoff to recover an avoidable 429.
    # Lives here (not in rewrite_bullets.py) so orchestrator.py's Gemma
    # calls -- which go through this same shared client -- get it too.
    GEMMA_MIN_INTERVAL_SECS = 65
    _last_gemma_call_ts = 0.0

    @staticmethod
    def resolve_refs(schema: dict) -> dict:
        """
        Inlines every "$ref": "#/$defs/X" pointer with a deep copy of
        $defs["X"], then drops $defs from the tree.

        Pydantic's model_json_schema() emits nested BaseModel fields as
        $ref/$defs, but sanitize_schema() deletes $defs unconditionally
        (Gemini's structured-output API doesn't support $ref/$defs) -- so
        a nested model's schema would be left with a dangling $ref if this
        resolution didn't happen first, most likely producing a 400 from
        the API. Must run before sanitize_schema, not after.
        """
        if not isinstance(schema, dict):
            return schema
        defs = schema.get("$defs", {})

        def _resolve(node, seen):
            if isinstance(node, dict):
                if "$ref" in node:
                    key = node["$ref"].rsplit("/", 1)[-1]
                    if key in seen:
                        raise ValueError(
                            f"Circular $ref detected resolving schema: {node['$ref']}"
                        )
                    if key not in defs:
                        raise ValueError(f"Unresolvable $ref: {node['$ref']}")
                    return _resolve(copy.deepcopy(defs[key]), seen | {key})
                return {k: _resolve(v, seen) for k, v in node.items() if k != "$defs"}
            if isinstance(node, list):
                return [_resolve(item, seen) for item in node]
            return node

        return _resolve(schema, frozenset())

    @staticmethod
    def sanitize_schema(schema: dict) -> dict:
        UNSUPPORTED = {
            "title",
            "description",
            "$defs",
            "$schema",
            "default",
            "examples",
            "additionalProperties",
        }
        if not isinstance(schema, dict):
            return schema
        cleaned = {}
        for k, v in schema.items():
            if k == "properties" and isinstance(v, dict):
                # Keys here are field names, not schema metadata -- must
                # never be treated as candidates for UNSUPPORTED stripping,
                # even when a field happens to be named e.g. "title" (a job
                # title, not the $schema "title" keyword). A prior version
                # stripped this blindly and deleted a field literally named
                # "title" from properties while "required" still listed it,
                # producing "property is not defined" from the API. Each
                # property's own schema is still sanitized normally.
                cleaned[k] = {
                    name: GeminiClient.sanitize_schema(prop) for name, prop in v.items()
                }
                continue
            if k in UNSUPPORTED:
                continue
            if isinstance(v, dict):
                cleaned[k] = GeminiClient.sanitize_schema(v)
            elif isinstance(v, list):
                cleaned[k] = [
                    GeminiClient.sanitize_schema(i) if isinstance(i, dict) else i
                    for i in v
                ]
            else:
                cleaned[k] = v
        return cleaned

    @staticmethod
    def _salvage_fields(cleaned: str) -> dict:
        """
        Recovers top-level "key": value pairs by regex when json.loads()
        fails outright -- observed cause: the model produces a valid answer
        up front, then degenerates into repeating a phrase (e.g. echoing an
        instruction back at itself) until it runs out of output tokens,
        leaving the JSON string unterminated. The early, valid field(s)
        are still intact in the text even though the object as a whole
        never closes, so a full-string json.loads() throwing away
        everything is losing a real answer, not just discarding garbage.
        Only recovers string/number leaf values -- not lists/objects,
        which can't be delimited reliably without a real parser.
        """
        salvaged = {}
        for key, str_val in re.findall(r'"(\w+)"\s*:\s*"((?:\\.|[^"\\])*)"', cleaned):
            try:
                salvaged[key] = json.loads(f'"{str_val}"')
            except json.JSONDecodeError:
                continue
        for key, num_val in re.findall(r'"(\w+)"\s*:\s*(-?\d+(?:\.\d+)?)', cleaned):
            salvaged.setdefault(key, json.loads(num_val))
        return salvaged

    @staticmethod
    def parse_json(text: str) -> dict:
        if not text:
            return {}
        cleaned = re.sub(
            r"<think>.*?(?:</think>|<\/think>)", "", text, flags=re.DOTALL
        ).strip()
        if not cleaned:
            raise ValueError(
                "parse_json: string was empty after stripping thinking tokens."
            )
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"```\s*$", "", cleaned.strip(), flags=re.MULTILINE)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            salvaged = GeminiClient._salvage_fields(cleaned)
            if salvaged:
                cli_art.console.print(
                    f"    {cli_art.WARNING} parse_json() salvaged {len(salvaged)} field(s) from unterminated "
                    "JSON -- the response was truncated or malformed; treat this result as partial.",
                    soft_wrap=True,
                )
            return salvaged

    @staticmethod
    def generate(
        model: str,
        system_instruction: str,
        contents: str,
        response_schema=None,
        extra_schema_properties: dict = None,
        extra_required: list = None,
        temperature: float = 0.0,
        max_retries: int = 6,
        max_output_tokens: int = None,
        service_tier: str = "standard",
        model_fallback: bool = True,
        tools: list = None,
        inline_file: tuple[bytes, str] = None,
        fallbacks: dict = None,
    ) -> tuple[str | None, dict]:
        # fallbacks overrides MODEL_FALLBACKS for an ungrounded call -- e.g.
        # SCORING_FALLBACKS, which keeps a scoring call off 3.5-flash-lite.
        # inline_file, when given, is (raw_bytes, mime_type) -- e.g. a
        # screenshot PDF/PNG of a job posting (see jd_image_ingest.py).
        # Sent as a second `parts` entry alongside the text prompt, base64
        # inline (not the separate Files API) -- these screenshots are a
        # few MB, comfortably under Gemini's inline-request size limit, so
        # there's no reason to add the extra upload round-trip. Gemini's
        # documented PDF support reads an image-only PDF (no text layer)
        # the same way it reads a plain image, which is what makes this
        # viable at all -- pdfminer/pypdf extract nothing from a
        # screenshot-only PDF (confirmed empirically: 2 characters from a
        # real Tesla careers page screencapture).
        url = f"{BASE_URL}/{model}:generateContent"

        valid_tiers = {"standard", "priority", "flex"}
        tier = (service_tier or "standard").strip().lower()
        if tier not in valid_tiers:
            raise ValueError(f"Invalid service_tier {service_tier!r}.")

        # Google Search grounding (tools=[{"google_search": {}}]) and
        # structured JSON output (response_schema) have long been mutually
        # exclusive on Gemini's API -- a grounded call must return free-form
        # text with citations, not a schema-constrained object. Caught here
        # rather than surfacing as a confusing 400 from the API itself.
        if tools and response_schema is not None:
            raise ValueError(
                "generate(): tools (e.g. search grounding) and response_schema cannot be combined in one call."
            )
        # A grounded call never swaps models. Search-grounding quota is per
        # model FAMILY on the free tier -- zero for every Gemini 3 model,
        # 1.5K/day for the Gemma 4 models -- so a MODEL_FALLBACKS swap
        # (gemma-4-31b-it -> gemini-3.1-flash-lite) trades an intermittent
        # Gemma 500 for a guaranteed 429, spending the remaining retries on
        # a model that cannot ground at all. Failing on the original model
        # lets the caller fall through to its next tier sooner. (Gemma DOES
        # support Google Search -- verified live 2026-09-13; an earlier
        # version of this comment said otherwise.)
        # A grounded call swaps only within its tool's quota family (see
        # GROUNDED_FALLBACKS).
        if tools:
            fallbacks = grounded_fallbacks(tools)
        elif fallbacks is None:
            fallbacks = MODEL_FALLBACKS
        failure_streak = 0
        key_switches = 0

        for attempt in range(max_retries + len(api_keys())):
            # Switching to a fresh key after a 429 doesn't spend a retry.
            if attempt - key_switches >= max_retries:
                break
            if "gemma" in model.lower():
                elapsed = time.time() - GeminiClient._last_gemma_call_ts
                if elapsed < GeminiClient.GEMMA_MIN_INTERVAL_SECS:
                    wait = GeminiClient.GEMMA_MIN_INTERVAL_SECS - elapsed
                    cli_art.console.print(
                        f"    {theme.colorize_icon('hint')} Pacing Gemma call: waiting {wait:.1f}s (16k TPM cap)...",
                        soft_wrap=True,
                    )
                    if (
                        os.environ.get("CI") == "true"
                        or os.environ.get("RESUME_BUILDER_TESTING") == "1"
                    ) and not hasattr(time.sleep, "assert_called"):
                        pass
                    else:
                        time.sleep(wait)
                GeminiClient._last_gemma_call_ts = time.time()

            # Used to force temperature to 0.0 whenever response_schema was
            # set, regardless of what the caller passed -- silently
            # defeating orchestrator.py's stall-escalation block, which
            # computes an escalating fix_temperature specifically for its
            # own schema-constrained retry call. Real 2026-09-03 build: 4
            # fix attempts against the same TemplateSchema came back
            # byte-identical because every one of them was actually sent
            # at temperature 0.0 no matter what fix_temperature said.
            generation_config: dict = {"temperature": temperature}
            if max_output_tokens is not None:
                generation_config["maxOutputTokens"] = int(max_output_tokens)

            if "gemma" in model.lower():
                # Gemma 4 emits a "thought" reasoning preamble by default
                # (see the thought-part filter below) -- those tokens are
                # discarded but still billed against the 16k TPM cap.
                # thinkingLevel: "minimal" suppresses them at the source.
                generation_config["thinkingConfig"] = {"thinkingLevel": "minimal"}
            elif "flash-lite" in model.lower():
                # B46/P5#1 (phase-5-modernization.md): every flash-lite call
                # (CRITIQUE_MODEL, BUILDER_MODEL, FIND_WEBSITE_MODEL,
                # SCORE_MODEL) previously sent no thinkingConfig at all, so
                # it ran at whatever Google's current default is for this
                # tier -- confirmed "minimal", but this tier's default has
                # already shifted once (Gemini 3.5 Flash rollout). Pinning
                # it explicitly keeps today's behavior identical while
                # making it immune to a future silent default change.
                generation_config["thinkingConfig"] = {"thinkingLevel": "minimal"}

            raw_schema = None
            if response_schema is not None:
                generation_config["responseMimeType"] = "application/json"
                # Gemma must also get responseSchema, not just responseMimeType --
                # without it, Gemma defaults to emitting a "thought": true reasoning
                # part before the real answer, which breaks parts[0]-based extraction.
                if hasattr(response_schema, "model_json_schema"):
                    raw_schema = response_schema.model_json_schema()
                elif hasattr(response_schema, "schema") and callable(
                    response_schema.schema
                ):
                    raw_schema = response_schema.schema()
                elif isinstance(response_schema, dict):
                    raw_schema = response_schema
                elif isinstance(response_schema, str):
                    try:
                        raw_schema = json.loads(response_schema)
                    except json.JSONDecodeError:
                        cli_art.console.print(
                            f"{cli_art.ERROR} response_schema string is not valid JSON.",
                            soft_wrap=True,
                        )
                if raw_schema and (extra_schema_properties or extra_required):
                    # Callers that need profile-specific enum fields not knowable
                    # at Pydantic class-definition time (e.g. orchestrator.py's
                    # per-profile education achievement-key options) merge them
                    # in here rather than passing a hand-built dict as
                    # response_schema -- this keeps response_schema=SomeModel
                    # identity-comparable in tests/mocks that route on it, and
                    # keeps the merge applied before resolve_refs/sanitize_schema
                    # so it goes through the exact same pipeline as every other
                    # property. Copies rather than mutates raw_schema in place,
                    # since a Pydantic-sourced dict could in principle be reused
                    # across calls.
                    raw_schema = dict(raw_schema)
                    raw_schema["properties"] = {
                        **raw_schema.get("properties", {}),
                        **(extra_schema_properties or {}),
                    }
                    raw_schema["required"] = list(
                        raw_schema.get("required", [])
                    ) + list(extra_required or [])
                if raw_schema:
                    generation_config["responseSchema"] = GeminiClient.sanitize_schema(
                        GeminiClient.resolve_refs(raw_schema)
                    )

            # systemInstruction as its own top-level field, same shape for
            # every model -- current Gemma-4-on-Gemini-API docs show it
            # supported natively; the earlier manual merge into `contents`
            # was a workaround for older Gemma versions that didn't respect
            # a separate systemInstruction field.
            # Attempt to use or create explicit context cache for Gemini requests
            cache_name = None
            if "gemini" in model.lower():
                cache_name = GeminiClient._get_or_create_cache(
                    model, system_instruction
                )

            parts = [{"text": contents}]
            if inline_file is not None:
                file_bytes, mime_type = inline_file
                parts.append(
                    {
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": base64.b64encode(file_bytes).decode("ascii"),
                        }
                    }
                )

            body = {
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": generation_config,
                "serviceTier": tier,
            }
            if cache_name:
                body["cachedContent"] = cache_name
            else:
                body["systemInstruction"] = {"parts": [{"text": system_instruction}]}

            if tools:
                body["tools"] = tools

            rate_limiter.acquire(1.0)
            used_key = _get_auth_headers(model)["x-goog-api-key"]
            try:
                resp = requests.post(
                    url,
                    json=body,
                    headers={"x-goog-api-key": used_key},
                    timeout=GeminiClient._timeout,
                )
                # Self-healing fallback: if cachedContent expired or was evicted (HTTP 400), fall back immediately
                if (
                    resp.status_code == 400
                    and cache_name
                    and "cache" in resp.text.lower()
                ):
                    # Evict from class map
                    cls_key = None
                    for k, entry in GeminiClient._cache_map.items():
                        if entry.get("cache_name") == cache_name:
                            cls_key = k
                            break
                    if cls_key:
                        GeminiClient._cache_map.pop(cls_key, None)
                    cli_art.console.print(
                        f"    {theme.colorize_icon('warning')} Context cache expired or evicted. Self-healing fallback to inline systemInstruction...",
                        soft_wrap=True,
                    )
                    # Retry this attempt with inline systemInstruction directly
                    body.pop("cachedContent", None)
                    body["systemInstruction"] = {
                        "parts": [{"text": system_instruction}]
                    }
                    resp = requests.post(
                        url,
                        json=body,
                        headers={"x-goog-api-key": used_key},
                        timeout=GeminiClient._timeout,
                    )
            except requests.exceptions.RequestException as e:
                failure_streak += 1
                if model_fallback and failure_streak >= 2 and model in fallbacks:
                    fallback_model = fallbacks[model]
                    cli_art.console.print(
                        f"    {cli_art.WARNING} Transport failures — falling back to {fallback_model}...",
                        soft_wrap=True,
                    )
                    model = fallback_model
                    url = f"{BASE_URL}/{model}:generateContent"
                    failure_streak = 0
                sleep_dur = (
                    0
                    if (
                        os.environ.get("CI") == "true"
                        or os.environ.get("RESUME_BUILDER_TESTING") == "1"
                    )
                    else min(BASE_BACKOFF_SECS * (2**attempt), MAX_BACKOFF_SECS)
                    + random.uniform(1, 4)
                )
                cli_art.console.print(
                    f"    {cli_art.WARNING} Network error ({GeminiClient._timeout}s): {type(e).__name__}: {str(e)[:120]}. "
                    f"Waiting {sleep_dur:.1f}s before retry {attempt+1}/{max_retries}...",
                    soft_wrap=True,
                )
                time.sleep(sleep_dur)
                continue

            if resp.status_code in SERVER_ERRORS:
                failure_streak += 1
            elif resp.status_code == 429:
                if mark_key_rate_limited(
                    used_key, model, _server_retry_delay_secs(resp)
                ):
                    key_switches += 1
                    cli_art.console.print(
                        f"    {cli_art.WARNING} Rate limited on {key_label(used_key)} -- "
                        f"switching to {key_label(_get_api_key(model))}.",
                        soft_wrap=True,
                    )
                    continue
                failure_streak += 1

            if resp.status_code == HIGH_DEMAND_STATUS:
                cli_art.console.print(
                    f"    {cli_art.WARNING} Model high demand (503). Treating as transient.",
                    soft_wrap=True,
                )

            if resp.status_code in RETRYABLE:
                if model_fallback and failure_streak >= 2 and model in fallbacks:
                    fallback_model = fallbacks[model]
                    cli_art.console.print(
                        f"    {cli_art.WARNING} Server failures — falling back to {fallback_model}...",
                        soft_wrap=True,
                    )
                    model = fallback_model
                    url = f"{BASE_URL}/{model}:generateContent"
                    failure_streak = 0
                server_delay = _server_retry_delay_secs(resp)
                if (
                    os.environ.get("CI") == "true"
                    or os.environ.get("RESUME_BUILDER_TESTING") == "1"
                ):
                    sleep_dur = 0
                elif server_delay is not None:
                    # The server's own RetryInfo hint beats our guessed
                    # exponential curve -- a small buffer on top since the
                    # hint is the earliest safe retry time, not a
                    # guarantee, and free-tier quota windows are unforgiving.
                    sleep_dur = server_delay + random.uniform(1, 4)
                else:
                    sleep_dur = min(
                        BASE_BACKOFF_SECS * (2**attempt), MAX_BACKOFF_SECS
                    ) + random.uniform(1, 4)
                cli_art.console.print(
                    f"    {cli_art.WARNING} HTTP {resp.status_code}. Waiting {sleep_dur:.1f}s"
                    f"{' (server-specified)' if server_delay is not None else ''} (retry {attempt+1}/{max_retries})...",
                    soft_wrap=True,
                )
                time.sleep(sleep_dur)
                continue

            if resp.status_code in (400, 404):
                cli_art.console.print(
                    f"    {cli_art.WARNING} Gemini API permanent error {resp.status_code}: {resp.reason}. Not retrying.",
                    soft_wrap=True,
                )
                try:
                    cli_art.print_literal(json.dumps(resp.json(), indent=2)[:800])
                except Exception:
                    cli_art.print_literal(resp.text[:800])
                return None, {}

            try:
                resp.raise_for_status()
            except requests.exceptions.HTTPError as e:
                cli_art.console.print(
                    f"    {cli_art.WARNING} HTTP error {resp.status_code}: {e}. Not retrying.",
                    soft_wrap=True,
                )
                return None, {}

            try:
                data = resp.json()
            except Exception as e:
                cli_art.friendly_warning(
                    e,
                    "reading the AI's response",
                    "treating this request as if it came back empty",
                )
                return None, {}

            candidates = data.get("candidates", [])
            if not candidates:
                return None, data.get("usageMetadata", {})

            usage = data.get("usageMetadata", {})

            finish_reason = candidates[0].get("finishReason")
            if finish_reason not in (None, "STOP", "MAX_TOKENS"):
                cli_art.cli_warning(
                    f"{_FINISH_REASON_EXPLANATIONS.get(finish_reason, _FINISH_REASON_DEFAULT)} "
                    "Skipping this one and moving on."
                )
                # Raw API code kept as VERBOSE-only detail: it's the first
                # thing worth knowing when debugging a prompt, and the last
                # thing a job seeker needs on screen.
                cli_art.detail(f"    finishReason={finish_reason!r}")
                return None, usage
            if finish_reason == "MAX_TOKENS":
                usage["truncated"] = True

            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            # Skip thinking parts (part.get("thought") is True) -- Gemma without
            # a schema puts its reasoning in parts[0] and the real answer later;
            # concatenate only the non-thought parts to get the actual response.
            text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
            failure_streak = 0
            GeminiClient._consecutive_full_failures = 0
            return text, usage

        GeminiClient._consecutive_full_failures += 1
        if (
            GeminiClient._consecutive_full_failures
            >= GeminiClient.SUSTAINED_FAILURE_THRESHOLD
        ):
            failures = GeminiClient._consecutive_full_failures
            GeminiClient._consecutive_full_failures = 0
            raise SustainedFailureError(
                f"GeminiClient.generate() exhausted retries on {failures} consecutive "
                f"calls (model={model}) -- this looks like a sustained quota issue, not "
                "a transient blip. Add backup keys (GEMINI_API_KEY_2, GEMINI_API_KEY_3 -- each from a different Google Cloud project) to .env, or swap GEMINI_API_KEY, and re-run."
            )
        return None, {}

    @staticmethod
    def embed(text: str) -> list[float] | None:
        """
        Generates an embedding vector for the given text using EMBED_MODEL.
        Used by orchestrator.py's mine_bullet_bank() for semantic similarity.
        Native output dimension: 768 (gemini-embedding-2).
        """
        url = f"{BASE_URL}/{EMBED_MODEL}:embedContent"
        payload = {
            "model": f"models/{EMBED_MODEL}",
            "content": {"parts": [{"text": text}]},
            "outputDimensionality": EMBED_DIM,
        }
        rate_limiter.acquire(1.0)
        try:
            headers = _get_auth_headers(EMBED_MODEL)
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            if resp.status_code == 429 and mark_key_rate_limited(
                headers["x-goog-api-key"], EMBED_MODEL
            ):
                resp = requests.post(
                    url, json=payload, headers=_get_auth_headers(EMBED_MODEL), timeout=30
                )
            resp.raise_for_status()
            return resp.json().get("embedding", {}).get("values")
        except Exception as e:
            cli_art.console.print(
                f"    {cli_art.WARNING} Embed error: {e}", soft_wrap=True
            )
            return None


class OllamaClient:
    """Local offline LLM client for Ollama / vLLM execution without cloud API keys."""

    DEFAULT_HOST = "http://localhost:11434"
    DEFAULT_MODEL = "llama3.2"

    @staticmethod
    def is_available(host: str = DEFAULT_HOST) -> bool:
        """Checks if the local Ollama daemon is reachable."""
        try:
            resp = requests.get(f"{host}/api/tags", timeout=2)
            return resp.status_code == 200
        except Exception:
            return False

    @staticmethod
    def generate(
        prompt: str,
        system_instruction: str = "",
        model: str = DEFAULT_MODEL,
        host: str = DEFAULT_HOST,
        temperature: float = 0.0,
    ) -> str | None:
        """Generates a text completion using the local Ollama instance."""
        url = f"{host}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "system": system_instruction,
            "stream": False,
            "options": {"temperature": temperature},
        }
        try:
            resp = requests.post(url, json=payload, timeout=120)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("response", "")
            return None
        except Exception:
            return None
