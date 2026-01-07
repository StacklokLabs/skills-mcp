"""Tests for TokenEstimator service."""

from skills_mcp.domain.services.token_estimator import TokenEstimator, estimate_tokens


class TestTokenEstimator:
    """Tests for TokenEstimator class."""

    def test_estimate_empty_string(self) -> None:
        """Empty string should return 0 tokens."""
        estimator = TokenEstimator()
        assert estimator.estimate("") == 0

    def test_estimate_short_text(self) -> None:
        """Short text should return at least 1 token."""
        estimator = TokenEstimator()
        result = estimator.estimate("hello")
        assert result >= 1

    def test_estimate_longer_text(self) -> None:
        """Longer text should return more tokens than short text."""
        estimator = TokenEstimator()
        short_result = estimator.estimate("hello")
        long_result = estimator.estimate("hello world this is a longer text")
        assert long_result > short_result

    def test_estimate_proportional_to_length(self) -> None:
        """Token count should be roughly proportional to text length."""
        estimator = TokenEstimator()
        text1 = "a" * 100
        text2 = "a" * 200
        tokens1 = estimator.estimate(text1)
        tokens2 = estimator.estimate(text2)
        # tokens2 should be roughly double tokens1 (with some tolerance)
        assert tokens2 > tokens1
        assert tokens2 < tokens1 * 3  # Allow for some variance

    def test_is_accurate_property(self) -> None:
        """is_accurate should indicate if tiktoken is available."""
        estimator = TokenEstimator()
        # The property should return a boolean
        assert isinstance(estimator.is_accurate, bool)

    def test_estimate_file_utf8(self) -> None:
        """estimate_file should handle UTF-8 content."""
        estimator = TokenEstimator()
        content = b"Hello, world!"
        result = estimator.estimate_file(content)
        assert result >= 1

    def test_estimate_file_binary(self) -> None:
        """estimate_file should handle binary content."""
        estimator = TokenEstimator()
        # Binary content that's not valid UTF-8
        content = bytes([0xFF, 0xFE, 0x00, 0x01])
        result = estimator.estimate_file(content)
        assert result >= 1

    def test_estimate_file_empty(self) -> None:
        """estimate_file should handle empty content."""
        estimator = TokenEstimator()
        result = estimator.estimate_file(b"")
        assert result == 0


class TestEstimateTokensFunction:
    """Tests for convenience estimate_tokens function."""

    def test_estimate_tokens_empty(self) -> None:
        """estimate_tokens should handle empty string."""
        assert estimate_tokens("") == 0

    def test_estimate_tokens_simple(self) -> None:
        """estimate_tokens should work for simple text."""
        result = estimate_tokens("Hello, world!")
        assert result >= 1

    def test_estimate_tokens_consistent(self) -> None:
        """estimate_tokens should return consistent results."""
        text = "The quick brown fox jumps over the lazy dog."
        result1 = estimate_tokens(text)
        result2 = estimate_tokens(text)
        assert result1 == result2
