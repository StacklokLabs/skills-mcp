"""Token estimation service.

Provides token count estimation for text content using a hybrid approach:
- Uses tiktoken library when available for accurate counts
- Falls back to character-based approximation otherwise
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any


# Approximate characters per token for English text
_CHARS_PER_TOKEN = 4


@lru_cache(maxsize=1)
def _get_tiktoken_encoder() -> Any | None:
    """Get the tiktoken encoder, caching the result.

    Returns:
        The tiktoken encoder, or None if tiktoken is not available.
    """
    try:
        import tiktoken  # noqa: PLC0415

        return tiktoken.get_encoding("cl100k_base")
    except ImportError:
        return None


class TokenEstimator:
    """Service for estimating token counts in text.

    Uses a hybrid approach:
    - If tiktoken is installed, uses cl100k_base encoding for accurate counts
    - Otherwise, uses character approximation (~4 chars per token)

    The cl100k_base encoding is used by GPT-4 and similar models. While not
    exact for Claude's tokenizer, it provides a reasonable approximation.

    Example:
        estimator = TokenEstimator()
        count = estimator.estimate("Hello, world!")
        print(f"Estimated tokens: {count}")
    """

    def __init__(self) -> None:
        """Initialize the token estimator."""
        self._encoder = _get_tiktoken_encoder()

    @property
    def is_accurate(self) -> bool:
        """Return whether accurate token counting is available.

        Returns:
            True if tiktoken is available, False if using approximation.
        """
        return self._encoder is not None

    def estimate(self, text: str) -> int:
        """Estimate the token count for a piece of text.

        Args:
            text: The text to estimate tokens for.

        Returns:
            Estimated token count.
        """
        if not text:
            return 0

        if self._encoder is not None:
            # Use tiktoken for accurate counting
            tokens = self._encoder.encode(text)
            return len(tokens)

        # Fallback to character approximation
        return self._estimate_from_chars(text)

    def _estimate_from_chars(self, text: str) -> int:
        """Estimate tokens from character count.

        Args:
            text: The text to estimate.

        Returns:
            Estimated token count based on character length.
        """
        return max(1, len(text) // _CHARS_PER_TOKEN)

    def estimate_file(self, content: bytes, encoding: str = "utf-8") -> int:
        """Estimate token count for file content.

        Args:
            content: The file content as bytes.
            encoding: The text encoding to use.

        Returns:
            Estimated token count.
        """
        try:
            text = content.decode(encoding)
            return self.estimate(text)
        except UnicodeDecodeError:
            # For binary files, use byte count as rough approximation
            return max(1, len(content) // _CHARS_PER_TOKEN)


# Module-level convenience function
def estimate_tokens(text: str) -> int:
    """Estimate token count for text.

    This is a convenience function that creates a TokenEstimator
    instance and estimates the token count.

    Args:
        text: The text to estimate tokens for.

    Returns:
        Estimated token count.
    """
    estimator = TokenEstimator()
    return estimator.estimate(text)
