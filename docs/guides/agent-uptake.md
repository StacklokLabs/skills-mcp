# Getting agents to use your skills

Serving skills over MCP only matters if agents reach for them. Measured behavior in Claude Code (July 2026) shows that with the server's defaults, agents pick up served skills on natural prompts with no client-side configuration, but only for skills that land in the always-loaded part of the catalog. The evidence behind every rule on this page is in [how agents discover served skills](../explanation/agent-discovery.md).

## What to do

### 1. Write skill descriptions as triggers

The embedded catalog only works if each skill's description says *when to use it*, with the keywords a user's request would contain. This is the same rule the Agent Skills spec gives skill authors, and it is load-bearing here: the description is what an agent matches a task against.

### 2. Put the skills that matter in the first ten catalog slots

The always-loaded catalog fits roughly ten full name+description entries; skills past that appear as bare names or a count, and [measurement shows bare names never trigger unprompted use](../explanation/agent-discovery.md#how-this-scales-large-catalogs). Catalog order follows source order (local sources first, then git, then OCI), and within a source, discovery order. There is no priority-pinning mechanism yet, so arrange your sources so the most important skills come first.

### 3. Add an imperative CLAUDE.md line for large catalogs

At small catalog sizes a CLAUDE.md steering line is optional reinforcement. Past roughly a dozen skills it becomes the mechanism, because it forces a full-catalog call instead of relying on the embedded preview, and its reliability does not depend on catalog size.

A vague pointer ("team skills are available from the skills server") measurably does nothing. Make it imperative and name the tool:

> Before writing commit messages, release notes, or similar recurring artifacts, call the skill server's `list_skills` tool and follow the matching skill.

### 4. Scope connections instead of growing the catalog

A team rarely needs 100 skills at once. Serving a filtered subset per team keeps each connection's catalog inside the always-loaded budget honestly, instead of relying on skills the agent will never see.

### 5. Avoid overlapping client-native skills

When the client has a locally-installed skill covering the same domain as a served skill, the native one wins, even when the served skill is visible in context. The server wins when it is the only source for a domain. For a drop-in deployment, remove or avoid overlapping local skills rather than trying to outrank them.

### 6. Tell interactive users about slash commands

Each skill is also an MCP prompt, so interactive Claude Code exposes `/mcp__<server-name>__<skill-name>` slash commands for direct invocation. This path does not work in print mode (`claude -p` rejects MCP prompt commands). Continue exposes prompts as `/skill-name`.

## What you get by default

- **Claude Code needs nothing extra.** The `list_skills` tool carries the `anthropic/alwaysLoad` flag, so its description (with the embedded catalog and trigger text) is in context from the first turn. Natural prompts matching a fully-listed skill work with zero client-side configuration.
- **No overhead on unrelated prompts.** Under-triggering is the failure mode, not over-triggering: prompts that match no skill produce no skill lookups.
- **Other clients differ.** `anthropic/alwaysLoad` is a Claude Code extension; clients without tool search load all descriptions anyway, and the flag is inert for them. Only Claude Code has been measured; see the [findings](../explanation/agent-discovery.md#findings-appendix-claude-code-july-2026).

The exact tool contracts, annotations, and instructions text these behaviors ride on are documented in the [MCP surface reference](../reference/mcp-surface.md).
