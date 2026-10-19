# MCP surface

The server speaks Streamable HTTP at `/mcp` and supports two interoperable client paths:

- **Extension-aware clients** use the accepted SEP-2640 snapshot: `skills/list`, `skills/get`, and byte-faithful `skill://` resources.
- **Legacy clients** keep the existing tools, prompts, and progressive `skills://` resources.

This is alignment with accepted SEP-2640 at PR head `d6b31a03504c15677d49b922b6b6ace0ef65728d`, not a claim of final conformance. The proposal and SDK may continue to evolve.

## SEP-2640 skills extension

The server advertises:

```json
{
  "capabilities": {
    "extensions": {
      "io.modelcontextprotocol/skills": {}
    }
  }
}
```

MCP SDK 2.1.1's `Extension`/`MethodBinding` mechanism registers and advertises extension methods but does not gate method dispatch on per-client advertisement. The server uses those bindings and modern `server/discover` capability negotiation; a legacy `initialize` handshake does not receive an unnegotiated extension capability. Because the SDK does not enforce method opt-in, the server does not invent an incompatible call gate. The former `capabilities.experimental` claim has been removed.

### `skills/list`

Returns one complete deterministic page of static skills. Each item has `uri`, `name`, `description`, and `resources: "static"`. Supplying any cursor is rejected with JSON-RPC `-32602` because there is no second page.

A name is display metadata, not identity. Canonical identity is the normalized source-relative skill path, so two skills may share a frontmatter name at different paths. Source precedence applies only when exact canonical paths collide. Name lookup remains first-match only on legacy surfaces.

### `skills/get`

Accepts only an exact canonical manifest URI:

```
skill://<source-relative-skill-path>/SKILL.md
```

Supporting-file URIs, malformed URIs, legacy `skills://` URIs, and unknown skills return `-32602`. The result includes the complete JSON-compatible frontmatter—including unknown keys, nested values, and the original `allowed-tools` spelling/value shape—and every static file as `{uri, digest, size}`.

Each static snapshot recursively includes every regular file, including hidden, nested, arbitrary-directory, binary, and `SKILL.md` files. Entries are sorted deterministically and carry exact captured bytes, byte sizes, and `sha256:<hex>` digests. A skill is omitted from SEP if its snapshot is incomplete or inconsistent, escapes through a symlink, exceeds 512 files or 16 MiB total, uses YAML aliases/anchors or non-JSON YAML, or has a frontmatter name that does not match its skill directory. Legacy Git name fallback and frontmatter-name-wins entries remain available only through legacy surfaces.

### Canonical resource reads

`resources/read` accepts every URI returned by `skills/get`, even before `skills/list` or `skills/get`. Reads return the exact stored bytes:

- valid UTF-8 is returned as text only when encoding it again reproduces the same bytes;
- all other content is returned as a base64 blob.

Canonical reads never add token headers and never mutate legacy expansion state.

`directoryRead` and `resources/directory/read` are deliberately deferred and are neither advertised nor registered. Static `skills/get` listings already describe the complete snapshot.

## Legacy tools

| Tool | Tier | Purpose |
|------|------|---------|
| `list_skills` | 1 | Catalog of names, descriptions, and legacy resource counts |
| `get_skill` | 2 | SKILL.md body and typed resource listing; expands the skill |
| `get_skill_resource` | 3 | Text resource addressed as `type/filename` |
| `validate_skill` | - | Opt-in filesystem validation within configured roots |

All tools are read-only, idempotent, and closed-world. `list_skills` retains `anthropic/alwaysLoad`, but its always-loaded description is static, neutral, and contains no untrusted skill metadata. Names and descriptions are returned only by the tool call.

## Legacy progressive resources

```
skills://{name}
skills://{name}/scripts/{file}
skills://{name}/references/{file}
skills://{name}/assets/{file}
```

Initial `resources/list` contains skill-level entries. Reading `skills://{name}` expands only that connection's listing and, on the legacy protocol, emits `resources/list_changed`; subsequent listings reveal scripts, references, and assets. Direct legacy reads still work without listing first. Legacy text resource reads retain token-count headers for compatibility.

Session identity comes from `mcp-session-id`. Requests without it are sessionless and cannot share expansion state. Under the SDK v2 modern protocol, change delivery would require `subscriptions/listen`; because this server does not implement that stream, modern discovery honestly reports `resources.listChanged: false`.

## Prompts

Each display name is exposed as an MCP prompt. `prompts/get` returns the body as a user message, appends optional `args`, and retains the legacy typed-resource summary.

## Trust and host policy

Server instructions identify local, Git, or OCI origin and treat skill content as untrusted input. Clients must apply host policy, permissions, user instructions, and normal safety checks. The server does not claim that content is vetted, authoritative, or must be followed exactly.
