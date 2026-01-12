#!/usr/bin/env python3
"""Example analysis script."""


def analyze(data: str) -> dict:
    """Analyze the given data."""
    return {
        "length": len(data),
        "words": len(data.split()),
    }


if __name__ == "__main__":
    result = analyze("Hello, world!")
    print(result)
