"""The provider's behaviour against a local Brain (ADR-0052 §4, §10)."""

from __future__ import annotations

import json
import logging
import os
import unittest
from datetime import datetime, timezone
from unittest import mock

from tests.support import (
    PERSONA,
    PROFILE,
    TOKEN,
    ZONE,
    FakeBrain,
    briefing,
    load_plugin,
)

brain = load_plugin()

# A pinned instant (TESTING.md: time-dependent logic pins the day).
NOW = datetime(2026, 10, 29, 13, 5, tzinfo=timezone.utc)
TIME_LINE = "Current local time: Thursday 2026-10-29 14:05 (Europe/Berlin)"
BOTH = PERSONA + "\n\n" + PROFILE

# Words that would only reach a request if a hook sent what it was given.
MESSAGE = "the person's own words: my back hurts"


class ProviderCase(unittest.TestCase):
    def setUp(self) -> None:
        self.server = FakeBrain()
        self.addCleanup(self.server.close)
        env = mock.patch.dict(
            os.environ, {"BRAIN_API_URL": self.server.url, "BRAIN_API_TOKEN": TOKEN}
        )
        env.start()
        self.addCleanup(env.stop)
        brain._fallback.clear()
        self.addCleanup(brain._fallback.clear)
        self.clock = 1000.0
        monotonic = mock.patch.object(brain, "_monotonic", lambda: self.clock)
        monotonic.start()
        self.addCleanup(monotonic.stop)
        utcnow = mock.patch.object(brain, "_utcnow", lambda: NOW)
        utcnow.start()
        self.addCleanup(utcnow.stop)
        timeout = mock.patch.object(brain, "TIMEOUT_SECONDS", 0.3)
        timeout.start()
        self.addCleanup(timeout.stop)

    def provider(self, session: str = "s1", **kwargs: str):
        p = brain.BrainMemoryProvider()
        kwargs.setdefault("platform", "telegram")
        kwargs.setdefault("hermes_home", "/tmp/hermes-home")
        p.initialize(session, **kwargs)
        return p

    def remember_a_good_answer(self) -> None:
        self.assertEqual(self.provider("good").system_prompt_block(), BOTH)


class Availability(ProviderCase):
    def test_available_when_url_and_token_are_set_without_a_request(self) -> None:
        self.assertTrue(brain.BrainMemoryProvider().is_available())
        self.assertEqual(self.server.requests, [])

    def test_unavailable_without_either(self) -> None:
        for missing in ("BRAIN_API_URL", "BRAIN_API_TOKEN"):
            with mock.patch.dict(os.environ, {missing: "  "}):
                self.assertFalse(brain.BrainMemoryProvider().is_available(), missing)
        with mock.patch.dict(os.environ, {"BRAIN_API_URL": "file:///etc/passwd"}):
            self.assertFalse(brain.BrainMemoryProvider().is_available())
        self.assertEqual(self.server.requests, [])

    def test_no_tools_and_no_recall_indicator(self) -> None:
        p = self.provider()
        self.assertEqual(p.get_tool_schemas(), [])
        self.assertIsNone(p.recall_status())
        self.assertEqual(p.name, "brain")

    def test_register_hands_hermes_one_provider(self) -> None:
        ctx = mock.Mock()
        brain.register(ctx)
        ctx.register_memory_provider.assert_called_once()
        (provider,), _ = ctx.register_memory_provider.call_args
        self.assertIsInstance(provider, brain.BrainMemoryProvider)


class SessionBlock(ProviderCase):
    def test_primary_gets_the_persona_then_the_profile(self) -> None:
        self.assertEqual(self.provider(agent_context="primary").system_prompt_block(), BOTH)

    def test_absent_agent_context_counts_as_primary(self) -> None:
        self.assertEqual(self.provider().system_prompt_block(), BOTH)

    def test_any_other_context_gets_the_persona_only(self) -> None:
        for context in ("subagent", "cron", "flush"):
            self.assertEqual(
                self.provider(agent_context=context).system_prompt_block(), PERSONA, context
            )

    def test_one_request_per_session_and_again_for_a_new_one(self) -> None:
        p = self.provider()
        p.system_prompt_block()
        p.system_prompt_block()
        self.assertEqual(len(self.server.requests), 1)
        p.on_session_switch("s2", parent_session_id="s1", reset=True)
        p.system_prompt_block()
        self.assertEqual(len(self.server.requests), 2)

    def test_the_request_is_one_bare_get_with_the_token(self) -> None:
        self.provider().system_prompt_block()
        (request,) = self.server.requests
        self.assertEqual(request.method, "GET")
        self.assertEqual(request.path, "/v1/me/briefing")
        self.assertEqual(request.body, b"")
        self.assertEqual(request.headers.get("Authorization"), f"Bearer {TOKEN}")

    def test_a_trailing_slash_on_the_url_changes_nothing(self) -> None:
        with mock.patch.dict(os.environ, {"BRAIN_API_URL": self.server.url + "/"}):
            self.assertEqual(self.provider().system_prompt_block(), BOTH)
        self.assertEqual(self.server.requests[0].path, "/v1/me/briefing")

    def test_an_empty_profile_block_leaves_the_persona_alone(self) -> None:
        self.server.answer(200, briefing(profile_block=""))
        self.assertEqual(self.provider().system_prompt_block(), PERSONA)

    def test_unknown_fields_are_ignored(self) -> None:
        self.server.answer(200, briefing(later_field={"nested": [1, 2]}, another="x"))
        self.assertEqual(self.provider().system_prompt_block(), BOTH)


class Panel(ProviderCase):
    def test_api_server_gets_nothing_from_either_hook_and_no_request(self) -> None:
        p = self.provider(platform="api_server")
        self.assertEqual(p.system_prompt_block(), "")
        self.assertEqual(p.prefetch("hello"), "")
        self.assertEqual(self.server.requests, [])

    def test_platform_from_on_turn_start_when_initialize_had_none(self) -> None:
        p = brain.BrainMemoryProvider()
        p.initialize("s1", hermes_home="/tmp/hermes-home")
        p.on_turn_start(1, MESSAGE, platform="api_server")
        self.assertEqual(p.system_prompt_block(), "")
        self.assertEqual(self.server.requests, [])

    def test_agent_context_from_on_turn_start_when_initialize_had_none(self) -> None:
        p = self.provider()
        p.on_turn_start(1, MESSAGE, agent_context="subagent")
        self.assertEqual(p.system_prompt_block(), PERSONA)


class Fallback(ProviderCase):
    def test_a_5xx_or_a_timeout_with_nothing_remembered_gives_nothing(self) -> None:
        self.server.answer(503)
        self.assertEqual(self.provider("a").system_prompt_block(), "")
        self.server.answer(200, delay=1.0)
        self.assertEqual(self.provider("b").system_prompt_block(), "")

    def test_a_5xx_uses_the_last_good_answer_under_15_minutes(self) -> None:
        self.remember_a_good_answer()
        self.server.answer(502)
        self.clock += 14 * 60
        self.assertEqual(self.provider("later").system_prompt_block(), BOTH)

    def test_a_timeout_uses_the_last_good_answer_under_15_minutes(self) -> None:
        self.remember_a_good_answer()
        self.server.answer(200, delay=1.0)
        self.clock += 60
        self.assertEqual(self.provider("later").system_prompt_block(), BOTH)

    def test_a_refused_connection_uses_the_last_good_answer(self) -> None:
        self.remember_a_good_answer()
        self.server.close()
        self.assertEqual(self.provider("later").system_prompt_block(), BOTH)
        self.server = FakeBrain()  # for the cleanup's close()

    def test_the_last_good_answer_expires_after_15_minutes(self) -> None:
        self.remember_a_good_answer()
        self.server.answer(500)
        self.clock += 15 * 60 + 1
        self.assertEqual(self.provider("later").system_prompt_block(), "")

    def test_a_401_or_403_gives_nothing_and_forgets_the_last_good_answer(self) -> None:
        for refusal in (401, 403):
            with self.subTest(refusal):
                brain._fallback.clear()
                self.server.answer(200)
                self.remember_a_good_answer()
                self.server.answer(refusal)
                self.assertEqual(self.provider("refused").system_prompt_block(), "")
                # A following timeout no longer finds anything to fall back on.
                self.server.answer(200, delay=1.0)
                self.assertEqual(self.provider("after").system_prompt_block(), "")

    def test_another_token_never_reads_the_last_good_answer(self) -> None:
        self.remember_a_good_answer()
        self.server.answer(503)
        with mock.patch.dict(os.environ, {"BRAIN_API_TOKEN": "another-test-token"}):
            self.assertEqual(self.provider("other").system_prompt_block(), "")

    def test_any_other_answer_gives_nothing(self) -> None:
        self.remember_a_good_answer()
        cases = {
            "404": (404, None),
            "not json": (200, b"<html>maintenance</html>"),
            "a list": (200, [briefing()]),
            "missing a field": (200, {k: v for k, v in briefing().items() if k != "knows_me"}),
            "a field of the wrong type": (200, briefing(persona_block=["x"])),
            "an empty zone": (200, briefing(zone="")),
            "too large": (200, briefing(profile_block="x" * 70_000)),
        }
        for label, (status, body) in cases.items():
            with self.subTest(label):
                self.server.answer(status, body)
                self.assertEqual(self.provider(label).system_prompt_block(), "")

    def test_a_redirect_is_not_followed(self) -> None:
        elsewhere = FakeBrain()
        self.addCleanup(elsewhere.close)
        self.server.answer(302)
        self.server.location = elsewhere.url + "/v1/me/briefing"
        self.assertEqual(self.provider().system_prompt_block(), "")
        self.assertEqual(elsewhere.requests, [])


class TimeLine(ProviderCase):
    def test_prefetch_is_the_time_line_in_the_briefing_zone(self) -> None:
        p = self.provider()
        p.system_prompt_block()
        self.assertEqual(p.prefetch(MESSAGE), TIME_LINE)
        self.assertEqual(len(self.server.requests), 1)

    def test_no_zone_known_yet_gives_nothing(self) -> None:
        self.assertEqual(self.provider().prefetch(MESSAGE), "")
        self.assertEqual(self.server.requests, [])

    def test_a_zone_zoneinfo_does_not_know_gives_nothing(self) -> None:
        self.server.answer(200, briefing(zone="Nowhere/At_All"))
        p = self.provider()
        self.assertEqual(p.system_prompt_block(), BOTH)
        self.assertEqual(p.prefetch(MESSAGE), "")

    def test_the_zone_outlives_a_session_switch_and_not_a_refusal(self) -> None:
        p = self.provider()
        p.system_prompt_block()
        p.on_session_switch("resumed")
        self.assertEqual(p.prefetch(MESSAGE), TIME_LINE)
        self.server.answer(403)
        p.system_prompt_block()
        self.assertEqual(p.prefetch(MESSAGE), "")


class NothingOfTheConversation(ProviderCase):
    """v0.1 sends nothing of a conversation (ADR-0052 §2, §6, §12)."""

    MESSAGE_HOOKS = (
        "sync_turn",
        "queue_prefetch",
        "on_session_end",
        "on_pre_compress",
        "on_memory_write",
        "on_delegation",
        "handle_tool_call",
    )

    def test_every_hook_that_receives_a_message_is_the_base_class_no_op(self) -> None:
        for hook in self.MESSAGE_HOOKS:
            self.assertTrue(hasattr(brain.MemoryProvider, hook), hook)
            self.assertNotIn(hook, vars(brain.BrainMemoryProvider), hook)

    def test_a_whole_session_makes_one_request_with_none_of_its_words(self) -> None:
        p = self.provider()
        messages = [{"role": "user", "content": MESSAGE}]
        p.on_turn_start(1, MESSAGE, platform="telegram")
        p.system_prompt_block()
        p.prefetch(MESSAGE, session_id="s1")
        p.queue_prefetch(MESSAGE, session_id="s1")
        p.sync_turn(MESSAGE, MESSAGE, session_id="s1", messages=messages)
        p.on_memory_write("add", "user", MESSAGE)
        p.on_delegation(MESSAGE, MESSAGE, child_session_id="c1")
        p.on_pre_compress(messages)
        p.on_session_end(messages)
        p.shutdown()
        (request,) = self.server.requests
        for word in ("back", "hurts", "own words"):
            self.assertNotIn(word, request.raw())


class NeverRaises(ProviderCase):
    def test_no_hook_raises_whatever_the_server_does(self) -> None:
        answers = [
            (200, None),
            (500, None),
            (200, b"\xff\xfe not utf-8"),
            (200, b"null"),
            (200, briefing(zone=None)),
        ]
        for status, body in answers:
            with self.subTest(status=status, body=body):
                self.server.answer(status, body)
                p = self.provider(f"{status}-{body!r}")
                p.on_turn_start(1, MESSAGE)
                p.system_prompt_block()
                p.prefetch(MESSAGE)
                p.on_session_switch("next")

    def test_no_hook_raises_on_input_hermes_should_not_send(self) -> None:
        p = brain.BrainMemoryProvider()
        p.initialize(None)  # type: ignore[arg-type]
        p.on_turn_start(None, None)  # type: ignore[arg-type]
        p.on_session_switch(None)  # type: ignore[arg-type]
        self.assertIsInstance(p.system_prompt_block(), str)
        self.assertIsInstance(p.prefetch(None), str)  # type: ignore[arg-type]

    def test_no_hook_raises_without_configuration(self) -> None:
        with mock.patch.dict(os.environ, {"BRAIN_API_URL": "", "BRAIN_API_TOKEN": ""}):
            p = self.provider()
            self.assertEqual(p.system_prompt_block(), "")
            self.assertEqual(p.prefetch(MESSAGE), "")
        self.assertEqual(self.server.requests, [])


class Logs(ProviderCase):
    def test_no_log_line_carries_a_block_the_token_or_the_url(self) -> None:
        secret_persona = "persona-words-that-must-not-be-logged"
        secret_profile = "profile-words-that-must-not-be-logged"
        root = logging.getLogger()
        with self.assertLogs(root, level=logging.DEBUG) as logs:
            self.server.answer(
                200, briefing(persona_block=secret_persona, profile_block=secret_profile)
            )
            self.provider("ok").system_prompt_block()
            for status in (401, 403, 404, 500):
                self.server.answer(status)
                self.provider(str(status)).system_prompt_block()
            self.server.answer(200, b"not json")
            self.provider("garbage").system_prompt_block()
            self.server.answer(200, delay=1.0)
            self.provider("slow").system_prompt_block()
        lines = "\n".join(logs.output)
        # The anchor: the plugin did log, so the absence below means something.
        self.assertIn("Brain briefing: HTTP 200", lines)
        self.assertIn("HTTP 403", lines)
        for forbidden in (secret_persona, secret_profile, TOKEN, self.server.url, ZONE):
            self.assertNotIn(forbidden, lines)


class ContractFields(unittest.TestCase):
    def test_the_fields_the_plugin_requires_are_the_contract_required_fields(self) -> None:
        from tests.support import contract_path

        schema = json.loads(contract_path().read_text("utf-8"))
        self.assertEqual(sorted(brain.REQUIRED_FIELDS), sorted(schema["required"]))
        kinds = {"string": str, "boolean": bool}
        for field, kind in brain.REQUIRED_FIELDS.items():
            self.assertIs(kinds[schema["properties"][field]["type"]], kind, field)


if __name__ == "__main__":
    unittest.main()
