"""Brain memory provider for Hermes.

Fetches one briefing per Hermes session from a Brain instance
(``GET /v1/me/briefing``) and hands it to Hermes as the provider's system-prompt
block. Every word of that block is rendered by the Brain; the only text this
plugin writes itself is the time line ``prefetch()`` returns.

Version 0.1 sends nothing of a conversation to the Brain. Its one request is
the GET above, with no query string and no body.

Standard library only: this module runs inside Hermes' own environment and
must not bring a dependency into it.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from agent.memory_provider import MemoryProvider

__version__ = "0.1.0"

logger = logging.getLogger(__name__)

BRIEFING_PATH = "/v1/me/briefing"

# Hermes does not bound system_prompt_block() in time, so the request must.
TIMEOUT_SECONDS = 3.0

# How long the last good answer may stand in after a network error or a 5xx.
# Never after a 401/403: a revoked or narrowed token is not answered from memory.
FALLBACK_SECONDS = 15 * 60

# The two blocks are bounded at 4,000 characters by the Brain; this is a
# backstop against a body that is not a briefing at all.
MAX_BODY_BYTES = 64 * 1024

# Hermes' platform name for its OpenAI-compatible API server: the Brain's panel.
# The panel gets everything from the Brain's own instructions, so the plugin
# stays silent there and a turn never carries the briefing twice.
PANEL_PLATFORM = "api_server"

PRIMARY_CONTEXT = "primary"

# The fields the plugin reads, with their types. Fields it does not know are
# ignored (the path versions the contract, /v1 only ever gains fields).
REQUIRED_FIELDS: Dict[str, type] = {
    "persona_block": str,
    "profile_block": str,
    "zone": str,
    "as_of": str,
    "knows_me": bool,
}

# English and fixed, not the host's locale, so the line reads the same on every
# host and exactly as the Brain's own `currentLocalTimeLine` writes it.
# Indexed by datetime.weekday(): Monday is 0.
WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _monotonic() -> float:
    return time.monotonic()


def current_local_time_line(at: datetime, zone: str) -> str:
    """``Current local time: Thursday 2026-10-29 14:05 (Europe/Berlin)``.

    "Current local time", not "as of": Hermes' own date line uses "as of" for
    an old state, and this one means now. An empty or unknown zone gives "".
    """
    if not zone:
        return ""
    try:
        from zoneinfo import ZoneInfo

        local = at.astimezone(ZoneInfo(zone))
    except Exception:
        return ""
    return (
        f"Current local time: {WEEKDAYS[local.weekday()]} "
        f"{local.year:04d}-{local.month:02d}-{local.day:02d} "
        f"{local.hour:02d}:{local.minute:02d} ({zone})"
    )


def _parse_briefing(body: bytes) -> Optional[Dict[str, Any]]:
    """The fields the plugin needs, or None when the body is not a briefing."""
    try:
        data = json.loads(body.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    briefing: Dict[str, Any] = {}
    for field, kind in REQUIRED_FIELDS.items():
        value = data.get(field)
        if not isinstance(value, kind):
            return None
        briefing[field] = value
    if not briefing["zone"]:
        return None
    return briefing


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect would carry the token to wherever it points; refuse it."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


_opener = urllib.request.build_opener(_NoRedirect())

# The last good answer, kept across provider instances: Hermes' gateway builds
# a new agent, and with it a new provider, for a new session, which is exactly
# when a Brain deploy would otherwise leave the session with nothing. Keyed by
# the URL and a hash of the token, so another credential never reads it.
_fallback_lock = threading.Lock()
_fallback: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def _credential_key(url: str, token: str) -> str:
    return hashlib.sha256(f"{url}\n{token}".encode("utf-8")).hexdigest()


def _remember(key: str, briefing: Dict[str, Any]) -> None:
    with _fallback_lock:
        _fallback[key] = (_monotonic(), briefing)


def _forget(key: str) -> None:
    with _fallback_lock:
        _fallback.pop(key, None)


def _recall(key: str) -> Optional[Dict[str, Any]]:
    with _fallback_lock:
        entry = _fallback.get(key)
    if entry is None:
        return None
    stored_at, briefing = entry
    if _monotonic() - stored_at > FALLBACK_SECONDS:
        return None
    return briefing


def _settings() -> Optional[Tuple[str, str]]:
    """The base URL (without /v1) and the token, from the profile's environment."""
    url = os.environ.get("BRAIN_API_URL", "").strip().rstrip("/")
    token = os.environ.get("BRAIN_API_TOKEN", "").strip()
    if not url or not token:
        return None
    if not url.startswith(("https://", "http://")):
        return None
    return url, token


def fetch_briefing() -> Tuple[Optional[Dict[str, Any]], bool]:
    """One GET of the briefing, with the fallback rules of ADR-0052 §4.

    Returns the briefing (or None) and whether the Brain refused the token.
    Logs the status code and the body's length only — never a block or the
    token.
    """
    settings = _settings()
    if settings is None:
        return None, False
    url, token = settings
    key = _credential_key(url, token)
    request = urllib.request.Request(
        url + BRIEFING_PATH,
        method="GET",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": f"hermes-brain-memory/{__version__}",
        },
    )
    try:
        with _opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            status = response.status
            body = response.read(MAX_BODY_BYTES + 1)
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
        if status in (401, 403):
            _forget(key)
            logger.info("Brain briefing: HTTP %d, nothing used", status)
            return None, True
        if status >= 500:
            logger.info("Brain briefing: HTTP %d, falling back", status)
            return _recall(key), False
        logger.info("Brain briefing: HTTP %d, nothing used", status)
        return None, False
    except Exception as error:
        # Timeouts, refused connections, TLS and DNS failures. The class name
        # only: an exception's message may carry the URL.
        logger.info("Brain briefing: %s, falling back", type(error).__name__)
        return _recall(key), False

    if status != 200 or len(body) > MAX_BODY_BYTES:
        logger.info("Brain briefing: HTTP %d, %d bytes, nothing used", status, len(body))
        return None, False
    briefing = _parse_briefing(body)
    if briefing is None:
        logger.info("Brain briefing: HTTP 200, %d bytes, not a briefing", len(body))
        return None, False
    logger.info("Brain briefing: HTTP 200, %d bytes", len(body))
    _remember(key, briefing)
    return briefing, False


class BrainMemoryProvider(MemoryProvider):
    """Context only: no tools, no recall indicator, no writes.

    Every hook that receives a message — ``sync_turn``, ``queue_prefetch``,
    ``on_session_end``, ``on_pre_compress``, ``on_memory_write``,
    ``on_delegation`` — is left as the base class's no-op. ``prefetch`` and
    ``on_turn_start`` are overridden but never read or send their message.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._session_id = ""
        self._platform = ""
        self._agent_context = ""
        # The briefing of the current session, fetched at most once for it.
        self._briefing: Optional[Dict[str, Any]] = None
        self._briefing_session: Optional[str] = None
        # The zone of the last briefing this provider obtained. It outlives the
        # session switch, because a resumed session reuses its stored prompt
        # and system_prompt_block() is not asked again; a refused token clears it.
        self._zone = ""

    @property
    def name(self) -> str:
        return "brain"

    def is_available(self) -> bool:
        # No network here (Hermes' contract): configured is available.
        return _settings() is not None

    def initialize(self, session_id: str, **kwargs: Any) -> None:
        try:
            with self._lock:
                self._session_id = str(session_id or "")
                self._platform = str(kwargs.get("platform") or "")
                self._agent_context = str(kwargs.get("agent_context") or "")
        except Exception:
            pass

    def on_turn_start(self, turn_number: int, message: str, **kwargs: Any) -> None:
        # Only the runtime context, for a Hermes that did not hand it to
        # initialize(). The message is not read.
        try:
            with self._lock:
                if not self._platform and kwargs.get("platform"):
                    self._platform = str(kwargs["platform"])
                if not self._agent_context and kwargs.get("agent_context"):
                    self._agent_context = str(kwargs["agent_context"])
        except Exception:
            pass

    def on_session_switch(
        self,
        new_session_id: str,
        *,
        parent_session_id: str = "",
        reset: bool = False,
        rewound: bool = False,
        **kwargs: Any,
    ) -> None:
        # /new, /reset, /resume, /branch and compression: a new session id is a
        # new session, and its block is fetched again — that is how a changed
        # persona or profile reaches a running chat.
        try:
            with self._lock:
                self._session_id = str(new_session_id or "")
        except Exception:
            pass

    def _in_panel(self) -> bool:
        return self._platform == PANEL_PLATFORM

    def _session_briefing(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            if self._briefing_session == self._session_id:
                return self._briefing
            session = self._session_id
        briefing, refused = fetch_briefing()
        with self._lock:
            if briefing is not None:
                self._zone = briefing["zone"]
            elif refused:
                self._zone = ""
            # Only a briefing is kept for the session; after a failure the next
            # build of the prompt (compression, say) asks again.
            if briefing is not None and self._session_id == session:
                self._briefing = briefing
                self._briefing_session = session
            elif self._session_id == session:
                self._briefing = None
                self._briefing_session = None
        return briefing

    def system_prompt_block(self) -> str:
        try:
            if self._in_panel():
                return ""
            briefing = self._session_briefing()
            if briefing is None:
                return ""
            persona = briefing["persona_block"].strip()
            context = self._agent_context or PRIMARY_CONTEXT
            if context != PRIMARY_CONTEXT:
                return persona
            profile = briefing["profile_block"].strip()
            return "\n\n".join(part for part in (persona, profile) if part)
        except Exception:
            return ""

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        # The query is not used and not sent anywhere: the line is rendered
        # here, from the zone of the last briefing, with no request per turn.
        try:
            if self._in_panel():
                return ""
            with self._lock:
                zone = self._zone
            return current_local_time_line(_utcnow(), zone)
        except Exception:
            return ""

    def recall_status(self) -> None:
        return None

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return []


def register(ctx: Any) -> None:
    ctx.register_memory_provider(BrainMemoryProvider())
