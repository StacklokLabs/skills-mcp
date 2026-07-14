---
name: binary-skill
description: A skill whose only resource is a binary asset for e2e binary-handling tests
---

# Binary Skill

This skill exists solely to exercise binary-asset handling in the tools API.
Its single asset (`assets/logo.png`) is a minimal PNG that cannot be decoded
as UTF-8 text, so `get_skill_resource` must report a graceful binary error.
