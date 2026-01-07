"""Tests for session management."""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

import pytest

from skills_mcp.domain.models.skill_name import SkillName
from skills_mcp.infrastructure.mcp.session import (
    DEFAULT_SESSION_TIMEOUT,
    SessionManager,
    SessionState,
)


class TestSessionState:
    """Tests for SessionState."""

    def test_create_session_state(self) -> None:
        """Should create session state with given ID."""
        state = SessionState(session_id="test-123")
        assert state.session_id == "test-123"
        assert state.expanded_skills == set()

    def test_is_expanded_false_initially(self) -> None:
        """Should return False for skills not yet expanded."""
        state = SessionState(session_id="test-123")
        assert state.is_expanded(SkillName("some-skill")) is False

    def test_mark_expanded_adds_skill(self) -> None:
        """Should mark skill as expanded."""
        state = SessionState(session_id="test-123")
        skill_name = SkillName("test-skill")

        state.mark_expanded(skill_name)

        assert state.is_expanded(skill_name) is True
        assert "test-skill" in state.expanded_skills

    def test_mark_expanded_updates_last_accessed(self) -> None:
        """Should update last_accessed when marking expanded."""
        state = SessionState(session_id="test-123")
        original_time = state.last_accessed

        # Force a time difference
        state.mark_expanded(SkillName("test-skill"))

        assert state.last_accessed >= original_time

    def test_touch_updates_last_accessed(self) -> None:
        """Should update last_accessed on touch."""
        state = SessionState(session_id="test-123")
        original_time = state.last_accessed

        state.touch()

        assert state.last_accessed >= original_time


class TestSessionManager:
    """Tests for SessionManager."""

    def test_get_or_create_new_session(self) -> None:
        """Should create new session when ID doesn't exist."""
        manager = SessionManager()

        session = manager.get_or_create("session-1")

        assert session.session_id == "session-1"
        assert manager.session_count == 1

    def test_get_or_create_returns_existing_session(self) -> None:
        """Should return existing session when ID exists."""
        manager = SessionManager()

        session1 = manager.get_or_create("session-1")
        session1.mark_expanded(SkillName("test-skill"))

        session2 = manager.get_or_create("session-1")

        assert session2 is session1
        assert session2.is_expanded(SkillName("test-skill"))

    def test_get_or_create_generates_uuid_when_none(self) -> None:
        """Should generate UUID when session_id is None."""
        manager = SessionManager()

        session = manager.get_or_create(None)

        assert session.session_id is not None
        assert len(session.session_id) > 0

    def test_get_returns_existing_session(self) -> None:
        """Should return session by ID."""
        manager = SessionManager()
        created = manager.get_or_create("session-1")

        found = manager.get("session-1")

        assert found is created

    def test_get_returns_none_for_unknown_session(self) -> None:
        """Should return None for unknown session ID."""
        manager = SessionManager()

        found = manager.get("nonexistent")

        assert found is None

    def test_mark_expanded_creates_session_if_needed(self) -> None:
        """Should create session when marking expanded."""
        manager = SessionManager()
        skill_name = SkillName("test-skill")

        manager.mark_expanded("new-session", skill_name)

        assert manager.is_expanded("new-session", skill_name) is True

    def test_is_expanded_returns_false_for_unknown_session(self) -> None:
        """Should return False for unknown session."""
        manager = SessionManager()

        assert manager.is_expanded("nonexistent", SkillName("skill")) is False

    def test_sessions_are_isolated(self) -> None:
        """Different sessions should have isolated state."""
        manager = SessionManager()
        skill_name = SkillName("test-skill")

        manager.mark_expanded("session-1", skill_name)

        assert manager.is_expanded("session-1", skill_name) is True
        assert manager.is_expanded("session-2", skill_name) is False

    def test_cleanup_expired_removes_old_sessions(self) -> None:
        """Should remove sessions older than timeout."""
        # Use a very short timeout
        manager = SessionManager(timeout=timedelta(seconds=0))

        # Create a session
        manager.get_or_create("old-session")

        # Cleanup should remove it
        removed = manager.cleanup_expired()

        assert removed == 1
        assert manager.session_count == 0

    def test_cleanup_expired_keeps_recent_sessions(self) -> None:
        """Should keep sessions within timeout."""
        manager = SessionManager(timeout=timedelta(hours=24))

        manager.get_or_create("recent-session")

        removed = manager.cleanup_expired()

        assert removed == 0
        assert manager.session_count == 1

    def test_remove_deletes_session(self) -> None:
        """Should remove specific session."""
        manager = SessionManager()
        manager.get_or_create("session-1")

        result = manager.remove("session-1")

        assert result is True
        assert manager.session_count == 0

    def test_remove_returns_false_for_unknown_session(self) -> None:
        """Should return False when session doesn't exist."""
        manager = SessionManager()

        result = manager.remove("nonexistent")

        assert result is False

    def test_default_timeout(self) -> None:
        """Should use 24 hour default timeout."""
        assert timedelta(hours=24) == DEFAULT_SESSION_TIMEOUT

    def test_session_count_property(self) -> None:
        """Should track number of active sessions."""
        manager = SessionManager()

        assert manager.session_count == 0

        manager.get_or_create("session-1")
        assert manager.session_count == 1

        manager.get_or_create("session-2")
        assert manager.session_count == 2

    def test_session_id_validation_too_long(self) -> None:
        """Should reject session IDs that are too long."""
        manager = SessionManager()

        # Session ID over 256 characters
        long_id = "a" * 257

        with pytest.raises(ValueError, match="too long"):
            manager.get_or_create(long_id)

    def test_session_id_validation_invalid_characters(self) -> None:
        """Should reject session IDs with invalid characters."""
        manager = SessionManager()

        with pytest.raises(ValueError, match="invalid characters"):
            manager.get_or_create("session<script>alert(1)</script>")

    def test_session_id_validation_allows_valid_ids(self) -> None:
        """Should accept valid session IDs."""
        manager = SessionManager()

        # These should all be valid
        valid_ids = [
            "abc123",
            "session-1",
            "SESSION_ID",
            "a1b2c3-d4e5f6_G7H8I9",
            "a" * 256,  # Exactly at max length
        ]

        for session_id in valid_ids:
            session = manager.get_or_create(session_id)
            assert session.session_id == session_id


class TestSessionManagerConcurrency:
    """Tests for concurrent access to SessionManager."""

    def test_concurrent_session_creation(self) -> None:
        """Should safely handle concurrent session creation."""
        manager = SessionManager()
        session_ids = [f"session-{i}" for i in range(100)]

        def create_session(session_id: str) -> str:
            session = manager.get_or_create(session_id)
            return session.session_id

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(create_session, sid) for sid in session_ids]
            results = [f.result() for f in as_completed(futures)]

        # All sessions should be created
        assert len(results) == 100
        assert manager.session_count == 100

    def test_concurrent_get_or_create_same_session(self) -> None:
        """Multiple threads creating the same session should get same instance."""
        manager = SessionManager()
        results: list[SessionState] = []
        lock = threading.Lock()

        def get_session() -> None:
            session = manager.get_or_create("shared-session")
            with lock:
                results.append(session)

        threads = [threading.Thread(target=get_session) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads should get the same session instance
        assert len(results) == 10
        first_session = results[0]
        for session in results[1:]:
            assert session is first_session

    def test_concurrent_mark_expanded(self) -> None:
        """Should safely handle concurrent mark_expanded calls."""
        manager = SessionManager()

        def mark_skill(skill_name: str) -> None:
            manager.mark_expanded("session-1", SkillName(skill_name))

        skill_names = [f"skill-{i}" for i in range(50)]

        with ThreadPoolExecutor(max_workers=10) as executor:
            list(executor.map(mark_skill, skill_names))

        # All skills should be marked as expanded
        for skill_name in skill_names:
            assert manager.is_expanded("session-1", SkillName(skill_name))

    def test_concurrent_cleanup_and_access(self) -> None:
        """Should safely handle cleanup during concurrent access."""
        manager = SessionManager(timeout=timedelta(hours=24))
        errors: list[Exception] = []
        lock = threading.Lock()

        def create_and_access() -> None:
            try:
                for i in range(10):
                    session_id = f"session-{threading.current_thread().name}-{i}"
                    manager.get_or_create(session_id)
                    manager.mark_expanded(session_id, SkillName("test-skill"))
            except Exception as e:
                with lock:
                    errors.append(e)

        def cleanup_loop() -> None:
            try:
                for _ in range(5):
                    manager.cleanup_expired()
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [
            threading.Thread(target=create_and_access, name=f"worker-{i}")
            for i in range(5)
        ]
        threads.append(threading.Thread(target=cleanup_loop, name="cleaner"))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No exceptions should have been raised
        assert len(errors) == 0

    def test_concurrent_remove_and_access(self) -> None:
        """Should safely handle remove during concurrent access."""
        manager = SessionManager()
        errors: list[Exception] = []
        lock = threading.Lock()

        # Create initial sessions
        for i in range(20):
            manager.get_or_create(f"session-{i}")

        def access_sessions() -> None:
            try:
                for i in range(20):
                    manager.get(f"session-{i}")
                    manager.is_expanded(f"session-{i}", SkillName("test"))
            except Exception as e:
                with lock:
                    errors.append(e)

        def remove_sessions() -> None:
            try:
                for i in range(20):
                    manager.remove(f"session-{i}")
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [
            threading.Thread(target=access_sessions) for _ in range(3)
        ] + [threading.Thread(target=remove_sessions)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No exceptions should have been raised
        assert len(errors) == 0
