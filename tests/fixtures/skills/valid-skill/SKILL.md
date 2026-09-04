---
name: valid-skill
description: A valid test skill with all features
license: MIT
compatibility: claude-3
metadata:
  author: test-author
  version: "1.0"
  nested:
    enabled: true
    levels: [1, 2]
allowed-tools: Read Write Bash
x-test-field:
  preserve: [alpha, 7]
---

# Valid Skill

This is a test skill with a complete set of features.

## Usage

Use this skill for testing the MCP server.

## Examples

```python
print("Hello from valid-skill")
```
