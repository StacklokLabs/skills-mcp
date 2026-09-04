# How agents discover served skills

Serving skills over MCP only matters if agents reach for them. Live trials with Claude Code (July 2026) started from a sobering baseline: on natural prompts like "write a commit message for this change", the agent never touched the server. Zero times out of six, even with the tools pre-approved and a perfectly matching skill one call away.

This page explains why that happened, what the server does about it, and how the approach scales. The operator-facing to-do list distilled from these findings is in [getting agents to use your skills](../guides/agent-uptake.md). The raw numbers are in the [findings appendix](#findings-appendix-claude-code-july-2026) below, clearly dated: re-run the trials if client behavior changes.

## Why agents ignored the server

Three causes stacked on top of each other:

1. **Tool descriptions are deferred.** Claude Code enables MCP tool search by default: at session start the model sees only tool *names* and the server *instructions*. Tool descriptions, including the skill catalog embedded in `list_skills`, stay out of context until the model decides to search for tools. For a task it thinks it can already do, it never searches, so it never learns the server is relevant.
2. **"Skills" is native client vocabulary.** Claude Code has its own built-in skills feature. A nudge like "check what skills are available to you" made the model inspect its *built-in* skill list and explicitly dismiss the MCP server as unrelated.
3. **The model thinks it already knows.** For commit messages, release notes, and similar tasks, the model has strong priors. Without a reason to believe the organization's version is different, it answers from memory.

## What the server does about it

Each mitigation targets one of those causes. All of them live in `src/skills_mcp/infrastructure/mcp/server.py`.

**Origin-aware instructions without an authority claim.** Server instructions identify operator-configured local, Git, or OCI origins and direct legacy clients to the discovery workflow, while explicitly requiring host policy, permissions, and user instructions to govern use. Skill content is untrusted input; the server does not call it vetted or authoritative and does not tell a model to follow it exactly.

**Explicit disambiguation from native skills.** The instructions and the `list_skills` description both state that these skills are separate from any built-in skills the client ships with. In trials, this flipped the "check what skills are available" prompt from a failure (routed to the native feature) to a full, correct skill run.

**`anthropic/alwaysLoad` on `list_skills`.** This meta flag keeps a neutral discovery hint in Claude Code's initial context. The description contains no skill names or descriptions because repository content is untrusted; the model must call `list_skills` to retrieve the catalog as data. This closes an always-loaded prompt-injection boundary, at the cost of no longer exposing per-skill trigger text before the first tool call.

**Catalog data is disclosed only by the tool result.** Names and descriptions remain available from `list_skills`, but never appear in the always-loaded tool description. For reliable uptake, explicitly steer the client to call `list_skills` or use an extension-aware client that discovers `skills/list`.

**"Use when" descriptions and read-only annotations.** Every tool description states when to call it and shows one example call. All four tools declare `readOnlyHint`/`idempotentHint` annotations, which clients use to relax permission handling and parallelize calls.

## How this scales: large catalogs

The always-loaded description is intentionally static and contains no repository-controlled names or descriptions. Large and small catalogs therefore have the same safe discovery path: the model calls `list_skills`, then selects from the returned untrusted catalog data.

What to do about it, in order of confidence:

- **Use CLAUDE.md steering per project.** Explicitly require the full-catalog call. Its reliability does not depend on catalog size.
- **Scope connections instead of growing the catalog.** A team rarely needs 100 skills at once; serving a filtered subset makes the returned catalog easier to select from.

Two directions serve different clients: a search-style legacy dispatch tool (`find_skill(task)`) remains unmeasured, while extension-aware clients can now negotiate the accepted SEP-2640 snapshot and preload `skills/list` descriptions without relying on the 2 KB tool-description preview. The extension path is implemented; actual uptake still depends on client support.

Until then, the honest positioning is: a drop-in replacement up to roughly a dozen skills per connection; beyond that, add per-project steering or scoping.

## Known limitations and open questions

- **A matching native skill preempts the server.** In one trial the model had a locally-installed skill covering the same domain as a served skill, and it used the native one without consulting the MCP catalog, even though the served skill was visible in the always-loaded description. The server wins when it is the only source for a domain; it loses ties to client-native skills. For a true drop-in deployment, avoid overlapping local skills rather than trying to outrank them.
- **Under-triggering is the failure mode, not over-triggering.** An unrelated prompt ("what's the capital of Australia?") produced zero skill lookups and answered in two seconds; the server adds no overhead to prompts it doesn't match.
- The trials covered Claude Code only. Cline, Roo Code, and Continue load tool descriptions differently and were not measured.
- MCP sampling (the server asking the client's model to run a completion, which would allow server-side skill matching) is not supported by Claude Code, so the design does not rely on it.
- The tool names (`list_skills`, `get_skill`) still share vocabulary with the native feature. The disambiguation wording proved sufficient in trials, so the spec-aligned names were kept; renaming remains an option if collisions reappear.
- A skill-informed run costs 45 to 60 seconds end to end in `claude -p` (catalog, skill load, resource fetches, self-validation), versus about 10 seconds for an answer from memory. That is the price of following the organization's conventions; trim skill workflows if it matters.

## Findings appendix (Claude Code, July 2026)

The numbers come from live `claude -p` trials against this server, run in July 2026 with tools pre-approved. Client behavior can change; re-run the trials before extending these conclusions.

| Condition (Claude Code, `claude -p`, tools pre-approved) | Before | After |
|---|---|---|
| Bare natural prompt ("write a commit message for...") | 0/6 | **3/3** |
| Bare natural prompt, different skill (release notes) | not tested | **1/1** |
| "Check what skills are available to you, then..." | 0/2 (routed to native skills) | **1/1** |
| Vague CLAUDE.md pointer ("team skills are available from...") | 0/2 | 0/2 |
| Explicit CLAUDE.md steering naming `list_skills` | 2/2 | not re-tested |

"Before" is the server without the mitigations above; "after" is with all of them in place. Success means the model called `list_skills`, loaded the matching skill with `get_skill`, fetched its bundled resources, and produced output that follows the skill's instructions, verified with a house rule the model would not produce on its own.
