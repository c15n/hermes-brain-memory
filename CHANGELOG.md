# Changelog

## 0.1.0 — 2026-10-30

- First release. One briefing per Hermes session from `GET /v1/me/briefing`: the
  persona block and the profile block in the system prompt, the persona block alone
  for any `agent_context` other than `primary`, nothing on Hermes' API server.
- `prefetch()` returns the current local time, rendered from the briefing's time zone.
- After a network error, a timeout or a 5xx, the last good briefing for the same URL
  and token stands in for up to 15 minutes; a 401 or 403 forgets it.
- Sends nothing of a conversation. No tools.
- Tested against Hermes v0.21.0 (tag `v2026.8.31`).
