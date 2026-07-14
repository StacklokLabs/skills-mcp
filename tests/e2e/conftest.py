"""E2E test fixtures for server subprocess management and MCP client."""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager, closing
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


# Path to test skill fixtures
FIXTURES_PATH = Path(__file__).parent.parent / "fixtures" / "skills"


def find_free_port() -> int:
    """Find a free TCP port on localhost.

    Uses ephemeral port binding to avoid conflicts.
    """
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return int(s.getsockname()[1])


@dataclass
class ServerInfo:
    """Information about a running server instance."""

    process: subprocess.Popen[str]
    host: str
    port: int

    @property
    def url(self) -> str:
        """Return the base server URL."""
        return f"http://{self.host}:{self.port}"

    @property
    def mcp_url(self) -> str:
        """Return the MCP endpoint URL."""
        return f"{self.url}/mcp"


async def wait_for_server_ready(url: str, timeout: float = 10.0) -> None:  # noqa: ASYNC109
    """Wait for server to accept connections.

    Uses exponential backoff to poll the server.

    Args:
        url: Base server URL (without /mcp path).
        timeout: Maximum time to wait in seconds.

    Raises:
        TimeoutError: If server doesn't respond within timeout.
    """
    start = asyncio.get_event_loop().time()
    delay = 0.1
    max_delay = 1.0

    async with httpx.AsyncClient() as client:
        while True:
            elapsed = asyncio.get_event_loop().time() - start
            if elapsed > timeout:
                raise TimeoutError(
                    f"Server at {url} did not become ready within {timeout}s"
                )

            try:
                # Try a simple HTTP request to the /mcp endpoint
                # Any response (even 4xx/5xx) means server is up
                await client.get(f"{url}/mcp", timeout=1.0)
                return
            except (httpx.ConnectError, httpx.TimeoutException):
                await asyncio.sleep(delay)
                delay = min(delay * 2, max_delay)


async def shutdown_server(server_info: ServerInfo, timeout: float = 5.0) -> None:  # noqa: ASYNC109
    """Gracefully shutdown the server subprocess.

    Sends SIGTERM first, then SIGKILL if needed.

    Args:
        server_info: Server instance to shutdown.
        timeout: Maximum time to wait for graceful shutdown.
    """
    process = server_info.process

    if process.poll() is not None:
        # Already terminated
        return

    # Send SIGTERM for graceful shutdown
    process.terminate()

    try:
        # Wait for graceful shutdown
        loop = asyncio.get_event_loop()
        await asyncio.wait_for(
            loop.run_in_executor(None, process.wait),
            timeout=timeout,
        )
    except TimeoutError:
        # Force kill if graceful shutdown failed
        process.kill()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, process.wait)


@pytest.fixture
async def e2e_server() -> AsyncIterator[ServerInfo]:
    """Start and manage the skills-mcp server subprocess.

    Uses the test fixtures directory for skills.
    Waits for server to be ready before yielding.
    Gracefully shuts down on cleanup.
    """
    port = find_free_port()
    host = "127.0.0.1"

    # Start server using SKILLS_MCP_PATHS environment variable
    env = {
        **os.environ,
        "SKILLS_MCP_PATHS": str(FIXTURES_PATH),
    }

    # Server output goes to an unnamed temp file, NOT subprocess.PIPE: nothing
    # drains the pipes during the run, so a chatty server would fill the OS
    # pipe buffer and deadlock mid-log-write while the client awaits forever.
    log_file = tempfile.TemporaryFile(mode="w+", encoding="utf-8")  # noqa: SIM115
    process = subprocess.Popen(  # noqa: ASYNC220, S603
        [sys.executable, "-m", "skills_mcp", "--host", host, "--port", str(port)],
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )

    server_info = ServerInfo(
        process=process,
        host=host,
        port=port,
    )

    try:
        # Wait for server to be ready
        await wait_for_server_ready(server_info.url, timeout=10.0)
        yield server_info
    finally:
        # Graceful shutdown
        await shutdown_server(server_info)
        log_file.close()


# Type alias for the client factory
ClientFactory = Callable[[], AbstractAsyncContextManager[ClientSession]]


@pytest.fixture
def mcp_client_factory(e2e_server: ServerInfo) -> ClientFactory:
    """Factory for creating multiple independent MCP client sessions.

    Use this for session isolation tests where you need multiple clients.
    Each call creates a completely new HTTP connection with its own session ID.

    Returns:
        An async context manager factory that yields ClientSession instances.
    """

    @asynccontextmanager
    async def create_client() -> AsyncIterator[ClientSession]:
        # Cannot combine these context managers due to tuple unpacking
        async with streamable_http_client(e2e_server.mcp_url) as (  # noqa: SIM117
            read,
            write,
            _,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    return create_client


def wait_for_server_ready_sync(url: str, timeout: float = 10.0) -> None:
    """Synchronously wait for the server to accept connections.

    A synchronous twin of :func:`wait_for_server_ready`, used by the
    module-scoped fixture. The module scope must NOT use an async fixture:
    ``asyncio_default_fixture_loop_scope="function"`` binds the event loop to
    each test function, so a module-scoped async fixture would run on a loop
    that is torn down before the module's tests finish — a loop-scope trap.
    Keeping the fixture synchronous side-steps that entirely.

    Args:
        url: Base server URL (without /mcp path).
        timeout: Maximum time to wait in seconds.

    Raises:
        TimeoutError: If server doesn't respond within timeout.
    """
    start = time.monotonic()
    delay = 0.1
    max_delay = 1.0

    with httpx.Client() as client:
        while True:
            if time.monotonic() - start > timeout:
                raise TimeoutError(
                    f"Server at {url} did not become ready within {timeout}s"
                )
            try:
                client.get(f"{url}/mcp", timeout=1.0)
                return
            except (httpx.ConnectError, httpx.TimeoutException):
                time.sleep(delay)
                delay = min(delay * 2, max_delay)


def shutdown_server_sync(server_info: ServerInfo, timeout: float = 5.0) -> None:
    """Synchronously terminate the server subprocess.

    Sends SIGTERM first, escalating to SIGKILL if it doesn't exit in time.

    Args:
        server_info: Server instance to shut down.
        timeout: Maximum time to wait for graceful shutdown.
    """
    process = server_info.process
    if process.poll() is not None:
        # Already terminated
        return

    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


@pytest.fixture(scope="module")
def e2e_server_module() -> Iterator[ServerInfo]:
    """Start one shared skills-mcp server for a whole test module.

    Deliberately synchronous (see :func:`wait_for_server_ready_sync`). Shares a
    single subprocess across every test in the module to amortize startup cost,
    while each test still opens its own MCP client session (and thus its own
    session ID) via :func:`mcp_client_factory_shared`.
    """
    port = find_free_port()
    host = "127.0.0.1"

    env = {
        **os.environ,
        "SKILLS_MCP_PATHS": str(FIXTURES_PATH),
    }

    # See e2e_server: output must go to a temp file, not an undrained PIPE.
    # This matters even more here — the module-scoped server accumulates a
    # whole module's worth of log output and WILL fill the pipe buffer.
    log_file = tempfile.TemporaryFile(mode="w+", encoding="utf-8")  # noqa: SIM115
    process = subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "skills_mcp", "--host", host, "--port", str(port)],
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )

    server_info = ServerInfo(
        process=process,
        host=host,
        port=port,
    )

    try:
        wait_for_server_ready_sync(server_info.url, timeout=10.0)
        yield server_info
    finally:
        shutdown_server_sync(server_info)
        log_file.close()


@pytest.fixture
def mcp_client_factory_shared(e2e_server_module: ServerInfo) -> ClientFactory:
    """Function-scoped client factory over the module-scoped shared server.

    Each call creates a fresh HTTP connection with its own MCP session ID, so
    tests remain isolated at the session level even though they share the
    underlying server process.
    """

    @asynccontextmanager
    async def create_client() -> AsyncIterator[ClientSession]:
        async with streamable_http_client(e2e_server_module.mcp_url) as (  # noqa: SIM117
            read,
            write,
            _,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    return create_client
