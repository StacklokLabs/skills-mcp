# Contributing

Thank you for your interest in contributing to Skills MCP Server!

## Getting Started

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/skills-mcp.git
   cd skills-mcp
   ```
3. Install dependencies:
   ```bash
   uv sync --all-extras
   ```
4. Create a branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Workflow

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src/skills_mcp

# Run specific test file
uv run pytest tests/unit/domain/test_skill_validator.py
```

### Code Quality

```bash
# Format code
uv run ruff format .

# Lint code
uv run ruff check .

# Fix auto-fixable issues
uv run ruff check --fix .

# Type check
uv run mypy src/
```

### Documentation

```bash
# Serve docs locally
uv run mkdocs serve

# Build docs
uv run mkdocs build
```

## Pull Request Process

1. Ensure all tests pass
2. Update documentation if needed
3. Add tests for new functionality
4. Follow the code style guidelines
5. Write a clear PR description

## Commit Messages

Use conventional commits format:

```
type(scope): description

[optional body]

[optional footer]
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Code style (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding tests
- `chore`: Maintenance tasks

Examples:
```
feat(domain): add skill validation for name format
fix(mcp): handle timeout in skill discovery
docs: update installation instructions
```

## Code Review

All submissions require review. We use GitHub pull requests for this purpose.

## Questions?

- Open an issue for bugs or feature requests
- Start a discussion for questions or ideas
