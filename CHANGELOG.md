# Changelog

## 0.1.1 — 2026-11-01

- The profile only for an agent Hermes names `agent_context: primary`; an agent with no
  `agent_context` now gets the persona block alone, like a subagent.
- `BRAIN_API_URL` must be `https://`; plain `http://` only for `localhost` or
  `127.0.0.1`. Any other URL leaves the plugin unavailable, and no request is made.
- `plugin.yaml` declares `requires_hermes: ">=0.21.0"`.
- README: the MCP server's `Authorization` header as `Bearer ${BRAIN_API_TOKEN}`, so the
  token is kept in `.env` once rather than also in Hermes' `MCP_<NAME>_API_KEY`.
- Tested against Hermes v0.22.5 (tag `v0.22.5`).

## 0.1.0 — 2026-10-30

- First release. One briefing per Hermes session from `GET /v1/me/briefing`: the
  persona block and the profile block in the system prompt, the persona block alone
  for any `agent_context` other than `primary`, nothing on Hermes' API server.
- `prefetch()` returns the current local time, rendered from the briefing's time zone.
- After a network error, a timeout or a 5xx, the last good briefing for the same URL
  and token stands in for up to 15 minutes; a 401 or 403 forgets it.
- Sends nothing of a conversation. No tools.
- Tested against Hermes v0.21.0 (tag `v2026.8.31`).
