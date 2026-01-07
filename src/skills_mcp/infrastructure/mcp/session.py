"""Session state management for MCP connections.

Each MCP connection has its own session state tracking which skills
have been "expanded" (their sub-resources are visible).
"""

from __future__ import annotations

import logging
import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from skills_mcp.domain.models.skill_name import SkillName


logger = logging.getLogger(__name__)


# Default session timeout
DEFAULT_SESSION_TIMEOUT = timedelta(hours=24)

# Session ID constraints
MAX_SESSION_ID_LENGTH = 256
# Allow alphanumeric, hyphens, underscores (safe for logging and dict keys)
SESSION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


@dataclass
class SessionState:
    """Per-connection session state.

    Tracks which skills have been "expanded" for this session,
    meaning their sub-resources (scripts, references, assets)
    should be visible in resource listings.

    Attributes:
        session_id: Unique identifier for this session.
        expanded_skills: Set of skill names that have been expanded.
        created_at: When the session was created.
        last_accessed: When the session was last accessed.
    """

    session_id: str
    expanded_skills: set[str] = field(default_factory=set)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_accessed: datetime = field(default_factory=lambda: datetime.now(UTC))

    def is_expanded(self, skill_name: SkillName) -> bool:
        """Check if a skill is expanded in this session.

        Args:
            skill_name: The skill name to check.

        Returns:
            True if the skill is expanded, False otherwise.
        """
        return skill_name.value in self.expanded_skills

    def mark_expanded(self, skill_name: SkillName) -> None:
        """Mark a skill as expanded in this session.

        Args:
            skill_name: The skill name to mark as expanded.
        """
        self.expanded_skills.add(skill_name.value)
        self.last_accessed = datetime.now(UTC)

    def touch(self) -> None:
        """Update the last accessed timestamp."""
        self.last_accessed = datetime.now(UTC)


class SessionManager:
    """Manages per-connection session state.

    This class provides thread-safe management of session state for
    multiple concurrent MCP connections. Each connection gets its own
    session with isolated state.

    Example:
        manager = SessionManager()
        session = manager.get_or_create("session-123")
        session.mark_expanded(SkillName("data-analysis"))
        if session.is_expanded(SkillName("data-analysis")):
            # Include sub-resources in listing
            pass
    """

    def __init__(self, timeout: timedelta = DEFAULT_SESSION_TIMEOUT) -> None:
        """Initialize the session manager.

        Args:
            timeout: Maximum age for sessions before cleanup.
        """
        self._sessions: dict[str, SessionState] = {}
        self._timeout = timeout
        self._lock = threading.RLock()  # Reentrant lock for nested calls

    def get_or_create(self, session_id: str | None = None) -> SessionState:
        """Get an existing session or create a new one.

        Args:
            session_id: Optional session ID. If not provided, a new UUID
                is generated. If provided, it must pass validation.

        Returns:
            The session state for the given ID.

        Raises:
            ValueError: If the session ID is invalid.
        """
        if session_id is None:
            session_id = str(uuid.uuid4())
        else:
            # Validate externally-provided session ID
            self._validate_session_id(session_id)

        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionState(session_id=session_id)
                logger.debug("Created new session: %s", session_id)

            session = self._sessions[session_id]
            session.touch()
            return session

    def get(self, session_id: str) -> SessionState | None:
        """Get an existing session by ID.

        Args:
            session_id: The session ID to look up.

        Returns:
            The session state, or None if not found.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                session.touch()
            return session

    def mark_expanded(self, session_id: str, skill_name: SkillName) -> None:
        """Mark a skill as expanded in a session.

        Args:
            session_id: The session ID.
            skill_name: The skill name to mark as expanded.
        """
        with self._lock:
            session = self.get_or_create(session_id)
            session.mark_expanded(skill_name)
            logger.debug(
                "Marked skill as expanded: session=%s, skill=%s",
                session_id,
                skill_name.value,
            )

    def is_expanded(self, session_id: str, skill_name: SkillName) -> bool:
        """Check if a skill is expanded in a session.

        Args:
            session_id: The session ID.
            skill_name: The skill name to check.

        Returns:
            True if the skill is expanded, False otherwise.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            return session.is_expanded(skill_name)

    def cleanup_expired(self) -> int:
        """Remove expired sessions.

        Returns:
            Number of sessions removed.
        """
        with self._lock:
            now = datetime.now(UTC)
            expired = [
                sid
                for sid, session in self._sessions.items()
                if now - session.last_accessed > self._timeout
            ]

            for sid in expired:
                del self._sessions[sid]

            if expired:
                logger.info("Cleaned up %d expired sessions", len(expired))

            return len(expired)

    def remove(self, session_id: str) -> bool:
        """Remove a specific session.

        Args:
            session_id: The session ID to remove.

        Returns:
            True if the session was removed, False if not found.
        """
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.debug("Removed session: %s", session_id)
                return True
            return False

    @property
    def session_count(self) -> int:
        """Return the number of active sessions."""
        with self._lock:
            return len(self._sessions)

    def _validate_session_id(self, session_id: str) -> None:
        """Validate a session ID.

        Args:
            session_id: The session ID to validate.

        Raises:
            ValueError: If the session ID is invalid.
        """
        if len(session_id) > MAX_SESSION_ID_LENGTH:
            raise ValueError(
                f"Session ID too long: {len(session_id)} > {MAX_SESSION_ID_LENGTH}"
            )
        if not SESSION_ID_PATTERN.match(session_id):
            raise ValueError("Session ID contains invalid characters")
