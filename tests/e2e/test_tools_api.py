"""E2E tests for the MCP tools API (list_tools / call_tool).

Exercises the ``list_skills``, ``get_skill``, and ``get_skill_resource`` tools
over a real Streamable HTTP transport against the fixture skills, including the
adversarial argument paths (traversal, wrong types, unknown names/types).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path

import pytest
from mcp import ClientSession


# Type alias matches conftest.py
ClientFactory = Callable[[], AbstractAsyncContextManager[ClientSession]]

# Fixture skills root, used to compare resource content byte-for-byte.
FIXTURES = Path(__file__).parent.parent / "fixtures" / "skills"

EXPECTED_TOOL_NAMES = {
    "list_skills",
    "get_skill",
    "get_skill_resource",
    "validate_skill",
}
INSTRUCTIONS_KEYS = {"name", "description", "body", "token_count", "resources"}


def _text(result: object) -> str:
    """Extract the first text block from a CallToolResult."""
    return result.content[0].text  # type: ignore[attr-defined,no-any-return]


@pytest.mark.e2e
class TestListToolsE2E:
    """tools/list over the wire."""

    async def test_list_tools_exposes_all_four_tools(
        self, mcp_client_factory_shared: ClientFactory
    ) -> None:
        """All four skill tools should be advertised."""
        async with mcp_client_factory_shared() as client:
            result = await client.list_tools()

            assert {t.name for t in result.tools} == EXPECTED_TOOL_NAMES

    async def test_list_tools_always_loaded_description_is_static_and_untrusted(
        self, mcp_client_factory_shared: ClientFactory
    ) -> None:
        """Always-loaded text excludes fixture-controlled metadata."""
        async with mcp_client_factory_shared() as client:
            result = await client.list_tools()
            list_skills = next(t for t in result.tools if t.name == "list_skills")

            assert list_skills.description is not None
            assert "untrusted" in list_skills.description
            assert "valid-skill" not in list_skills.description


@pytest.mark.e2e
class TestCallToolListSkillsE2E:
    """list_skills tool call."""

    async def test_list_skills_call_returns_fixture_catalog_json(
        self, mcp_client_factory_shared: ClientFactory
    ) -> None:
        """list_skills should return the fixture catalog as JSON with counts."""
        async with mcp_client_factory_shared() as client:
            result = await client.call_tool("list_skills", {})

            data = json.loads(_text(result))
            names = {entry["name"] for entry in data}
            assert {"valid-skill", "minimal-skill", "git-commit"} <= names

            valid = next(e for e in data if e["name"] == "valid-skill")
            assert valid["resources"] == {
                "scripts": 1,
                "references": 1,
                "assets": 1,
            }


@pytest.mark.e2e
class TestCallToolGetSkillE2E:
    """get_skill tool call."""

    async def test_get_skill_call_returns_instructions_json_with_resource_names(
        self, mcp_client_factory_shared: ClientFactory
    ) -> None:
        """get_skill should return the instructions dict with resource names."""
        async with mcp_client_factory_shared() as client:
            result = await client.call_tool("get_skill", {"name": "valid-skill"})

            data = json.loads(_text(result))
            assert set(data.keys()) == INSTRUCTIONS_KEYS
            assert data["resources"]["scripts"][0]["name"] == "analyze.py"
            assert "Valid Skill" in data["body"]

    async def test_get_skill_response_lets_model_construct_resource_path(
        self, mcp_client_factory_shared: ClientFactory
    ) -> None:
        """A model can build a valid resource_path from get_skill output alone.

        Pins the cross-layer discoverability contract: the resource-type keys in
        the get_skill JSON are exactly the type prefixes get_skill_resource
        accepts, so ``f"scripts/{name}"`` round-trips to real content.
        """
        async with mcp_client_factory_shared() as client:
            skill = json.loads(
                _text(await client.call_tool("get_skill", {"name": "valid-skill"}))
            )
            script_name = skill["resources"]["scripts"][0]["name"]
            resource_path = f"scripts/{script_name}"

            result = await client.call_tool(
                "get_skill_resource",
                {"skill_name": "valid-skill", "resource_path": resource_path},
            )
            text = _text(result)

            assert not text.startswith("Error")
            expected = (FIXTURES / "valid-skill" / "scripts" / "analyze.py").read_text()
            assert text == expected

    async def test_get_skill_call_expands_skill_in_resource_listing(
        self, mcp_client_factory_shared: ClientFactory
    ) -> None:
        """Calling get_skill should expand its sub-resources for the session."""
        async with mcp_client_factory_shared() as client:
            await client.call_tool("get_skill", {"name": "valid-skill"})

            resources = await client.list_resources()
            uris = {str(r.uri) for r in resources.resources}

            assert "skills://valid-skill/scripts/analyze.py" in uris

    async def test_get_skill_unknown_skill_returns_error_text(
        self, mcp_client_factory_shared: ClientFactory
    ) -> None:
        """An unknown skill returns a graceful error; the session stays usable."""
        async with mcp_client_factory_shared() as client:
            result = await client.call_tool("get_skill", {"name": "no-such-skill"})
            assert _text(result) == "Error: skill not found: no-such-skill"

            # Session remains usable for a follow-up call.
            after = await client.call_tool("list_skills", {})
            assert json.loads(_text(after))

    async def test_get_skill_empty_args_returns_error_text(
        self, mcp_client_factory_shared: ClientFactory
    ) -> None:
        """Omitting the required name arg is rejected as an error result.

        The SDK validates arguments against inputSchema before dispatch, so the
        missing required ``name`` yields ``isError`` rather than reaching the
        tool body.
        """
        async with mcp_client_factory_shared() as client:
            result = await client.call_tool("get_skill", {})

            assert result.is_error is True
            assert _text(result)

    async def test_get_skill_wrong_arg_type_returns_graceful_error(
        self, mcp_client_factory_shared: ClientFactory
    ) -> None:
        """A non-string name is handled gracefully; the session survives.

        This is the adversarial "{"name": 123}" probe. The MCP SDK's input
        validation (jsonschema against inputSchema) rejects the non-string value
        before dispatch, so the request returns ``isError`` and never reaches
        ``_tool_get_skill``. NOTE: if that validation layer were bypassed,
        ``SkillName(123)`` raises an uncaught ``TypeError`` (documented as a
        finding in the corresponding unit tests) — the transport boundary is the
        only thing making this graceful.
        """
        async with mcp_client_factory_shared() as client:
            result = await client.call_tool("get_skill", {"name": 123})

            assert result.is_error is True
            assert _text(result)

            # Session survives the malformed request.
            after = await client.call_tool("list_skills", {})
            assert after.is_error is not True
            assert json.loads(_text(after))


@pytest.mark.e2e
class TestCallToolGetSkillResourceE2E:
    """get_skill_resource tool call — adversarial paths."""

    async def test_get_skill_resource_traversal_returns_error_text(
        self, mcp_client_factory_shared: ClientFactory
    ) -> None:
        """Path traversal is rejected with a graceful error string."""
        async with mcp_client_factory_shared() as client:
            result = await client.call_tool(
                "get_skill_resource",
                {
                    "skill_name": "valid-skill",
                    "resource_path": "scripts/../../../etc/passwd",
                },
            )

            assert _text(result) == "Error: path traversal not allowed"

    async def test_get_skill_resource_pathless_format_returns_error_text(
        self, mcp_client_factory_shared: ClientFactory
    ) -> None:
        """A resource_path lacking a type prefix returns a format error."""
        async with mcp_client_factory_shared() as client:
            result = await client.call_tool(
                "get_skill_resource",
                {"skill_name": "valid-skill", "resource_path": "analyze.py"},
            )

            assert "must be in format 'type/filename'" in _text(result)

    async def test_get_skill_resource_unknown_type_returns_error_text(
        self, mcp_client_factory_shared: ClientFactory
    ) -> None:
        """An unrecognized resource type surfaces the loading-error prefix."""
        async with mcp_client_factory_shared() as client:
            result = await client.call_tool(
                "get_skill_resource",
                {"skill_name": "valid-skill", "resource_path": "wrong/analyze.py"},
            )

            assert _text(result).startswith("Error loading resource:")

    async def test_get_skill_resource_binary_asset_returns_error_text(
        self, mcp_client_factory_shared: ClientFactory
    ) -> None:
        """A binary asset returns the exact binary-not-text error."""
        async with mcp_client_factory_shared() as client:
            result = await client.call_tool(
                "get_skill_resource",
                {"skill_name": "binary-skill", "resource_path": "assets/logo.png"},
            )

            assert (
                _text(result)
                == "Error: resource is binary and cannot be returned as text"
            )


@pytest.mark.e2e
class TestCallToolUnknownE2E:
    """Unknown tool dispatch."""

    async def test_call_tool_unknown_name_returns_error(
        self, mcp_client_factory_shared: ClientFactory
    ) -> None:
        """An unknown tool name returns an error result; session survives."""
        async with mcp_client_factory_shared() as client:
            result = await client.call_tool("does-not-exist", {})
            assert result.is_error is True

            after = await client.call_tool("list_skills", {})
            assert after.is_error is not True
            assert json.loads(_text(after))
