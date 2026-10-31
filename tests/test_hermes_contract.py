"""The plugin against Hermes' `agent/memory_provider.py` at the tested tag,
read by AST (ADR-0052 §10): every hook the plugin defines exists in the base
class with the same parameters, and every abstract method is implemented.

A Hermes whose interface moved breaks the plugin, not the Brain; this is where
that shows before the owner's Telegram does. Moving to another Hermes version
means replacing tests/hermes/memory_provider.py and the pins in support.py.
"""

from __future__ import annotations

import ast
import hashlib
import unittest
from typing import Dict, List, Tuple

from tests.support import HERMES_BASE, HERMES_BASE_SHA256, PLUGIN

Signature = Tuple[Tuple[str, ...], Tuple[str, ...], Tuple[str, ...], bool, bool]


def methods(path, class_name: str) -> Dict[str, ast.FunctionDef]:
    tree = ast.parse(path.read_text("utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                item.name: item
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
    raise AssertionError(f"no class {class_name} in {path}")


def signature(fn: ast.FunctionDef) -> Signature:
    a = fn.args
    return (
        tuple(p.arg for p in a.posonlyargs),
        tuple(p.arg for p in a.args),
        tuple(p.arg for p in a.kwonlyargs),
        a.vararg is not None,
        a.kwarg is not None,
    )


def is_abstract(fn: ast.FunctionDef) -> bool:
    return any(
        (isinstance(d, ast.Name) and d.id == "abstractmethod")
        or (isinstance(d, ast.Attribute) and d.attr == "abstractmethod")
        for d in fn.decorator_list
    )


BASE = methods(HERMES_BASE, "MemoryProvider")
PLUGIN_METHODS = methods(PLUGIN / "__init__.py", "BrainMemoryProvider")


class HermesContract(unittest.TestCase):
    def test_the_base_class_is_the_tested_tag_unchanged(self) -> None:
        digest = hashlib.sha256(HERMES_BASE.read_bytes()).hexdigest()
        self.assertEqual(digest, HERMES_BASE_SHA256)

    def test_every_hook_the_plugin_defines_is_hermes_with_its_parameters(self) -> None:
        hooks: List[str] = [n for n in PLUGIN_METHODS if not n.startswith("_")]
        # The anchor: the hooks ADR-0052 §5 relies on are among them.
        for needed in (
            "name",
            "is_available",
            "initialize",
            "system_prompt_block",
            "prefetch",
            "get_tool_schemas",
            "recall_status",
            "on_turn_start",
            "on_session_switch",
        ):
            self.assertIn(needed, hooks)
        for hook in hooks:
            with self.subTest(hook):
                self.assertIn(hook, BASE, f"Hermes has no hook {hook}")
                self.assertEqual(signature(PLUGIN_METHODS[hook]), signature(BASE[hook]))

    def test_every_abstract_method_is_implemented(self) -> None:
        abstract = [n for n, fn in BASE.items() if is_abstract(fn)]
        self.assertIn("get_tool_schemas", abstract)
        for name in abstract:
            self.assertIn(name, PLUGIN_METHODS, name)

    def test_initialize_documents_platform_and_agent_context(self) -> None:
        doc = ast.get_docstring(BASE["initialize"]) or ""
        for kwarg in ("platform", "hermes_home", "agent_context"):
            self.assertIn(kwarg, doc)
        self.assertIn('"primary"', doc)


if __name__ == "__main__":
    unittest.main()
