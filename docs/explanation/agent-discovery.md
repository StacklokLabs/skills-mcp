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

**Imperative instructions with an authority claim.** The server's MCP instructions (one of the only two things a tool-search client shows the model up front) are written as trigger text, not a capability statement. They name concrete trigger tasks (commit messages, release notes, changelogs, PR descriptions), and they borrow the wording that works for Context7's documentation server: check the catalog *even if you already know how to do the task*, because the organization's skill is authoritative and encodes conventions your defaults will miss.

**Explicit disambiguation from native skills.** The instructions and the `list_skills` description both state that these skills are separate from any built-in skills the client ships with. In trials, this flipped the "check what skills are available" prompt from a failure (routed to the native feature) to a full, correct skill run.

**`anthropic/alwaysLoad` on `list_skills`.** This meta flag is Claude Code's documented per-tool exemption from tool-search deferral. With it, the `list_skills` description, which carries the embedded catalog and the trigger text, is in context from the first turn. This was the decisive change: bare natural prompts went from 0/6 to 4/4, with the model calling `list_skills` directly (no tool search step) and then pulling `get_skill` and `get_skill_resource` on demand. Only the one discovery tool is always loaded; the rest stay deferred, which keeps the context cost near the price of the catalog itself.

**A byte-budgeted embedded catalog where every skill is at least named.** Clients truncate tool descriptions at around 2 KB, so the catalog is built against an explicit byte budget: up to 10 full name+description entries while they fit, then a names-only overflow line ("Also available: pdf, pptx, xlsx, ... (call list_skills for details)"), and only past that a bare count. The honest reading of the measurements: both a count-only marker and the names-only line were tested against prompts matching a past-cap skill, and *neither* drove discovery (0/2 each). The model answered from its own knowledge in seconds without paging the catalog; a bare name carries no domain cue. What reliably triggers a skill is a full entry, whose description says when to use it. The names line stays because it costs little and lets a model that *does* read the catalog (for example when the user asks what skills exist) see everything, but the practical rule is: **a skill only fires unprompted if it has a full entry in the always-loaded description**.

**"Use when" descriptions and read-only annotations.** Every tool description states when to call it and shows one example call. All four tools declare `readOnlyHint`/`idempotentHint` annotations, which clients use to relax permission handling and parallelize calls.

## How this scales: large catalogs

Unprompted discovery rides on a roughly 2 KB context window (the always-loaded `list_skills` description), which fits about ten described skills. That gives a large catalog three tiers of visibility:

1. **Full entries (about the first 10 skills).** Name plus trigger description in context from turn 1. These fire unprompted; this is the measured, working path.
2. **Names only (the next few dozen, budget permitting).** Present in an "Also available: pdf, pptx, ..." line. Measured result: a bare name never triggered discovery (0/2 on a task matching a named skill). These skills exist for a model that reads the catalog deliberately, but do not fire on their own.
3. **A bare count (everything past the byte budget).** Invisible until something else causes a `list_skills` call.

So with 100+ skills, expect roughly 90% of the catalog to be inert for unprompted use. Catalog order decides who gets tier 1, and today that order is simply source order (local sources first, then git, then OCI); there is no way yet to pin specific skills into the full entries.

What to do about it, in order of confidence:

- **Use CLAUDE.md steering per project.** At small catalog sizes the steering line is optional reinforcement; at large sizes it becomes the mechanism, because it forces the full-catalog call instead of relying on the embedded preview. It measured 2/2 and its reliability does not depend on catalog size. Different teams can name different trigger domains in their own projects.
- **Scope connections instead of growing the catalog.** A team rarely needs 100 skills at once; serving a filtered subset per team keeps each connection's catalog inside the budget honestly.
- **Curate the order.** Until priority pinning exists, arrange sources so the skills that matter most land in the first ten entries.

Two directions are plausible but unmeasured: a search-style dispatch tool (`find_skill(task)`) whose always-loaded description carries domain *keywords* instead of full entries (keywords are ~10 bytes each, so 100 domains fit where 100 descriptions cannot, but weak cues have already been seen to fail, so this needs trials before trusting it), and client-side support for the SEP-2640 skills extension, which would let clients preload served skill descriptions the way they preload local ones and remove the 2 KB constraint entirely.

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
