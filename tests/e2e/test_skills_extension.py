"""Real Streamable HTTP tests for the accepted SEP-2640 snapshot."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from mcp.types import Request, RequestParams, Result

from skills_mcp.infrastructure.mcp.skills_extension import (
    SkillsGetParams,
    SkillsGetResult,
    SkillsListParams,
    SkillsListResult,
)


if TYPE_CHECKING:
    from .conftest import ServerInfo


EXTENSION = "io.modelcontextprotocol/skills"


class _NullUriParams(RequestParams):
    uri: None = None


class _WrongUriParams(RequestParams):
    uri: int = 7


class _WrongCursorParams(RequestParams):
    cursor: int = 7


class _ExtraListParams(RequestParams):
    unexpected: str = "forbidden"


class _ExtraGetParams(RequestParams):
    uri: str = "skill://valid-skill/SKILL.md"
    unexpected: str = "forbidden"


@pytest.mark.e2e
async def test_skills_extension_lists_gets_and_reads_exact_snapshot(
    e2e_server: ServerInfo,
) -> None:
    """Extension discovery exposes complete, byte-faithful static snapshots."""
    async with streamable_http_client(e2e_server.mcp_url) as (  # noqa: SIM117
        read,
        write,
    ):
        async with ClientSession(read, write, extensions={EXTENSION: {}}) as session:
            discovered = await session.discover()
            assert discovered.capabilities.extensions == {EXTENSION: {}}
            assert discovered.capabilities.experimental is None

            listed = await session.send_request(
                Request(method="skills/list", params=SkillsListParams()),
                SkillsListResult,
            )
            duplicates = [
                skill for skill in listed.skills if skill.name == "duplicate-skill"
            ]
            expected_duplicates = {
                "skill://group-one/duplicate-skill/SKILL.md": (
                    "First duplicate-name fixture",
                    "First.",
                ),
                "skill://group-two/duplicate-skill/SKILL.md": (
                    "Second duplicate-name fixture",
                    "Second.",
                ),
            }
            assert {skill.uri for skill in duplicates} == set(expected_duplicates)
            for duplicate in duplicates:
                expected_description, expected_body = expected_duplicates[duplicate.uri]
                assert duplicate.description == expected_description
                duplicate_get = await session.send_request(
                    Request(
                        method="skills/get",
                        params=SkillsGetParams(uri=duplicate.uri),
                    ),
                    SkillsGetResult,
                )
                assert duplicate_get.uri == duplicate.uri
                assert duplicate_get.description == expected_description
                duplicate_read = await session.read_resource(duplicate.uri)
                assert hasattr(duplicate_read.contents[0], "text")
                assert expected_body in duplicate_read.contents[0].text
            item = next(skill for skill in listed.skills if skill.name == "valid-skill")
            assert item.uri == "skill://valid-skill/SKILL.md"
            assert item.resources == "static"

            got = await session.send_request(
                Request(method="skills/get", params=SkillsGetParams(uri=item.uri)),
                SkillsGetResult,
            )
            assert got.frontmatter["allowed-tools"] == "Read Write Bash"
            assert got.frontmatter["metadata"] == {
                "author": "test-author",
                "version": "1.0",
                "nested": {"enabled": True, "levels": [1, 2]},
            }
            assert got.frontmatter["x-test-field"] == {"preserve": ["alpha", 7]}

            paths = {
                resource.uri.removeprefix("skill://valid-skill/")
                for resource in got.resources
            }
            assert paths == {
                "SKILL.md",
                ".extension-hidden",
                "assets/config.json",
                "custom/deep/note.txt",
                "references/GUIDE.md",
                "scripts/analyze.py",
            }

            fixture_root = Path(__file__).parents[1] / "fixtures/skills/valid-skill"
            for resource in got.resources:
                result = await session.read_resource(resource.uri)
                assert len(result.contents) == 1
                content = result.contents[0]
                relative = resource.uri.removeprefix("skill://valid-skill/")
                expected = (fixture_root / relative).read_bytes()
                if hasattr(content, "text"):
                    raw = content.text.encode("utf-8")
                    assert raw == expected
                    assert "tokens:" not in content.text
                else:
                    raw = base64.b64decode(content.blob)
                    assert raw == expected
                assert len(raw) == resource.size
                assert resource.digest == f"sha256:{hashlib.sha256(raw).hexdigest()}"

            # Canonical direct reads do not require list/get first; use a fresh URI.
            binary = await session.read_resource("skill://binary-skill/assets/logo.png")
            assert len(binary.contents) == 1
            assert hasattr(binary.contents[0], "blob")
            assert binary.contents[0].mime_type == "application/octet-stream"
            expected_binary = (
                Path(__file__).parents[1]
                / "fixtures/skills/binary-skill/assets/logo.png"
            ).read_bytes()
            assert base64.b64decode(binary.contents[0].blob) == expected_binary


@pytest.mark.e2e
async def test_skills_extension_rejects_adversarial_requests(
    e2e_server: ServerInfo,
) -> None:
    """Malformed params, cursors, URIs, and deferred methods fail explicitly."""
    async with streamable_http_client(e2e_server.mcp_url) as (  # noqa: SIM117
        read,
        write,
    ):
        async with ClientSession(read, write, extensions={EXTENSION: {}}) as session:
            await session.discover()
            with pytest.raises(MCPError) as malformed:
                await session.send_request(
                    Request(method="skills/get", params=RequestParams()), Result
                )
            assert malformed.value.code == -32602

            for params in (_NullUriParams(), _WrongUriParams()):
                with pytest.raises(MCPError) as malformed_uri:
                    await session.send_request(
                        Request(method="skills/get", params=params), Result
                    )
                assert malformed_uri.value.code == -32602

            with pytest.raises(MCPError) as wrong_cursor:
                await session.send_request(
                    Request(method="skills/list", params=_WrongCursorParams()), Result
                )
            assert wrong_cursor.value.code == -32602

            for method, params in (
                ("skills/list", _ExtraListParams()),
                ("skills/get", _ExtraGetParams()),
            ):
                with pytest.raises(MCPError) as forbidden_extra:
                    await session.send_request(
                        Request(method=method, params=params), Result
                    )
                assert forbidden_extra.value.code == -32602
                assert (await session.list_resources()).resources

            with pytest.raises(MCPError) as cursor:
                await session.send_request(
                    Request(
                        method="skills/list", params=SkillsListParams(cursor="unknown")
                    ),
                    SkillsListResult,
                )
            assert cursor.value.code == -32602

            for uri in (
                "skill://valid-skill/scripts/analyze.py",
                "skill://unknown/SKILL.md",
                "skills://valid-skill",
            ):
                with pytest.raises(MCPError) as invalid:
                    await session.send_request(
                        Request(method="skills/get", params=SkillsGetParams(uri=uri)),
                        SkillsGetResult,
                    )
                assert invalid.value.code == -32602

            for uri in (
                "skill://valid-skill/../SKILL.md",
                "skill://valid-skill/%2e%2e/SKILL.md",
                "skill://valid-skill%2F..%2Fbinary-skill/SKILL.md",
                "skill://user@valid-skill/SKILL.md",
            ):
                with pytest.raises(MCPError) as traversal:
                    await session.read_resource(uri)
                assert traversal.value.code == -32602

            with pytest.raises(MCPError) as deferred:
                await session.send_request(
                    Request(method="resources/directory/read", params=RequestParams()),
                    Result,
                )
            assert deferred.value.code == -32601

            # Validation errors are request-local and do not poison the session.
            usable = await session.list_resources()
            assert usable.resources


@pytest.mark.e2e
async def test_legacy_client_does_not_receive_unnegotiated_extension_capability(
    e2e_server: ServerInfo,
) -> None:
    """A legacy handshake has no hidden extension advertisement."""
    async with streamable_http_client(e2e_server.mcp_url) as (  # noqa: SIM117
        read,
        write,
    ):
        async with ClientSession(read, write) as session:
            initialized = await session.initialize()
            assert initialized.capabilities.extensions is None
            assert initialized.capabilities.experimental == {}
            before = await session.list_resources()
            direct = await session.read_resource("skill://binary-skill/assets/logo.png")
            assert hasattr(direct.contents[0], "blob")
            after = await session.list_resources()
            assert [resource.uri for resource in after.resources] == [
                resource.uri for resource in before.resources
            ]
