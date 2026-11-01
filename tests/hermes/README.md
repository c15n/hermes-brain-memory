# Hermes' base class, as tested

`memory_provider.py` is `agent/memory_provider.py` from
[NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) at tag
`v0.22.5` (Hermes v0.22.5, commit `bf0203a794a07aac3ff764972ab9087baa4e4f4e`),
byte for byte. `LICENSE` is that repository's licence, which covers the file.

The tests load the plugin against it, so the plugin runs on the real base class without
Hermes installed, and `test_hermes_contract.py` reads its hooks by AST. Its SHA-256 is
pinned in `tests/support.py`; an edit here is red.

To test against another Hermes version, replace the file with that tag's copy and update
`HERMES_TAG`, `HERMES_VERSION`, `HERMES_COMMIT` and `HERMES_BASE_SHA256` in
`tests/support.py`, and the version named in the README and the changelog.
