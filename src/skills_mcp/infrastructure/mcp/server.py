"""MCP server implementation using Streamable HTTP transport.

Provides the main MCP server that exposes skills as resources
with progressive disclosure.
"""

from __future__ import annotations

import base64
import contextvars
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp.server import Server
from mcp.server.lowlevel import NotificationOptions
from mcp.server.streamable_http import StreamableHTTPServerTransport
from mcp.types import (
    BlobResourceContents,
    Resource,
    TextContent,
    TextResourceContents,
    Tool,
)
from pydantic import AnyUrl

from skills_mcp.domain.models.skill_name import SkillName
from skills_mcp.domain.services.manifest_parser import ManifestParser
from skills_mcp.domain.services.token_estimator import estimate_tokens
from skills_mcp.infrastructure.mcp.session import SessionManager


# Context variable for request-scoped session ID (thread-safe)
_current_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_session_id", default=None
)


if TYPE_CHECKING:
    from skills_mcp.domain.repositories import SkillRepository


logger = logging.getLogger(__name__)


# URI scheme for skills
SKILL_URI_SCHEME = "skills"

# URI path structure: skills://{name}/{type}/{file} has 3 parts
URI_RESOURCE_PARTS_COUNT = 3

# Default HTTP settings
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080


class SkillsMCPServer:
    """MCP server that exposes Agent Skills with progressive disclosure.

    The server exposes skills as resources with a three-tier disclosure model:
    1. Metadata tier: Only skill names and descriptions initially visible
    2. Instructions tier: Full SKILL.md body when skill is accessed
    3. Resources tier: Scripts, references, assets exposed after skill read

    Each MCP connection has isolated session state tracking which skills
    have been "expanded" (had their sub-resources revealed).

    Uses Streamable HTTP transport for communication.

    Example:
        repo = create_local_repository([Path("/skills")])
        server = SkillsMCPServer(repo)
        await server.run_http("127.0.0.1", 8080)
    """

    def __init__(
        self,
        repository: SkillRepository,
        *,
        session_manager: SessionManager | None = None,
        allowed_validation_paths: list[Path] | None = None,
    ) -> None:
        """Initialize the MCP server.

        Args:
            repository: The skill repository to serve.
            session_manager: Optional session manager. If not provided,
                a new one is created.
            allowed_validation_paths: Optional list of paths where validate_skill
                tool is allowed to operate. If not provided, validation is disabled.
        """
        self._repository = repository
        self._session_manager = session_manager or SessionManager()
        self._server = Server("skills-mcp")
        self._allowed_validation_paths = (
            [p.resolve() for p in allowed_validation_paths]
            if allowed_validation_paths
            else []
        )

        # Register handlers
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Register MCP protocol handlers."""
        # List resources handler
        @self._server.list_resources()  # type: ignore[no-untyped-call,untyped-decorator]
        async def list_resources() -> list[Resource]:
            """List available skill resources."""
            return await self._handle_list_resources()

        # Read resource handler
        @self._server.read_resource()  # type: ignore[no-untyped-call,untyped-decorator]
        async def read_resource(
            uri: str,
        ) -> list[TextResourceContents | BlobResourceContents]:
            """Read a skill or sub-resource."""
            return await self._handle_read_resource(uri)

        # List tools handler
        @self._server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
        async def list_tools() -> list[Tool]:
            """List available tools."""
            return await self._handle_list_tools()

        # Call tool handler
        @self._server.call_tool()  # type: ignore[untyped-decorator]
        async def call_tool(
            name: str, arguments: dict[str, Any]
        ) -> list[TextContent]:
            """Execute a tool."""
            return await self._handle_call_tool(name, arguments)

    async def _handle_list_resources(self) -> list[Resource]:
        """Handle resources/list request.

        Returns skill-level resources, plus sub-resources for any
        skills that have been expanded in the current session.

        Returns:
            List of available resources.
        """
        resources: list[Resource] = []
        skills = await self._repository.list_all()

        for skill in skills:
            # Always include skill-level resource
            skill_uri = f"{SKILL_URI_SCHEME}://{skill.name.value}"
            resources.append(
                Resource(
                    uri=AnyUrl(skill_uri),
                    name=skill.name.value,
                    description=skill.manifest.description_short,
                    mimeType="text/markdown",
                )
            )

            # Only include sub-resources if skill is expanded in this session
            session_id = _current_session_id.get()
            if session_id and self._session_manager.is_expanded(session_id, skill.name):
                resources.extend(
                    Resource(
                        uri=AnyUrl(f"{skill_uri}/scripts/{script.name}"),
                        name=script.name,
                        description=f"Script ({script.token_count} tokens)",
                        mimeType=self._get_mime_type(script.name),
                    )
                    for script in skill.scripts
                )

                resources.extend(
                    Resource(
                        uri=AnyUrl(f"{skill_uri}/references/{reference.name}"),
                        name=reference.name,
                        description=f"Reference ({reference.token_count} tokens)",
                        mimeType=self._get_mime_type(reference.name),
                    )
                    for reference in skill.references
                )

                resources.extend(
                    Resource(
                        uri=AnyUrl(f"{skill_uri}/assets/{asset.name}"),
                        name=asset.name,
                        description=f"Asset ({asset.token_count} tokens)",
                        mimeType=self._get_mime_type(asset.name),
                    )
                    for asset in skill.assets
                )

        return resources

    async def _handle_read_resource(
        self, uri: str
    ) -> list[TextResourceContents | BlobResourceContents]:
        """Handle resources/read request.

        When reading a skill-level resource, marks it as expanded
        and sends a list_changed notification.

        Args:
            uri: The resource URI to read.

        Returns:
            The resource contents.

        Raises:
            ValueError: If the URI is invalid or resource not found.
        """
        # Parse the URI: skills://{name} or skills://{name}/{type}/{file}
        if not uri.startswith(f"{SKILL_URI_SCHEME}://"):
            raise ValueError(f"Invalid URI scheme: {uri}")

        path = uri[len(f"{SKILL_URI_SCHEME}://") :]
        parts = path.split("/")

        if not parts or not parts[0]:
            raise ValueError(f"Invalid URI: {uri}")

        # Security: reject path traversal attempts
        if any(".." in part for part in parts):
            raise ValueError(f"Invalid URI: path traversal not allowed: {uri}")

        skill_name = SkillName(parts[0])

        if len(parts) == 1:
            # Reading skill instructions - this triggers expansion
            return await self._read_skill_instructions(skill_name)

        if len(parts) == URI_RESOURCE_PARTS_COUNT:
            # Reading a sub-resource: {name}/{type}/{file}
            resource_type = parts[1]
            resource_name = parts[2]
            return await self._read_skill_resource(
                skill_name, resource_type, resource_name
            )

        raise ValueError(f"Invalid URI format: {uri}")

    async def _read_skill_instructions(
        self, skill_name: SkillName
    ) -> list[TextResourceContents | BlobResourceContents]:
        """Read skill instructions (SKILL.md body).

        Marks the skill as expanded and sends a list_changed notification.

        Args:
            skill_name: The skill to read.

        Returns:
            The skill body content.
        """
        skill = await self._repository.find_by_name(skill_name)
        if skill is None:
            raise ValueError(f"Skill not found: {skill_name.value}")

        # Mark skill as expanded for this session
        session_id = _current_session_id.get()
        if session_id:
            was_expanded = self._session_manager.is_expanded(session_id, skill_name)
            self._session_manager.mark_expanded(session_id, skill_name)

            # Send list_changed notification if this is a new expansion
            if not was_expanded:
                await self._send_resources_list_changed()

        # Format body with token count header
        content = f"<!-- tokens: {skill.token_count} -->\n\n{skill.body}"

        return [
            TextResourceContents(
                uri=AnyUrl(f"{SKILL_URI_SCHEME}://{skill_name.value}"),
                mimeType="text/markdown",
                text=content,
            )
        ]

    async def _send_resources_list_changed(self) -> None:
        """Send resources/list_changed notification to client."""
        try:
            await self._server.request_context.session.send_resource_list_changed()
            logger.debug("Sent resources/list_changed notification")
        except Exception:
            # Notification failures shouldn't break the flow
            logger.warning("Failed to send resources/list_changed notification")

    async def _read_skill_resource(
        self,
        skill_name: SkillName,
        resource_type: str,
        resource_name: str,
    ) -> list[TextResourceContents | BlobResourceContents]:
        """Read a skill sub-resource.

        Args:
            skill_name: The skill name.
            resource_type: The resource type (scripts, references, assets).
            resource_name: The resource filename.

        Returns:
            The resource content.
        """
        content = await self._repository.get_resource_content(
            skill_name, resource_type, resource_name
        )

        # Try to decode as text
        try:
            text = content.decode("utf-8")
            mime_type = self._get_mime_type(resource_name)

            # Add token count comment for text files
            token_count = estimate_tokens(text)
            if mime_type == "text/x-python":
                text = f"# tokens: {token_count}\n{text}"
            elif mime_type in ("text/markdown", "text/plain"):
                text = f"<!-- tokens: {token_count} -->\n\n{text}"

            resource_uri = AnyUrl(
                f"{SKILL_URI_SCHEME}://{skill_name.value}/"
                f"{resource_type}/{resource_name}"
            )
            return [
                TextResourceContents(
                    uri=resource_uri,
                    mimeType=mime_type,
                    text=text,
                )
            ]
        except UnicodeDecodeError:
            # Binary content - return as blob
            resource_uri = AnyUrl(
                f"{SKILL_URI_SCHEME}://{skill_name.value}/"
                f"{resource_type}/{resource_name}"
            )
            return [
                BlobResourceContents(
                    uri=resource_uri,
                    mimeType="application/octet-stream",
                    blob=base64.b64encode(content).decode("ascii"),
                )
            ]

    async def _handle_list_tools(self) -> list[Tool]:
        """Handle tools/list request.

        Returns:
            List of available tools.
        """
        return [
            Tool(
                name="validate_skill",
                description="Validate a skill directory against the Agent Skills spec",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the skill directory to validate",
                        }
                    },
                    "required": ["path"],
                },
            )
        ]

    async def _handle_call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> list[TextContent]:
        """Handle tools/call request.

        Args:
            name: The tool name.
            arguments: The tool arguments.

        Returns:
            The tool result.
        """
        if name == "validate_skill":
            result = await self._validate_skill(arguments.get("path", ""))
            return [TextContent(type="text", text=result)]

        raise ValueError(f"Unknown tool: {name}")

    async def _validate_skill(self, path_str: str) -> str:
        """Validate a skill directory.

        Args:
            path_str: Path to the skill directory.

        Returns:
            Validation result message.
        """
        # Check if validation is enabled
        if not self._allowed_validation_paths:
            return "Error: Skill validation is disabled (no allowed paths configured)"

        skill_path = Path(path_str).resolve()

        # Security check: ensure path is within allowed directories
        if not self._is_validation_path_allowed(skill_path):
            return "Error: Path is outside allowed validation directories"

        # Validate path exists and is a directory with SKILL.md
        error = self._check_skill_path(skill_path, path_str)
        if error:
            return error

        parser = ManifestParser()
        try:
            manifest, body = parser.parse_file(skill_path / "SKILL.md")
            return (
                f"Valid skill: {manifest.name.value}\n"
                f"Description: {manifest.description}\n"
                f"Body length: {len(body)} characters"
            )
        except Exception as e:
            return f"Validation error: {e}"

    def _check_skill_path(self, skill_path: Path, original_path: str) -> str | None:
        """Check if skill path is valid.

        Args:
            skill_path: Resolved path to the skill directory.
            original_path: Original path string for error messages.

        Returns:
            Error message if invalid, None if valid.
        """
        if not skill_path.exists():
            return f"Error: Path does not exist: {original_path}"
        if not skill_path.is_dir():
            return f"Error: Path is not a directory: {original_path}"
        if not (skill_path / "SKILL.md").exists():
            return f"Error: SKILL.md not found in {original_path}"
        return None

    def _is_validation_path_allowed(self, path: Path) -> bool:
        """Check if a path is within allowed validation directories.

        Args:
            path: The resolved path to check.

        Returns:
            True if path is allowed, False otherwise.
        """
        try:
            resolved = path.resolve()
            for allowed_path in self._allowed_validation_paths:
                if resolved.is_relative_to(allowed_path):
                    return True
            return False
        except (ValueError, OSError):
            return False

    def _get_mime_type(self, filename: str) -> str:
        """Get MIME type for a filename.

        Args:
            filename: The filename.

        Returns:
            The MIME type.
        """
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        mime_types = {
            "py": "text/x-python",
            "js": "application/javascript",
            "ts": "application/typescript",
            "sh": "application/x-sh",
            "bash": "application/x-sh",
            "md": "text/markdown",
            "json": "application/json",
            "yaml": "application/x-yaml",
            "yml": "application/x-yaml",
            "txt": "text/plain",
            "html": "text/html",
            "css": "text/css",
        }
        return mime_types.get(ext, "text/plain")

    def create_asgi_app(self) -> Any:
        """Create an ASGI application for the MCP server.

        Returns:
            An ASGI application that handles MCP requests.
        """
        async def app(
            scope: dict[str, Any],
            receive: Any,
            send: Any,
        ) -> None:
            """ASGI application entry point."""
            if scope["type"] == "lifespan":
                # Handle lifespan events
                while True:
                    message = await receive()
                    if message["type"] == "lifespan.startup":
                        await send({"type": "lifespan.startup.complete"})
                    elif message["type"] == "lifespan.shutdown":
                        await send({"type": "lifespan.shutdown.complete"})
                        return
            elif scope["type"] == "http":
                # Extract session ID from headers
                headers = dict(scope.get("headers", []))
                session_id = headers.get(
                    b"mcp-session-id", b""
                ).decode("utf-8") or None

                # Create transport for this request
                transport = StreamableHTTPServerTransport(
                    mcp_session_id=session_id,
                    is_json_response_enabled=False,
                )

                # Store session ID for handlers (using context var for thread safety)
                if session_id:
                    _current_session_id.set(session_id)
                else:
                    _current_session_id.set(
                        self._session_manager.get_or_create().session_id
                    )

                # Handle the request
                async with transport.connect() as (read_stream, write_stream):
                    # Start the server in the background
                    import anyio  # noqa: PLC0415

                    async with anyio.create_task_group() as tg:
                        async def run_server() -> None:
                            await self._server.run(
                                read_stream,
                                write_stream,
                                self._server.create_initialization_options(
                                    notification_options=NotificationOptions(
                                        resources_changed=True,
                                    ),
                                    experimental_capabilities={},
                                ),
                            )

                        tg.start_soon(run_server)
                        await transport.handle_request(scope, receive, send)
                        tg.cancel_scope.cancel()

        return app

    async def run_http(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
    ) -> None:
        """Run the server using Streamable HTTP transport.

        Args:
            host: The host to bind to.
            port: The port to bind to.
        """
        import uvicorn  # noqa: PLC0415

        logger.info("Starting skills-mcp server on http://%s:%d", host, port)
        app = self.create_asgi_app()
        config = uvicorn.Config(app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()

    @property
    def server(self) -> Server:
        """Return the underlying MCP server."""
        return self._server
