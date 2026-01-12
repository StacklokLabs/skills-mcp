---
name: git-commit
description: Write clear, conventional commit messages that communicate changes effectively
license: Apache-2.0
compatibility: claude-3
metadata:
  author: skills-mcp
  version: "1.0"
  category: development
allowed-tools: Bash Read
---

# Git Commit Message Skill

Write commit messages that are clear, consistent, and useful for understanding project history.

## Conventional Commits Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

| Type | Description |
|------|-------------|
| `feat` | New feature for users |
| `fix` | Bug fix for users |
| `docs` | Documentation changes |
| `style` | Formatting, missing semicolons, etc. |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `perf` | Performance improvement |
| `test` | Adding or updating tests |
| `build` | Changes to build system or dependencies |
| `ci` | CI configuration changes |
| `chore` | Other changes that don't modify src or test files |
| `revert` | Reverts a previous commit |

### Scope

Optional. Describes the section of codebase affected:
- `auth`, `api`, `db`, `ui`, `config`, etc.

### Subject Line Rules

1. Use imperative mood: "add feature" not "added feature"
2. Don't capitalize first letter
3. No period at the end
4. Max 50 characters (72 absolute max)
5. Complete the sentence: "If applied, this commit will..."

### Body Guidelines

- Wrap at 72 characters
- Explain **what** and **why**, not **how**
- Use bullet points for multiple changes
- Reference issues when relevant

### Footer

- `BREAKING CHANGE: <description>` for breaking changes
- `Fixes #123` or `Closes #456` for issue references
- `Co-authored-by: Name <email>` for pair programming

## Examples

### Simple Feature
```
feat(auth): add password reset functionality
```

### Bug Fix with Body
```
fix(api): handle null response from payment provider

The payment API sometimes returns null instead of an error object
when the service is degraded. This caused unhandled exceptions
in production.

Fixes #892
```

### Breaking Change
```
feat(api)!: change authentication to use JWT tokens

Migrate from session-based auth to JWT tokens for better
scalability and stateless operation.

BREAKING CHANGE: All API clients must now include JWT token
in Authorization header instead of session cookie.
```

### Documentation
```
docs: update API reference with rate limiting info
```

### Refactoring
```
refactor(db): extract query builder into separate module

No functional changes. Improves testability and
reduces coupling between repository and query logic.
```

## Anti-Patterns to Avoid

- "WIP" or "work in progress"
- "fix stuff" or "updates"
- "asdfasdf" or keyboard mashing
- Multiple unrelated changes in one commit
- Commit messages longer than the code change
- "Fixed PR comments"

## Git Commands Reference

```bash
# Stage specific files
git add <file1> <file2>

# Interactive staging
git add -p

# Commit with message
git commit -m "feat: add new feature"

# Commit with body (opens editor)
git commit

# Amend last commit
git commit --amend
```
