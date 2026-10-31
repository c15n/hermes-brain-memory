# hermes-brain-memory

Published from a private monorepo; issues welcome here.

A memory provider for [Hermes](https://github.com/NousResearch/hermes-agent) that gives
every Hermes session one briefing from your Brain instance: who the assistant is for you
(persona and language), what Brain knows about you (your profile), the areas where Brain
remembers something — and, with every turn, the current local time.

Brain renders every word of the briefing. The plugin only joins the two blocks it gets
and writes one line itself, the time:

```
Current local time: Thursday 2026-10-29 14:05 (Europe/Berlin)
```

## Privacy

- **v0.1 sends no conversations.** The plugin's only request is
  `GET <BRAIN_API_URL>/v1/me/briefing`, once per Hermes session, with no query string and
  no body. No message, no reply and nothing Hermes remembers reaches Brain through this
  plugin. Its tests hold it to that.
- What Brain returns depends on the token's switch **"May know me (profile, persona,
  language)"**. Off, the briefing carries no profile, no persona notes and no name — only
  the default persona, the area hint and your time zone.
- The briefing goes into Hermes' system prompt, so it reaches your model provider (and
  any tracing you run) like the rest of the prompt.
- The plugin logs status codes and lengths only — never the token, the URL or a block.

## Requirements

- **Hermes v0.21.0** — tested against tag `v2026.8.31` (commit `29112bef0996`). Another
  version may change the provider interface; `tests/test_hermes_contract.py` reads it.
- Python 3.11 or later (Hermes' own requirement). Standard library only: the plugin
  installs no dependency into Hermes' environment.
- A Brain instance and a Brain API token — the same token Hermes already uses for Brain's
  MCP server.

## Install

Hermes installs from Git and pins by **commit**, not by tag: `--ref` takes a full
40-character commit SHA and nothing else. Find the commit of the release you want:

```sh
git ls-remote https://github.com/c15n/hermes-brain-memory 'refs/tags/v0.1.0*'
```

Use the line ending in `^{}` if there is one (an annotated tag), otherwise the only line.
(A browser URL with `/tree/v0.1.0/brain` does not pin either: Hermes keeps the folder
from it and drops the tag.) Then install the `brain/` folder of that commit:

```sh
hermes plugins install c15n/hermes-brain-memory/brain --ref <40-character commit SHA> --no-enable
```

- The plugin lands in **`$HERMES_HOME/plugins/brain/`**. The folder is named after
  `name:` in `brain/plugin.yaml`, and that name is what `memory.provider` refers to.
- `--no-enable` answers the installer's "Enable now?" prompt. A memory provider is not
  switched on through `plugins.enabled`; it is activated by `memory.provider` (below).
- Hermes scans the folder before it moves it into place. `brain/` holds two files,
  `__init__.py` and `plugin.yaml`.

## Configure

1. Put the URL and the token into the Hermes profile's `.env`:

   ```sh
   BRAIN_API_URL=https://brain.example.com
   BRAIN_API_TOKEN=<your Brain API token>
   ```

   `BRAIN_API_URL` is the Brain's base URL **without** `/v1`. Hermes loads the profile's
   `.env` into the environment, where the plugin reads both. Without either, the plugin
   reports itself unavailable and Hermes runs without it.

2. Activate it in the profile's `config.yaml`:

   ```yaml
   memory:
     provider: brain
   ```

3. Restart Hermes. A running chat keeps the prompt it started with; the briefing arrives
   in the next session (`/new` in Telegram).

Hermes' built-in memory (`MEMORY.md`, `USER.md`) keeps running; the plugin's block comes
in addition, in the rear part of the system prompt. The block is present while Hermes'
`memory` toolset is active.

## Update

There is no `hermes plugins update` for this plugin: it is installed pinned and from a
subfolder, and Hermes refuses to update either. Install the new release over the old one:

```sh
hermes plugins install c15n/hermes-brain-memory/brain --ref <40-character commit SHA> --force --no-enable
```

Then restart Hermes.

## Remove

Delete the `provider: brain` line from `config.yaml` and restart Hermes. Hermes returns to
its built-in memory alone, and Brain notices nothing. To remove the files too:

```sh
hermes plugins remove brain
```

## What it does, hook by hook

| Hook | Behaviour |
|---|---|
| `is_available()` | `True` when `BRAIN_API_URL` and `BRAIN_API_TOKEN` are set. No network. |
| `initialize()` | Remembers the session, `platform` and, when given, `agent_context`. No network. |
| `on_turn_start()` | Takes `platform` / `agent_context` when `initialize()` had none. The message is not read. |
| `system_prompt_block()` | Fetches the briefing once per session (timeout 3 s). The main agent gets the persona block, a blank line, the profile block; any other `agent_context` gets the persona block only. On Hermes' API server (`platform: api_server`) it returns nothing and makes no request. |
| `prefetch()` | The time line, rendered locally from the briefing's time zone. No request; the query is not used. |
| `get_tool_schemas()` | `[]` — no tools. |
| `recall_status()` | `None`. |
| `sync_turn()` and every other hook that receives messages | Hermes' default no-op. |

When the request fails:

| Answer | Result |
|---|---|
| network error, timeout or 5xx | the last good briefing for this URL and token, if it is at most 15 minutes old; otherwise nothing |
| 401 or 403 | nothing, and the last good briefing is forgotten |
| anything else (a redirect, a 404, a body that is not a briefing) | nothing |

No hook raises into Hermes. Fields the plugin does not know are ignored; a briefing
missing a required field is not used. The contract is the JSON Schema in
`contracts/v1/briefing.schema.json`.

## Development

```sh
python -m unittest discover -s tests -t .
```

Standard library only. `tests/hermes/memory_provider.py` is Hermes' base class at the
tested tag, unchanged, so the tests run against the real interface without Hermes
installed (see `tests/hermes/README.md`). `tests/fixtures/time-lines.json` holds the time
lines Brain's own rendering is tested against too.

## License

MIT — see `LICENSE`.
