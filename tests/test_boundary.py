"""The folder's boundary (ADR-0052 §6): `brain/` imports only the standard
library and Hermes' base class, and nothing here names a real host, a private
address or a token. The folder is published as it stands."""

from __future__ import annotations

import ast
import json
import re
import sys
import unittest
from pathlib import Path
from typing import Dict, List, Set, Tuple

from tests.support import PLUGIN, ROOT

# The one import that is not the standard library: the class Hermes asks for.
HERMES_IMPORTS = {"agent.memory_provider"}

# What the installed folder holds. Hermes' installer scans and copies all of it.
PLUGIN_FILES = {"__init__.py", "plugin.yaml"}

# Names under these are documentation placeholders or the public code host.
ALLOWED_HOSTS = re.compile(
    r"(^|\.)(example\.(com|org|net)|github\.com)$",
    re.IGNORECASE,
)

# A bare name under a common top-level domain (`.info` is left out: it is
# `logger.info` in every Python file), and the host of any URL, whatever its
# top-level domain.
HOST = re.compile(
    r"\b((?:[a-z0-9-]+\.)+(?:com|org|net|de|io|dev|app|ai|eu|cloud|co|me|so|xyz|tech|sh|link))\b",
    re.IGNORECASE,
)
URL_HOST = re.compile(r"\b[a-z][a-z0-9+.-]*://([^/\s:\"'<>`)]+)", re.IGNORECASE)
ALLOWED_URL_HOSTS = {"127.0.0.1", "localhost"}
# The one place a third host may stand: the JSON Schema dialect a contract
# declares, as the value of its top-level `$schema` in a file under
# `contracts/` (the mirror carries the briefing's schema there). The same URL
# anywhere else — another field, a .py file, a file outside `contracts/` — is
# a host like any other (owner, 2026-10-30).
# Joined, so this file does not name the host itself.
SCHEMA_DIALECT_HOST = "json-schema" + ".org"
SCHEMA_KEY = re.compile(r'"\$schema"\s*:\s*"([^"]*)"')

IPV4 = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")
ALLOWED_IPS = {"127.0.0.1", "0.0.0.0"}

SECRET_SHAPES = [
    re.compile(r"\bwsp_[A-Za-z0-9_-]{6,}"),  # the Brain's token scheme
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{20,}=*"),
    re.compile(r"\b(ghp|gho|ghs|github_pat)_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]


def stdlib() -> Set[str]:
    # Python 3.10 and later; the plugin's tests run on Hermes' 3.11.
    return set(sys.stdlib_module_names)


def imports(path: Path) -> List[str]:
    found: List[str] = []
    for node in ast.walk(ast.parse(path.read_text("utf-8"))):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                found.append("." * node.level + (node.module or ""))
            else:
                found.append(node.module or "")
    return found


def text_files() -> List[Path]:
    return [
        p
        for p in ROOT.rglob("*")
        if p.is_file()
        and "__pycache__" not in p.parts
        and p.suffix in {".py", ".md", ".yaml", ".yml", ".json", ".txt", ""}
    ]


def without_schema_dialect(rel: str, text: str) -> str:
    """The text with the contract's own `$schema` declaration taken out, when
    this is a JSON file under `contracts/` whose top-level `$schema` names the
    dialect host. Only that one occurrence: the rest is scanned as it is."""
    if not (rel.startswith("contracts/") and rel.endswith(".json")):
        return text
    try:
        doc = json.loads(text)
    except ValueError:
        return text
    declared = doc.get("$schema") if isinstance(doc, dict) else None
    if not isinstance(declared, str):
        return text
    hosts = URL_HOST.findall(declared)
    if hosts != [SCHEMA_DIALECT_HOST]:
        return text
    match = SCHEMA_KEY.search(text)
    if match is None or match.group(1) != declared:
        return text
    return text[: match.start()] + text[match.end() :]


def foreign_hosts(rel: str, text: str) -> List[str]:
    """Every host, URL host or IPv4 address in the text that is not a
    placeholder, the public code host or loopback."""
    text = without_schema_dialect(rel, text)
    found: List[str] = []
    for host in HOST.findall(text):
        if not ALLOWED_HOSTS.search(host):
            found.append(host)
    for host in URL_HOST.findall(text):
        if host not in ALLOWED_URL_HOSTS and not ALLOWED_HOSTS.search(host):
            found.append(host)
    for ip in IPV4.findall(text):
        if ip not in ALLOWED_IPS:
            found.append(ip)
    return found


class Boundary(unittest.TestCase):
    def test_brain_imports_only_the_standard_library_and_hermes_base(self) -> None:
        allowed = stdlib()
        found = imports(PLUGIN / "__init__.py")
        self.assertIn("urllib.request", found)  # the anchor: the walk sees imports
        for name in found:
            with self.subTest(name):
                self.assertTrue(
                    name in HERMES_IMPORTS or name.split(".")[0] in allowed,
                    f"{name} is neither the standard library nor Hermes' base class",
                )

    def test_the_plugin_folder_holds_only_its_two_files(self) -> None:
        present = {
            p.name for p in PLUGIN.iterdir() if p.name != "__pycache__"
        }
        self.assertEqual(present, PLUGIN_FILES)

    def test_no_real_host_or_private_address_anywhere_in_the_folder(self) -> None:
        files = text_files()
        self.assertGreater(len(files), 5)
        seen_placeholder = False
        for path in files:
            rel = path.relative_to(ROOT).as_posix()
            text = path.read_text("utf-8", errors="replace")
            seen_placeholder = seen_placeholder or any(
                "example" in host for host in HOST.findall(text) if ALLOWED_HOSTS.search(host)
            )
            self.assertEqual(foreign_hosts(rel, text), [], f"{rel} names a real host or address")
        # The anchor: the README's placeholders were read, so the scan reached it.
        self.assertTrue(seen_placeholder)

    def test_the_dialect_host_passes_only_as_a_contracts_schema_declaration(self) -> None:
        url = "https://" + SCHEMA_DIALECT_HOST + "/draft/2020-12/schema"
        contract = json.dumps({"$schema": url, "type": "object"}, indent=2)
        self.assertEqual(foreign_hosts("contracts/v1/x.schema.json", contract), [])
        # The negative control: the same URL anywhere else is a host.
        elsewhere: Dict[str, Tuple[str, str]] = {
            "in a .py file": ("brain/__init__.py", f'SCHEMA = "{url}"\n'),
            "in another JSON field": (
                "contracts/v1/x.schema.json",
                json.dumps({"$schema": url, "$id": url}, indent=2),
            ),
            "as $schema outside contracts/": (
                "tests/fixtures/x.json",
                contract,
            ),
            "as a nested $schema only": (
                "contracts/v1/x.schema.json",
                json.dumps({"properties": {"a": {"$schema": url}}}, indent=2),
            ),
            "another host as $schema": (
                "contracts/v1/x.schema.json",
                json.dumps({"$schema": "https://" + "brain.internal" + ".dev/schema"}, indent=2),
            ),
        }
        for label, (rel, text) in elsewhere.items():
            with self.subTest(label):
                self.assertNotEqual(foreign_hosts(rel, text), [], f"{label} passed")

    def test_no_token_shaped_string_anywhere_in_the_folder(self) -> None:
        files = text_files()
        self.assertGreater(len(files), 5)
        for path in files:
            text = path.read_text("utf-8", errors="replace")
            for shape in SECRET_SHAPES:
                match = shape.search(text)
                self.assertIsNone(
                    match, f"{path.relative_to(ROOT)}: {shape.pattern} matches"
                )

    def test_the_secret_shapes_would_see_one(self) -> None:
        # The patterns are not blind: each matches a made-up value of its shape.
        samples = [
            "wsp_" + "a1B2c3D4e5_" + "x" * 20,
            "Bearer " + "A" * 30,
            "ghp_" + "b" * 30,
            "sk-" + "c" * 30,
            "-----BEGIN OPENSSH " + "PRIVATE KEY-----",
        ]
        for shape, sample in zip(SECRET_SHAPES, samples):
            self.assertIsNotNone(shape.search(sample), shape.pattern)


if __name__ == "__main__":
    unittest.main()
