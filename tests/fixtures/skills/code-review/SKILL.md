---
name: code-review
description: Systematic code review methodology for identifying issues, suggesting improvements, and ensuring code quality
license: Apache-2.0
compatibility: claude-3
metadata:
  author: skills-mcp
  version: "1.0"
  category: development
allowed-tools: Read Grep Glob
---

# Code Review Skill

Perform thorough, constructive code reviews that improve code quality and share knowledge.

## Review Process

### 1. Understand Context
- What problem does this code solve?
- What are the requirements or acceptance criteria?
- How does it fit into the larger system?

### 2. Review Checklist

#### Correctness
- [ ] Does the code do what it's supposed to do?
- [ ] Are edge cases handled?
- [ ] Are error conditions handled appropriately?
- [ ] Is the logic correct and complete?

#### Security
- [ ] No hardcoded secrets or credentials
- [ ] Input validation on all external data
- [ ] Protection against injection attacks (SQL, XSS, command)
- [ ] Proper authentication/authorization checks
- [ ] Sensitive data properly protected

#### Performance
- [ ] No unnecessary database queries or API calls
- [ ] Efficient algorithms and data structures
- [ ] Appropriate caching strategies
- [ ] No memory leaks or resource exhaustion risks

#### Maintainability
- [ ] Clear, descriptive naming
- [ ] Functions are small and focused (single responsibility)
- [ ] No code duplication (DRY principle)
- [ ] Appropriate abstraction level
- [ ] Comments explain "why", not "what"

#### Testing
- [ ] Unit tests for new functionality
- [ ] Edge cases covered in tests
- [ ] Tests are readable and maintainable
- [ ] Mocks used appropriately

### 3. Feedback Guidelines

**Be Specific**: Point to exact lines and explain the issue clearly.

**Be Constructive**: Suggest solutions, not just problems.

**Prioritize**: Distinguish between blocking issues and nice-to-haves.

**Be Kind**: Review the code, not the person.

## Review Comment Templates

### Bug/Issue
```
🐛 **Bug**: [description]
Line X: [code snippet]
This will cause [problem] because [reason].
Suggested fix: [solution]
```

### Improvement
```
💡 **Suggestion**: [description]
Consider [alternative approach] because [benefit].
```

### Question
```
❓ **Question**: [what you're unsure about]
I'm not sure I understand [aspect]. Could you explain [specific question]?
```

### Praise
```
✨ **Nice**: [what you like]
This is a clean solution for [problem].
```

## Common Issues to Watch For

1. **Null/undefined handling**: Missing null checks
2. **Resource cleanup**: Unclosed connections, file handles
3. **Race conditions**: Concurrent access to shared state
4. **Error swallowing**: Empty catch blocks
5. **Magic numbers**: Unexplained literal values
6. **Deep nesting**: Complex conditional logic
7. **Large functions**: Functions doing too many things
8. **Inconsistent error handling**: Mix of exceptions and return codes
