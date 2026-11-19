# Changelog

## 0.2.0 — 2026-11-19

- Renders the agent's own page when the briefing carries `agent_block` (ADR-0065 §9,
  ADR-0064 §7): identity, mandate and working notes, as the Brain quotes them. It comes
  first, before the persona block.
- Renders the About and Now of the contexts when the briefing carries `context_block`,
  after the profile block. Order: agent, persona, profile, contexts — joined by a blank
  line, never rewritten or cut; the Brain holds the budget.
- The profile and the contexts only for `agent_context: primary`; any other agent gets
  the agent block and the persona block.
- Both fields stay optional. Without them (an older Brain, a person's token) the block is
  as before; one that is empty or not a string is left out and the rest still used.
- Still one GET per session, nothing of a conversation sent.
- README: recommends switching Hermes' built-in memory off once its entries are moved to
  the Brain — both `memory_enabled` and `user_profile_enabled`, never the `memory`
  toolset, which would withhold the plugin's block too. Left on, the agent keeps two
  memories it cannot tell apart in the prompt. The Remove section says to turn both back
  on. No code change.

## 0.1.2 — 2026-11-02

- The time line comes back in a Hermes session that continues on a rebuilt agent
  (after Hermes evicted an idle agent, or after a restart). Hermes restores the stored
  prompt then and never asks for the session block, so the plugin did not know the time
  zone and `prefetch()` returned nothing until the next `/new`. `prefetch()` now fetches
  the briefing itself when it has no zone, at most once per session.
- The time line says that it is the authoritative current time, to be used instead of
  looking the time up with a tool. Hermes' own prompt tells some models to run `date`.

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
