---
name: test-generator
description: Generate comprehensive unit tests with proper structure, edge cases, and mocking
license: Apache-2.0
compatibility: claude-3
metadata:
  author: skills-mcp
  version: "1.0"
  category: testing
allowed-tools: Read Write Bash
---

# Test Generator Skill

Generate well-structured, comprehensive unit tests that ensure code reliability.

## Test Structure (AAA Pattern)

```python
def test_function_scenario_expected_result():
    # Arrange - Set up test data and conditions
    user = User(name="John", email="john@example.com")

    # Act - Execute the code being tested
    result = user.validate()

    # Assert - Verify the outcome
    assert result.is_valid is True
```

## Naming Convention

```
test_<function>_<scenario>_<expected_outcome>
```

Examples:
- `test_validate_email_with_valid_email_returns_true`
- `test_calculate_total_with_empty_cart_returns_zero`
- `test_authenticate_with_invalid_password_raises_error`

## Test Categories

### 1. Happy Path Tests
Test the normal, expected behavior.

```python
def test_add_numbers_with_positive_integers_returns_sum():
    result = add(2, 3)
    assert result == 5
```

### 2. Edge Cases
Test boundaries and limits.

```python
def test_divide_by_zero_raises_value_error():
    with pytest.raises(ValueError, match="Cannot divide by zero"):
        divide(10, 0)

def test_process_list_with_empty_list_returns_empty():
    result = process([])
    assert result == []

def test_truncate_string_at_max_length():
    result = truncate("hello world", max_length=5)
    assert result == "hello"
```

### 3. Error Handling
Test that errors are handled correctly.

```python
def test_fetch_user_with_invalid_id_raises_not_found():
    with pytest.raises(UserNotFoundError):
        fetch_user("invalid-id")

def test_parse_json_with_invalid_json_raises_parse_error():
    with pytest.raises(json.JSONDecodeError):
        parse_json("{invalid}")
```

### 4. State Changes
Test that state is modified correctly.

```python
def test_add_item_to_cart_increases_count():
    cart = Cart()
    cart.add_item(Product("Widget", 10.00))
    assert cart.item_count == 1
```

## Mocking Best Practices

### Mock External Dependencies

```python
from unittest.mock import Mock, patch

def test_send_email_calls_smtp_service():
    mock_smtp = Mock()

    with patch('myapp.email.smtp_client', mock_smtp):
        send_email("test@example.com", "Hello")

    mock_smtp.send.assert_called_once()

def test_fetch_data_handles_api_timeout():
    with patch('requests.get') as mock_get:
        mock_get.side_effect = requests.Timeout()

        result = fetch_data("https://api.example.com")

        assert result is None
```

### Mock Return Values

```python
def test_get_user_returns_user_from_database():
    mock_db = Mock()
    mock_db.find_one.return_value = {"id": "123", "name": "John"}

    user = get_user("123", db=mock_db)

    assert user.name == "John"
```

## Fixtures (pytest)

```python
import pytest

@pytest.fixture
def sample_user():
    return User(
        id="123",
        name="Test User",
        email="test@example.com"
    )

@pytest.fixture
def mock_database():
    with patch('myapp.db.connection') as mock:
        yield mock

def test_save_user(sample_user, mock_database):
    save_user(sample_user)
    mock_database.insert.assert_called_once()
```

## Parametrized Tests

```python
import pytest

@pytest.mark.parametrize("input,expected", [
    ("hello", "HELLO"),
    ("World", "WORLD"),
    ("", ""),
    ("123", "123"),
])
def test_uppercase_returns_uppercased_string(input, expected):
    assert uppercase(input) == expected

@pytest.mark.parametrize("a,b,expected", [
    (1, 2, 3),
    (0, 0, 0),
    (-1, 1, 0),
    (100, 200, 300),
])
def test_add_returns_correct_sum(a, b, expected):
    assert add(a, b) == expected
```

## Test Coverage Targets

| Type | Coverage |
|------|----------|
| Unit Tests | 80%+ line coverage |
| Critical Paths | 100% coverage |
| Edge Cases | All documented edge cases |
| Error Handlers | All catch blocks |

## Common Testing Patterns

### Testing Exceptions
```python
def test_invalid_input_raises_validation_error():
    with pytest.raises(ValidationError) as exc_info:
        validate({"bad": "data"})

    assert "required field missing" in str(exc_info.value)
```

### Testing Async Code
```python
import pytest

@pytest.mark.asyncio
async def test_async_fetch_returns_data():
    result = await fetch_async("https://api.example.com")
    assert result is not None
```

### Testing Classes
```python
class TestUserService:
    def setup_method(self):
        self.service = UserService()

    def test_create_user_returns_user(self):
        user = self.service.create("test@example.com")
        assert user.email == "test@example.com"

    def test_delete_user_removes_user(self):
        self.service.create("test@example.com")
        self.service.delete("test@example.com")
        assert self.service.find("test@example.com") is None
```

## Anti-Patterns to Avoid

1. **Testing implementation, not behavior**: Test what it does, not how
2. **Too many assertions**: One concept per test
3. **Test interdependence**: Tests should run in any order
4. **Brittle tests**: Don't assert on exact strings when structure matters
5. **No error testing**: Always test failure cases
6. **Slow tests**: Mock external services
