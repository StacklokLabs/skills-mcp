# Getting agents to use your skills

Serving skills over MCP only matters if agents reach for them. The always-loaded `list_skills` description is intentionally static: untrusted repository names and descriptions appear only in tool results. Explicit client or project steering should trigger catalog discovery.

## What to do

### 1. Write skill descriptions as selection cues

Once `list_skills` is called, each description should say *when to use the skill*, with keywords matching likely requests. Descriptions are returned as untrusted catalog data and are not embedded in an always-loaded prompt.

### 2. Add an imperative CLAUDE.md discovery line

Explicit steering makes the client call the catalog instead of relying on deferred tool discovery. This remains reliable regardless of catalog size.

A vague pointer ("team skills are available from the skills server") measurably does nothing. Make it imperative and name the tool:

> Before writing commit messages, release notes, or similar recurring artifacts, call the skill server's `list_skills` tool and follow the matching skill.

### 4. Scope connections instead of growing the catalog

A team rarely needs 100 skills at once. Serving a filtered subset per team keeps each connection's catalog inside the always-loaded budget honestly, instead of relying on skills the agent will never see.

### 5. Avoid overlapping client-native skills

When the client has a locally-installed skill covering the same domain as a served skill, the native one wins, even when the served skill is visible in context. The server wins when it is the only source for a domain. For a drop-in deployment, remove or avoid overlapping local skills rather than trying to outrank them.

### 6. Tell interactive users about slash commands

Each skill is also an MCP prompt, so interactive Claude Code exposes `/mcp__<server-name>__<skill-name>` slash commands for direct invocation. This path does not work in print mode (`claude -p` rejects MCP prompt commands). Continue exposes prompts as `/skill-name`.

## What you get by default

- **Claude Code gets a safe discovery hint.** The `list_skills` tool carries `anthropic/alwaysLoad`, but its description is static and labels returned content untrusted. Use explicit project steering when reliable automatic discovery matters.
- **No overhead on unrelated prompts.** Under-triggering is the failure mode, not over-triggering: prompts that match no skill produce no skill lookups.
- **Other clients differ.** `anthropic/alwaysLoad` is a Claude Code extension; clients without tool search load all descriptions anyway, and the flag is inert for them. Only Claude Code has been measured; see the [findings](../explanation/agent-discovery.md#findings-appendix-claude-code-july-2026).

The exact tool contracts, annotations, and instructions text these behaviors ride on are documented in the [MCP surface reference](../reference/mcp-surface.md).
