# Enabling skill validation

The `validate_skill` tool validates a skill directory against the [Agent Skills specification](https://agentskills.io/specification). It is **disabled by default**: with no paths configured, the tool answers every call with a "validation is disabled" message.

## Enable it

Allow-list one or more directories the tool may inspect, either on the command line (repeatable, takes precedence) or in the config file:

```bash
skills-mcp --validation-path ./skills --validation-path /srv/skills
```

```yaml
server:
  validation_paths:
    - ./skills
    - /srv/skills
```

A path passed to `validate_skill` that resolves outside every allow-listed directory is refused.

When validation is enabled, the server logs a `WARNING` at startup listing the allowed paths, so the posture change is visible even at the default log level. A configured path that does not exist or is not a directory also logs a warning (the server keeps serving).

## Scope the allow-list narrowly

!!! warning "Scope the allow-list narrowly"
    `validate_skill` intentionally reports whether a path exists and whether it has a valid skill structure *within* the allow-listed roots, to any connected client. Point `validation_paths` at the directories that hold your skills, not at a broad or shared location such as `/`, `$HOME`, or a multi-tenant data directory, so this probing cannot be used to fingerprint unrelated files.
