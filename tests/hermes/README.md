# Hermes' base class, as tested

`memory_provider.py` is `agent/memory_provider.py` from
[NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) at tag
`v2026.8.31` (Hermes v0.21.0, commit `29112bef099274229cadff79cdff7bf7b99c4b77`),
byte for byte. `LICENSE` is that repository's licence, which covers the file.

The tests load the plugin against it, so the plugin runs on the real base class without
Hermes installed, and `test_hermes_contract.py` reads its hooks by AST. Its SHA-256 is
pinned in `tests/support.py`; an edit here is red.

To test against another Hermes version, replace the file with that tag's copy and update
`HERMES_TAG`, `HERMES_VERSION`, `HERMES_COMMIT` and `HERMES_BASE_SHA256` in
`tests/support.py`, and the version named in the README and the changelog.
