"""Runs the plugin once against a Brain named by BRAIN_API_URL and
BRAIN_API_TOKEN, and prints what each hook returned as one JSON object.

Not a unittest module (its name keeps it out of discovery): the Brain's
integration test `tests/integration/hermes-plugin.test.ts` starts a test
instance, runs this, and holds the output to what the endpoint answered.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.support import load_plugin  # noqa: E402

brain = load_plugin()


def run(platform: str, agent_context: str) -> dict:
    p = brain.BrainMemoryProvider()
    p.initialize(
        f"live-{platform}-{agent_context}",
        platform=platform,
        hermes_home=tempfile.gettempdir(),
        agent_context=agent_context,
    )
    return {"block": p.system_prompt_block(), "time_line": p.prefetch("hello")}


print(
    json.dumps(
        {
            "available": brain.BrainMemoryProvider().is_available(),
            "primary": run("telegram", "primary"),
            "subagent": run("telegram", "subagent"),
            "panel": run("api_server", "primary"),
        }
    )
)
