#!/usr/bin/env python3
"""Template for generating pytest test files."""

TEMPLATE = '''"""Tests for {module_name}."""

import pytest
from unittest.mock import Mock, patch

from {module_path} import {class_or_function}


class Test{class_name}:
    """Tests for {class_or_function}."""

    def setup_method(self):
        """Set up test fixtures."""
        pass

    def test_{function}_with_valid_input_returns_expected(self):
        """Test happy path scenario."""
        # Arrange

        # Act
        result = {function}()

        # Assert
        assert result is not None

    def test_{function}_with_invalid_input_raises_error(self):
        """Test error handling."""
        # Arrange

        # Act & Assert
        with pytest.raises(ValueError):
            {function}(invalid_input)

    def test_{function}_with_edge_case_handles_correctly(self):
        """Test edge case."""
        # Arrange

        # Act
        result = {function}(edge_case_input)

        # Assert
        assert result == expected_edge_case_result


@pytest.fixture
def sample_data():
    """Provide sample test data."""
    return {{
        "key": "value",
    }}


@pytest.fixture
def mock_dependency():
    """Mock external dependency."""
    with patch("{module_path}.external_service") as mock:
        mock.return_value = "mocked_response"
        yield mock
'''


def generate_test_file(
    module_name: str,
    module_path: str,
    class_or_function: str,
) -> str:
    """Generate a test file from template."""
    return TEMPLATE.format(
        module_name=module_name,
        module_path=module_path,
        class_or_function=class_or_function,
        class_name=class_or_function.title().replace("_", ""),
        function=class_or_function.lower(),
    )


if __name__ == "__main__":
    # Example usage
    test_code = generate_test_file(
        module_name="user_service",
        module_path="myapp.services.user_service",
        class_or_function="UserService",
    )
    print(test_code)
