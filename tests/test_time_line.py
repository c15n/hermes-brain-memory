"""The time line (ADR-0052 §3), held to the fixture the Brain's own
`currentLocalTimeLine` test reads, so the two renderings say the same."""

from __future__ import annotations

import json
import unittest
from datetime import datetime

from tests.support import FIXTURES, load_plugin

brain = load_plugin()
FIXTURE = json.loads((FIXTURES / "time-lines.json").read_text("utf-8"))


def instant(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


class TimeLine(unittest.TestCase):
    def test_every_fixture_line(self) -> None:
        self.assertGreater(len(FIXTURE["lines"]), 0)
        for case in FIXTURE["lines"]:
            with self.subTest(case["why"]):
                self.assertEqual(
                    brain.current_local_time_line(instant(case["at"]), case["zone"]),
                    case["line"],
                )

    def test_an_unknown_zone_gives_nothing(self) -> None:
        self.assertGreater(len(FIXTURE["unknown_zones"]), 0)
        at = instant(FIXTURE["lines"][0]["at"])
        for zone in FIXTURE["unknown_zones"]:
            with self.subTest(zone=zone):
                self.assertEqual(brain.current_local_time_line(at, zone), "")


if __name__ == "__main__":
    unittest.main()
