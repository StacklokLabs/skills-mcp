"""E2E tests for the MCP prompts API (list_prompts / get_prompt).

Exercises each fixture skill exposed as an MCP prompt over a real Streamable
HTTP transport, including the arguments marker, the typed resource listing,
session expansion, and the error paths that surface as ``MCPError``.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

import pytest
from mcp import ClientSession
from mcp.shared.exceptions import MCPError


# Type alias matches conftest.py
ClientFactory = Callable[[], AbstractAsyncContextManager[ClientSession]]


def _message_text(result: object) -> str:
    """Extract the first message's text from a GetPromptResult."""
    return result.messages[0].content.text  # type: ignore[attr-defined,no-any-return]


@pytest.mark.e2e
class TestListPromptsE2E:
    """prompts/list over the wire."""

    async def test_list_prompts_returns_prompt_per_fixture_skill(
        self, mcp_client_factory_shared: ClientFactory
    ) -> None:
        """Each fixture skill is exposed as a prompt with an optional args arg."""
        async with mcp_client_factory_shared() as client:
            result = await client.list_prompts()

            names = {p.name for p in result.prompts}
            assert "valid-skill" in names

            for prompt in result.prompts:
                assert prompt.arguments is not None
                assert any(
                    arg.name == "args" and arg.required is False
                    for arg in prompt.arguments
                )


@pytest.mark.e2e
class TestGetPromptE2E:
    """prompts/get over the wire."""

    async def test_get_prompt_valid_skill_returns_body_as_user_message(
        self, mcp_client_factory_shared: ClientFactory
    ) -> None:
        """get_prompt returns the SKILL.md body as a user message."""
        async with mcp_client_factory_shared() as client:
            result = await client.get_prompt("valid-skill")

            assert result.messages[0].role == "user"
            assert "Valid Skill" in _message_text(result)
            assert result.description == "A valid test skill with all features"

    async def test_get_prompt_with_args_appends_arguments_marker(
        self, mcp_client_factory_shared: ClientFactory
    ) -> None:
        """Non-empty args are appended as an ARGUMENTS marker."""
        async with mcp_client_factory_shared() as client:
            result = await client.get_prompt("valid-skill", {"args": "do the thing"})

            assert "ARGUMENTS: do the thing" in _message_text(result)

    async def test_get_prompt_valid_skill_lists_type_prefixed_resource_paths(
        self, mcp_client_factory_shared: ClientFactory
    ) -> None:
        """The prompt body lists type-prefixed resource paths for the skill."""
        async with mcp_client_factory_shared() as client:
            result = await client.get_prompt("valid-skill")
            text = _message_text(result)

            assert "- scripts/analyze.py" in text
            assert "- references/GUIDE.md" in text
            assert "- assets/config.json" in text
            assert "Use get_skill_resource" in text

    async def test_get_prompt_expands_skill_in_resource_listing(
        self, mcp_client_factory_shared: ClientFactory
    ) -> None:
        """Calling get_prompt expands the skill's sub-resources for the session."""
        async with mcp_client_factory_shared() as client:
            await client.get_prompt("valid-skill")

            resources = await client.list_resources()
            uris = {str(r.uri) for r in resources.resources}

            assert "skills://valid-skill/scripts/analyze.py" in uris

    async def test_get_prompt_unknown_skill_raises_mcp_error(
        self, mcp_client_factory_shared: ClientFactory
    ) -> None:
        """An unknown skill name surfaces as an MCPError at the protocol layer."""
        async with mcp_client_factory_shared() as client:
            with pytest.raises(MCPError):
                await client.get_prompt("no-such-skill")

    async def test_get_prompt_invalid_name_raises_mcp_error(
        self, mcp_client_factory_shared: ClientFactory
    ) -> None:
        """An invalid skill name surfaces as an MCPError at the protocol layer."""
        async with mcp_client_factory_shared() as client:
            with pytest.raises(MCPError):
                await client.get_prompt("NOT VALID!!")

    async def test_get_prompt_empty_arguments_dict_omits_arguments_marker(
        self, mcp_client_factory_shared: ClientFactory
    ) -> None:
        """An empty arguments dict must not add an ARGUMENTS marker."""
        async with mcp_client_factory_shared() as client:
            result = await client.get_prompt("valid-skill", {})

            assert "ARGUMENTS:" not in _message_text(result)
