"""What every test here shares: the plugin, loaded against Hermes' real base
class, and a local Brain that answers what a test tells it to.

Standard library only, like the plugin.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
import time
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "brain"
FIXTURES = ROOT / "tests" / "fixtures"

# Hermes' `agent/memory_provider.py` at the tested tag, unchanged (see
# tests/hermes/README.md). The plugin imports its base class from there.
HERMES_BASE = ROOT / "tests" / "hermes" / "memory_provider.py"
HERMES_TAG = "v2026.8.31"
HERMES_VERSION = "0.21.0"
HERMES_COMMIT = "29112bef099274229cadff79cdff7bf7b99c4b77"
HERMES_BASE_SHA256 = "902e061d33b372cc28facd8c7bf7fe032aacda3f17ea1e4107fea9fd01885335"


def contract_path() -> Path:
    """The briefing's JSON Schema: in Brain's repository two levels up, in the
    public mirror beside the plugin."""
    for candidate in (
        ROOT.parent.parent / "contracts" / "v1" / "briefing.schema.json",
        ROOT / "contracts" / "v1" / "briefing.schema.json",
    ):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("contracts/v1/briefing.schema.json")


def load_plugin() -> types.ModuleType:
    """Import `brain` the way Hermes would see it: with `agent.memory_provider`
    importable and nothing else of Hermes."""
    if "agent.memory_provider" not in sys.modules:
        agent = types.ModuleType("agent")
        agent.__path__ = []  # a package, so the submodule resolves
        sys.modules.setdefault("agent", agent)
        spec = importlib.util.spec_from_file_location("agent.memory_provider", HERMES_BASE)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules["agent.memory_provider"] = module
        spec.loader.exec_module(module)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import brain

    return brain


PERSONA = "Persona block: a test persona, rendered by the Brain."
PROFILE = "Profile block: a test profile, rendered by the Brain."
ZONE = "Europe/Berlin"
TOKEN = "plugin-test-token-0123456789"


def briefing(**overrides: Any) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "persona_block": PERSONA,
        "profile_block": PROFILE,
        "zone": ZONE,
        "as_of": "2026-10-29T09:14:00+01:00",
        "knows_me": True,
    }
    body.update(overrides)
    return body


class Recorded:
    def __init__(self, method: str, path: str, headers: Dict[str, str], body: bytes):
        self.method = method
        self.path = path
        self.headers = headers
        self.body = body

    def raw(self) -> str:
        head = "\n".join(f"{k}: {v}" for k, v in self.headers.items())
        return f"{self.method} {self.path}\n{head}\n\n{self.body.decode('latin-1')}"


class FakeBrain:
    """A Brain on 127.0.0.1 that answers `status` with `body` after `delay`."""

    def __init__(self) -> None:
        self.status = 200
        self.body: bytes = json.dumps(briefing()).encode()
        self.delay = 0.0
        self.location: Optional[str] = None
        self.requests: List[Recorded] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def _answer(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                fake.requests.append(
                    Recorded(self.command, self.path, dict(self.headers.items()), body)
                )
                if fake.delay:
                    time.sleep(fake.delay)
                try:
                    self.send_response(fake.status)
                    if fake.location:
                        self.send_header("Location", fake.location)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(fake.body)))
                    self.end_headers()
                    self.wfile.write(fake.body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _answer

            def log_message(self, format: str, *args: Any) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(
            target=self._server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
        )
        self._thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def answer(self, status: int, body: Any = None, delay: float = 0.0) -> None:
        self.status = status
        if body is None:
            body = briefing() if status == 200 else {"error": "x"}
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.delay = delay

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
