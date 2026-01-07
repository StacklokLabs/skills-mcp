# Testing

This project uses pytest for testing with a focus on thorough domain layer coverage.

## Running Tests

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run with coverage report
uv run pytest --cov=src/skills_mcp --cov-report=html

# Run specific test file
uv run pytest tests/unit/domain/test_skill_validator.py

# Run tests matching a pattern
uv run pytest -k "test_validate"
```

## Test Organization

```
tests/
├── conftest.py              # Shared fixtures
├── unit/
│   ├── domain/              # Domain layer tests
│   │   ├── test_skill.py
│   │   └── test_skill_validator.py
│   └── application/         # Application layer tests
│       └── test_validate_skill.py
└── integration/
    └── infrastructure/      # Infrastructure tests
        └── test_mcp_tools.py
```

## Writing Tests

### Unit Tests

Test domain logic in isolation:

```python
import pytest
from skills_mcp.domain.models import SkillName

class TestSkillName:
    def test_valid_name(self) -> None:
        name = SkillName("my-skill")
        assert name.value == "my-skill"

    def test_invalid_name_uppercase(self) -> None:
        with pytest.raises(ValueError, match="Invalid skill name"):
            SkillName("My-Skill")

    def test_invalid_name_consecutive_hyphens(self) -> None:
        with pytest.raises(ValueError, match="Invalid skill name"):
            SkillName("my--skill")
```

### Async Tests

Use pytest-asyncio for async tests:

```python
import pytest
from skills_mcp.application.commands import ValidateSkillHandler

@pytest.mark.asyncio
async def test_validate_skill_success(
    mock_repository: MockSkillRepository,
) -> None:
    handler = ValidateSkillHandler(mock_repository)
    result = await handler.handle(ValidateSkillCommand(path=Path("./test-skill")))
    assert result.is_valid
```

### Fixtures

Define reusable fixtures in `conftest.py`:

```python
import pytest
from pathlib import Path

@pytest.fixture
def sample_skill_path(tmp_path: Path) -> Path:
    """Create a sample skill directory."""
    skill_dir = tmp_path / "sample-skill"
    skill_dir.mkdir()

    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text('''---
name: sample-skill
description: A sample skill for testing.
---

# Sample Skill

This is a test skill.
''')

    return skill_dir

@pytest.fixture
def mock_repository() -> MockSkillRepository:
    """Create a mock skill repository."""
    return MockSkillRepository()
```

### Integration Tests

Test MCP tools end-to-end:

```python
import pytest
from mcp.client import Client

@pytest.mark.asyncio
async def test_discover_skills_tool(mcp_server: TestServer) -> None:
    async with Client(mcp_server.url) as client:
        result = await client.call_tool("discover_skills", {"path": "/skills"})
        assert "skills" in result
```

## Naming Convention

Use descriptive test names:

```
test_<function>_<scenario>_<expected_outcome>
```

Examples:
- `test_validate_skill_missing_name_raises_validation_error`
- `test_discover_skills_empty_directory_returns_empty_list`
- `test_skill_name_with_hyphens_is_valid`

## Coverage Goals

- Domain layer: 90%+ coverage
- Application layer: 80%+ coverage
- Infrastructure layer: 70%+ coverage

## Mocking

Use unittest.mock or pytest-mock for mocking:

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_fetch_remote_skill(mock_http_client: AsyncMock) -> None:
    mock_http_client.get.return_value = MockResponse(status=200, text="...")

    fetcher = HttpSkillFetcher(mock_http_client)
    skill = await fetcher.fetch("https://example.com/skill")

    assert skill is not None
    mock_http_client.get.assert_called_once()
```
