"""MCP server implementation using Streamable HTTP transport.

Provides the main MCP server that exposes skills as resources,
tools, and prompts with progressive disclosure.

Skills are exposed through three complementary MCP mechanisms to
maximize compatibility across different AI coding agents:

1. **Resources** (``skills://`` URIs): Progressive disclosure for
   resource-aware clients (Roo Code, Cline).
2. **Tools** (``list_skills``, ``get_skill``, ``get_skill_resource``):
   Mirror the ``Skill`` tool pattern used by Claude Code, Roo Code,
   Cline, and Continue for universal tool-calling compatibility.
3. **Prompts**: Each skill as an MCP prompt, automatically converted
   to slash commands by clients like Continue.
"""

from __future__ import annotations

import contextlib
import json
import logging
import mimetypes
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp.server import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import (
    GetPromptResult,
    Prompt,
    PromptArgument,
    PromptMessage,
    Resource,
    TextContent,
    Tool,
)
from pydantic import AnyUrl
from starlette.applications import Starlette
from starlette.routing import Mount

from skills_mcp.domain.models.skill_name import SkillName
from skills_mcp.domain.services.manifest_parser import ManifestParser
from skills_mcp.domain.services.token_estimator import estimate_tokens
from skills_mcp.infrastructure.mcp.session import SessionManager


if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from starlette.types import Receive, Scope, Send

    from skills_mcp.domain.repositories import SkillRepository


logger = logging.getLogger(__name__)


# URI scheme for skills
SKILL_URI_SCHEME = "skills"

# URI path structure: skills://{name}/{type}/{file} has 3 parts
URI_RESOURCE_PARTS_COUNT = 3

# Default HTTP settings
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080

# MCP Session ID header name
MCP_SESSION_ID_HEADER = "mcp-session-id"


class SkillsMCPServer:
    """MCP server that exposes Agent Skills with progressive disclosure.

    The server exposes skills as resources with a three-tier disclosure model:
    1. Metadata tier: Only skill names and descriptions initially visible
    2. Instructions tier: Full SKILL.md body when skill is accessed
    3. Resources tier: Scripts, references, assets exposed after skill read

    Each MCP connection has isolated session state tracking which skills
    have been "expanded" (had their sub-resources revealed).

    Uses Streamable HTTP transport for communication via the MCP SDK's
    StreamableHTTPSessionManager for proper session handling.

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
            session_manager: Optional session manager for tracking expanded skills.
                If not provided, a new one is created.
            allowed_validation_paths: Optional list of paths where validate_skill
                tool is allowed to operate. If not provided, validation is disabled.
        """
        self._repository = repository
        self._session_manager = session_manager or SessionManager()
        self._server = Server(
            "skills-mcp",
            instructions=(
                "This server provides Agent Skills — reusable instructions, "
                "scripts, and resources that help you perform specific tasks.\n\n"
                "Use the `list_skills` tool to discover available skills. "
                "When a skill matches the current task, use `get_skill` to "
                "load its full instructions. Use `get_skill_resource` to "
                "load supporting files (scripts, references, assets) "
                "referenced by the skill."
            ),
        )
        self._allowed_validation_paths = (
            [p.resolve() for p in allowed_validation_paths]
            if allowed_validation_paths
            else []
        )
        self._http_session_manager: StreamableHTTPSessionManager | None = None

        # Register handlers
        self._register_handlers()

    def _get_session_id(self) -> str:
        """Get the current MCP session ID from the request context.

        The session ID is extracted from the mcp-session-id header which is
        required on all requests after initialization per the MCP spec.

        Returns:
            The session ID string, or "default" if not available.
        """
        try:
            # Access the Starlette Request object from request context
            # This is set by StreamableHTTPServerTransport via ServerMessageMetadata
            request = self._server.request_context.request
            if request is not None and hasattr(request, "headers"):
                session_id: str | None = request.headers.get(MCP_SESSION_ID_HEADER)
                if session_id:
                    return session_id
        except LookupError:
            # Outside of request context - this is expected during startup
            logger.debug("No request context available for session ID")
        return "default"

    def _register_handlers(self) -> None:
        """Register MCP protocol handlers.

        Registers three complementary sets of handlers:
        - **Resources**: Progressive disclosure via ``skills://`` URIs
        - **Tools**: ``list_skills``, ``get_skill``, ``get_skill_resource``,
          ``validate_skill`` for tool-calling clients
        - **Prompts**: Each skill as an MCP prompt for slash-command clients
        """

        # List resources handler
        @self._server.list_resources()  # type: ignore[no-untyped-call,untyped-decorator]
        async def list_resources() -> list[Resource]:
            """List available skill resources."""
            return await self._handle_list_resources()

        # Read resource handler
        @self._server.read_resource()  # type: ignore[no-untyped-call,untyped-decorator]
        async def read_resource(uri: AnyUrl) -> list[ReadResourceContents]:
            """Read a skill or sub-resource."""
            return await self._handle_read_resource(str(uri))

        # List tools handler
        @self._server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
        async def list_tools() -> list[Tool]:
            """List available tools."""
            return await self._handle_list_tools()

        # Call tool handler
        @self._server.call_tool()  # type: ignore[untyped-decorator]
        async def call_tool(
            name: str, arguments: dict[str, Any] | None
        ) -> list[TextContent]:
            """Execute a tool."""
            return await self._handle_call_tool(name, arguments or {})

        # List prompts handler
        @self._server.list_prompts()  # type: ignore[no-untyped-call,untyped-decorator]
        async def list_prompts() -> list[Prompt]:
            """List skills as MCP prompts."""
            return await self._handle_list_prompts()

        # Get prompt handler
        @self._server.get_prompt()  # type: ignore[no-untyped-call,untyped-decorator]
        async def get_prompt(
            name: str, arguments: dict[str, str] | None = None
        ) -> GetPromptResult:
            """Get a skill's content as an MCP prompt."""
            return await self._handle_get_prompt(name, arguments)

    async def _handle_list_resources(self) -> list[Resource]:
        """Handle resources/list request.

        Returns skill-level resources, plus sub-resources for any
        skills that have been expanded in the current session.

        Returns:
            List of available resources.
        """
        resources: list[Resource] = []
        skills = await self._repository.list_all()
        session_id = self._get_session_id()

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
            if self._session_manager.is_expanded(session_id, skill.name):
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

    async def _handle_read_resource(self, uri: str) -> list[ReadResourceContents]:
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
    ) -> list[ReadResourceContents]:
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
        session_id = self._get_session_id()
        was_expanded = self._session_manager.is_expanded(session_id, skill_name)
        self._session_manager.mark_expanded(session_id, skill_name)

        # Send list_changed notification if this is a new expansion
        if not was_expanded:
            await self._send_resources_list_changed()

        # Format body with token count header
        content = f"<!-- tokens: {skill.token_count} -->\n\n{skill.body}"

        return [ReadResourceContents(content=content, mime_type="text/markdown")]

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
    ) -> list[ReadResourceContents]:
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

            return [ReadResourceContents(content=text, mime_type=mime_type)]
        except UnicodeDecodeError:
            # Binary content - return as bytes
            return [
                ReadResourceContents(
                    content=content, mime_type="application/octet-stream"
                )
            ]

    async def _build_skill_catalog_description(self) -> str:
        """Build a dynamic tool description with embedded skill catalog.

        This mirrors Claude Code's pattern of embedding an ``<available_skills>``
        list in the Skill tool description, so models know what's available
        without making a separate tool call.

        Returns:
            Description string with embedded skill catalog.
        """
        skills = await self._repository.list_all()
        lines = [
            "List all available Agent Skills with their names and descriptions.",
            "",
            "Currently available skills:",
        ]
        if skills:
            lines.extend(
                f"- {skill.name.value}: {skill.manifest.description_short}"
                for skill in skills
            )
        else:
            lines.append("- (no skills currently loaded)")
        lines.append("")
        lines.append(
            "Returns the full catalog as JSON with name, description, "
            "and resource counts for each skill."
        )
        return "\n".join(lines)

    async def _handle_list_tools(self) -> list[Tool]:
        """Handle tools/list request.

        Returns tools that mirror how AI coding agents natively handle skills:
        - ``list_skills``: Discover available skills (Tier 1 catalog)
        - ``get_skill``: Load a skill's instructions (Tier 2 activation)
        - ``get_skill_resource``: Load a skill's files (Tier 3 resources)
        - ``validate_skill``: Validate a skill directory

        Returns:
            List of available tools.
        """
        catalog_description = await self._build_skill_catalog_description()

        return [
            Tool(
                name="list_skills",
                description=catalog_description,
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="get_skill",
                description=(
                    "Load a skill's full instructions by name. Call this when "
                    "you need to follow a skill's workflow or procedures. "
                    "Returns the complete SKILL.md body content along with "
                    "metadata about available resources (scripts, references, "
                    "assets) that can be loaded with get_skill_resource."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "The skill name (e.g., 'code-review')",
                        }
                    },
                    "required": ["name"],
                },
            ),
            Tool(
                name="get_skill_resource",
                description=(
                    "Load a specific resource file from a skill. Resources "
                    "include scripts, references, and assets that support "
                    "the skill's instructions."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "skill_name": {
                            "type": "string",
                            "description": "The skill name",
                        },
                        "resource_path": {
                            "type": "string",
                            "description": (
                                "Path to the resource relative to the skill "
                                "directory (e.g., 'scripts/analyze.py', "
                                "'references/guide.md')"
                            ),
                        },
                    },
                    "required": ["skill_name", "resource_path"],
                },
            ),
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
            ),
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
        if name == "list_skills":
            return await self._tool_list_skills()
        if name == "get_skill":
            return await self._tool_get_skill(arguments.get("name", ""))
        if name == "get_skill_resource":
            return await self._tool_get_skill_resource(
                arguments.get("skill_name", ""),
                arguments.get("resource_path", ""),
            )
        if name == "validate_skill":
            result = await self._validate_skill(arguments.get("path", ""))
            return [TextContent(type="text", text=result)]

        raise ValueError(f"Unknown tool: {name}")

    async def _tool_list_skills(self) -> list[TextContent]:
        """Handle list_skills tool call.

        Returns Tier 1 catalog: name, description, and resource counts
        for all available skills.

        Returns:
            JSON-formatted skill catalog.
        """
        skills = await self._repository.list_all()
        catalog = []
        for skill in skills:
            entry: dict[str, object] = {
                "name": skill.name.value,
                "description": skill.manifest.description,
            }
            # Include resource counts so the model knows what's available
            resource_count = len(skill.all_resources)
            if resource_count > 0:
                entry["resources"] = {
                    "scripts": len(skill.scripts),
                    "references": len(skill.references),
                    "assets": len(skill.assets),
                }
            catalog.append(entry)

        return [TextContent(type="text", text=json.dumps(catalog, indent=2))]

    async def _tool_get_skill(self, name_str: str) -> list[TextContent]:
        """Handle get_skill tool call.

        Returns Tier 2 content: full SKILL.md body with metadata and
        resource listing. Also marks the skill as expanded for this session.

        Args:
            name_str: The skill name string.

        Returns:
            Skill instructions with metadata.
        """
        if not name_str:
            return [TextContent(type="text", text="Error: skill name is required")]

        try:
            skill_name = SkillName(name_str)
        except ValueError as e:
            return [TextContent(type="text", text=f"Error: invalid skill name: {e}")]

        skill = await self._repository.find_by_name(skill_name)
        if skill is None:
            return [
                TextContent(type="text", text=f"Error: skill not found: {name_str}")
            ]

        # Mark as expanded for this session (for resource listings)
        session_id = self._get_session_id()
        was_expanded = self._session_manager.is_expanded(session_id, skill_name)
        self._session_manager.mark_expanded(session_id, skill_name)
        if not was_expanded:
            await self._send_resources_list_changed()

        # Build response with instructions dict (matches Skill.to_instructions_dict)
        result = skill.to_instructions_dict()
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    async def _tool_get_skill_resource(
        self, skill_name_str: str, resource_path: str
    ) -> list[TextContent]:
        """Handle get_skill_resource tool call.

        Returns Tier 3 content: a specific resource file from a skill.

        Args:
            skill_name_str: The skill name.
            resource_path: Relative path like ``scripts/analyze.py``.

        Returns:
            The resource file content.
        """
        error = self._validate_resource_args(skill_name_str, resource_path)
        if error:
            return [TextContent(type="text", text=error)]

        # Parse resource_path into type + name (e.g., "scripts/analyze.py")
        parts = resource_path.strip("/").split("/", 1)
        if len(parts) != 2:  # noqa: PLR2004
            return [
                TextContent(
                    type="text",
                    text=(
                        "Error: resource_path must be in format "
                        "'type/filename' (e.g., 'scripts/analyze.py')"
                    ),
                )
            ]

        resource_type, resource_name = parts

        try:
            skill_name = SkillName(skill_name_str)
            content = await self._repository.get_resource_content(
                skill_name, resource_type, resource_name
            )
            text = content.decode("utf-8")
            return [TextContent(type="text", text=text)]
        except UnicodeDecodeError:
            return [
                TextContent(
                    type="text",
                    text="Error: resource is binary and cannot be returned as text",
                )
            ]
        except ValueError as e:
            return [TextContent(type="text", text=f"Error: {e}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error loading resource: {e}")]

    @staticmethod
    def _validate_resource_args(skill_name_str: str, resource_path: str) -> str | None:
        """Validate arguments for get_skill_resource.

        Returns:
            Error message if invalid, None if valid.
        """
        if not skill_name_str:
            return "Error: skill_name is required"
        if not resource_path:
            return "Error: resource_path is required"
        if ".." in resource_path:
            return "Error: path traversal not allowed"
        return None

    # ------------------------------------------------------------------
    # Prompt handlers — each skill exposed as an MCP prompt
    # ------------------------------------------------------------------

    async def _handle_list_prompts(self) -> list[Prompt]:
        """Handle prompts/list request.

        Exposes each skill as an MCP prompt. Clients like Continue.dev
        automatically convert MCP prompts into slash commands, giving
        users ``/skill-name`` invocation for free.

        Returns:
            List of prompts, one per skill.
        """
        skills = await self._repository.list_all()
        return [
            Prompt(
                name=skill.name.value,
                description=skill.manifest.description_short,
                arguments=[
                    PromptArgument(
                        name="args",
                        description="Optional arguments for the skill",
                        required=False,
                    )
                ],
            )
            for skill in skills
        ]

    async def _handle_get_prompt(
        self,
        name: str,
        arguments: dict[str, str] | None = None,
    ) -> GetPromptResult:
        """Handle prompts/get request.

        Returns the skill's full SKILL.md body as a user message,
        mimicking how Claude Code injects skill content into
        the conversation as prompt expansion.

        Args:
            name: The skill/prompt name.
            arguments: Optional arguments (``args`` key).

        Returns:
            GetPromptResult with the skill body as a user message.
        """
        try:
            skill_name = SkillName(name)
        except ValueError as e:
            raise ValueError(f"Invalid skill name: {e}") from e

        skill = await self._repository.find_by_name(skill_name)
        if skill is None:
            raise ValueError(f"Skill not found: {name}")

        # Mark as expanded for this session
        session_id = self._get_session_id()
        was_expanded = self._session_manager.is_expanded(session_id, skill_name)
        self._session_manager.mark_expanded(session_id, skill_name)
        if not was_expanded:
            await self._send_resources_list_changed()

        # Build the prompt content
        body = skill.body

        # If args were provided, append them (matching Claude Code's behavior)
        args = (arguments or {}).get("args")
        if args:
            body = f"{body}\n\nARGUMENTS: {args}"

        # Include resource listing if the skill has any
        if skill.all_resources:
            resource_lines = ["\n\n---\nAvailable resources for this skill:"]
            resource_lines.extend(
                f"- scripts/{r.name} ({r.token_count} tokens)" for r in skill.scripts
            )
            resource_lines.extend(
                f"- references/{r.name} ({r.token_count} tokens)"
                for r in skill.references
            )
            resource_lines.extend(
                f"- assets/{r.name} ({r.token_count} tokens)" for r in skill.assets
            )
            resource_lines.append("\nUse get_skill_resource to load any of these.")
            body += "\n".join(resource_lines)

        return GetPromptResult(
            description=skill.manifest.description,
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(type="text", text=body),
                )
            ],
        )

    # ------------------------------------------------------------------
    # Validation tool
    # ------------------------------------------------------------------

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
        mime_type, _ = mimetypes.guess_type(filename)
        # Fallback for types mimetypes doesn't know well
        if mime_type is None:
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            fallbacks = {
                "ts": "application/typescript",
                "yaml": "application/x-yaml",
                "yml": "application/x-yaml",
            }
            mime_type = fallbacks.get(ext, "text/plain")
        return mime_type

    def create_asgi_app(self) -> Starlette:
        """Create a Starlette ASGI application for the MCP server.

        Uses the MCP SDK's StreamableHTTPSessionManager for proper
        session handling and transport management.

        Returns:
            A Starlette application that handles MCP requests at /mcp.
        """
        # Create the session manager for streamable HTTP
        self._http_session_manager = StreamableHTTPSessionManager(
            app=self._server,
            json_response=False,  # Use SSE streaming
            stateless=False,  # Maintain session state
        )

        # ASGI handler wrapper for the session manager
        async def handle_mcp_request(
            scope: Scope, receive: Receive, send: Send
        ) -> None:
            """Handle MCP requests via the session manager."""
            await self._http_session_manager.handle_request(  # type: ignore[union-attr]
                scope, receive, send
            )

        @contextlib.asynccontextmanager
        async def lifespan(_app: Starlette) -> AsyncIterator[None]:
            """Manage server lifecycle with the HTTP session manager."""
            async with self._http_session_manager.run():  # type: ignore[union-attr]
                logger.info("MCP session manager started")
                yield
                logger.info("MCP session manager stopped")

        # Create the Starlette app with routes
        # Use Mount instead of Route because handle_request is an ASGI app,
        # not an HTTP endpoint that returns a Response
        return Starlette(
            debug=False,
            routes=[
                Mount("/mcp", app=handle_mcp_request),
            ],
            lifespan=lifespan,
        )

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

        logger.info("Starting skills-mcp server on http://%s:%d/mcp", host, port)
        app = self.create_asgi_app()
        config = uvicorn.Config(app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()

    @property
    def server(self) -> Server:
        """Return the underlying MCP server."""
        return self._server
