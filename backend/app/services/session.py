import logging
import threading
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

logger = logging.getLogger(__name__)


@dataclass
class SessionConfig:
    """Configuration for session management"""
    max_messages_per_session: int = 50
    session_timeout_minutes: int = 60
    max_total_sessions: int = 10000
    cleanup_interval_seconds: int = 300  # Run cleanup every 5 minutes
    enable_auto_cleanup: bool = True


@dataclass
class SessionData:
    """Data stored for each session"""
    session_id: str
    messages: List[BaseMessage] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed: datetime = field(default_factory=datetime.utcnow)
    message_count: int = 0


class SessionStorage(ABC):
    """Abstract interface for session storage backends

    This allows swapping between in-memory, Redis, database, etc.
    """

    @abstractmethod
    def get_session(self, session_id: str) -> Optional[SessionData]:
        """Retrieve session data by ID"""
        pass

    @abstractmethod
    def save_session(self, session_data: SessionData):
        """Save or update session data"""
        pass

    @abstractmethod
    def delete_session(self, session_id: str):
        """Delete a session"""
        pass

    @abstractmethod
    def get_all_session_ids(self) -> List[str]:
        """Get all active session IDs"""
        pass

    @abstractmethod
    def get_session_count(self) -> int:
        """Get total number of active sessions"""
        pass


class InMemorySessionStorage(SessionStorage):
    """Thread-safe in-memory session storage

    Suitable for:
    - Development
    - Single-instance deployments
    - Low-to-medium traffic

    Not suitable for:
    - Multi-instance deployments (sessions not shared)
    - High-availability requirements (data lost on restart)
    """

    def __init__(self):
        self._sessions: Dict[str, SessionData] = {}
        self._lock = threading.RLock()  # Reentrant lock for thread safety
        logger.info("Initialized InMemorySessionStorage (thread-safe)")

    def get_session(self, session_id: str) -> Optional[SessionData]:
        """Thread-safe session retrieval"""
        with self._lock:
            return self._sessions.get(session_id)

    def save_session(self, session_data: SessionData):
        """Thread-safe session save"""
        with self._lock:
            self._sessions[session_data.session_id] = session_data

    def delete_session(self, session_id: str):
        """Thread-safe session deletion"""
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.debug(f"Deleted session: {session_id}")

    def get_all_session_ids(self) -> List[str]:
        """Thread-safe retrieval of all session IDs"""
        with self._lock:
            return list(self._sessions.keys())

    def get_session_count(self) -> int:
        """Thread-safe session count"""
        with self._lock:
            return len(self._sessions)


class SessionManager:
    """Manages chat sessions and conversation history

    Features:
    - Thread-safe operations
    - Configurable limits and timeouts
    - Pluggable storage backends
    - Automatic cleanup of expired sessions
    - Session capacity management
    """

    def __init__(self, storage: SessionStorage, config: SessionConfig):
        """Initialize session manager with dependency injection

        Args:
            storage: Storage backend for sessions
            config: Configuration settings
        """
        self.storage = storage
        self.config = config
        self._total_messages = 0  # Cached counter for efficiency
        self._lock = threading.RLock()  # For operations spanning multiple storage calls

        logger.info(
            f"SessionManager initialized: "
            f"max_messages={config.max_messages_per_session}, "
            f"timeout={config.session_timeout_minutes}min, "
            f"max_sessions={config.max_total_sessions}"
        )

    def get_messages(self, session_id: str) -> List[BaseMessage]:
        """Get message history for a session (creates session if needed)

        Args:
            session_id: Unique session identifier

        Returns:
            List of LangChain message objects

        Raises:
            ValueError: If session_id is invalid
            RuntimeError: If session limit is reached
        """
        # Validate session ID
        if not session_id or not isinstance(session_id, str):
            raise ValueError(f"Invalid session_id: {session_id}")

        if len(session_id) > 100:  # Prevent abuse
            raise ValueError("session_id too long (max 100 characters)")

        # Get or create session
        session_data = self.storage.get_session(session_id)

        if session_data is None:
            # Check capacity before creating new session
            if self.storage.get_session_count() >= self.config.max_total_sessions:
                # Try cleanup first
                self.cleanup_expired_sessions()
                # Check again
                if self.storage.get_session_count() >= self.config.max_total_sessions:
                    raise RuntimeError(
                        f"Session limit reached ({self.config.max_total_sessions}). "
                        "Try again later or clear old sessions."
                    )

            # Create new session
            logger.info(f"Creating new session: {session_id}")
            session_data = SessionData(session_id=session_id)
            self.storage.save_session(session_data)
        else:
            # Update last accessed time
            session_data.last_accessed = datetime.utcnow()
            self.storage.save_session(session_data)

        return session_data.messages

    def add_message(self, session_id: str, role: str, content: str):
        """Add a message to session history

        Args:
            session_id: Session identifier
            role: 'user' or 'assistant'
            content: Message content

        Raises:
            ValueError: If role is invalid or session_id is invalid
        """
        # Validate role
        if role not in ["user", "assistant"]:
            raise ValueError(f"Invalid role: {role}. Must be 'user' or 'assistant'")

        # Validate content
        if not content or not isinstance(content, str):
            raise ValueError("Message content must be a non-empty string")

        # Get session (will create if needed)
        session_data = self.storage.get_session(session_id)
        if session_data is None:
            # Trigger session creation via get_messages
            _ = self.get_messages(session_id)
            session_data = self.storage.get_session(session_id)

        # Create appropriate message type
        if role == "user":
            message = HumanMessage(content=content)
        else:  # role == "assistant"
            message = AIMessage(content=content)

        # Add message
        session_data.messages.append(message)
        session_data.message_count += 1
        session_data.last_accessed = datetime.utcnow()

        # Trim messages if exceeding limit
        if len(session_data.messages) > self.config.max_messages_per_session:
            # Keep most recent messages
            excess = len(session_data.messages) - self.config.max_messages_per_session
            session_data.messages = session_data.messages[excess:]
            logger.debug(
                f"Trimmed session {session_id} to {self.config.max_messages_per_session} messages "
                f"(removed {excess} oldest messages)"
            )

        # Save updated session
        self.storage.save_session(session_data)

        with self._lock:
            self._total_messages += 1

        logger.debug(f"Added {role} message to session {session_id} (total: {session_data.message_count})")

    def clear_session(self, session_id: str):
        """Delete a specific session

        Args:
            session_id: Session identifier
        """
        session_data = self.storage.get_session(session_id)
        if session_data:
            with self._lock:
                self._total_messages -= session_data.message_count
            logger.info(f"Clearing session: {session_id}")
            self.storage.delete_session(session_id)
        else:
            logger.debug(f"Session not found for clearing: {session_id}")

    def cleanup_expired_sessions(self) -> int:
        """Remove expired sessions to free memory

        Returns:
            Number of sessions cleaned up
        """
        now = datetime.utcnow()
        timeout = timedelta(minutes=self.config.session_timeout_minutes)
        expired_ids = []

        # Find expired sessions
        for session_id in self.storage.get_all_session_ids():
            session_data = self.storage.get_session(session_id)
            if session_data and (now - session_data.last_accessed) > timeout:
                expired_ids.append(session_id)

        # Delete expired sessions
        for session_id in expired_ids:
            session_data = self.storage.get_session(session_id)
            if session_data:
                with self._lock:
                    self._total_messages -= session_data.message_count
                logger.info(
                    f"Expiring session: {session_id} "
                    f"(last accessed: {session_data.last_accessed.isoformat()})"
                )
                self.storage.delete_session(session_id)

        if expired_ids:
            logger.info(f"Cleaned up {len(expired_ids)} expired sessions")

        return len(expired_ids)

    def get_session_stats(self) -> dict:
        """Get statistics about active sessions

        Returns:
            Dictionary with comprehensive session statistics
        """
        session_ids = self.storage.get_all_session_ids()
        sessions_info = []

        total_messages_recalc = 0
        for session_id in session_ids:
            session_data = self.storage.get_session(session_id)
            if session_data:
                total_messages_recalc += session_data.message_count
                sessions_info.append({
                    "session_id": session_id,
                    "message_count": session_data.message_count,
                    "created_at": session_data.created_at.isoformat(),
                    "last_accessed": session_data.last_accessed.isoformat()
                })

        return {
            "active_sessions": len(session_ids),
            "total_messages": total_messages_recalc,
            "max_sessions": self.config.max_total_sessions,
            "max_messages_per_session": self.config.max_messages_per_session,
            "session_timeout_minutes": self.config.session_timeout_minutes,
            "sessions": sessions_info
        }


# Singleton instance (can be replaced with FastAPI Depends for better DI)
_session_manager: Optional[SessionManager] = None
_session_manager_lock = threading.Lock()


def get_session_manager(
    storage: Optional[SessionStorage] = None,
    config: Optional[SessionConfig] = None
) -> SessionManager:
    """Get or create the session manager instance

    Args:
        storage: Optional storage backend (for DI/testing)
        config: Optional configuration (for DI/testing)

    Returns:
        SessionManager instance
    """
    global _session_manager

    # If dependencies provided, create new instance (for testing/DI)
    if storage is not None or config is not None:
        return SessionManager(
            storage=storage or InMemorySessionStorage(),
            config=config or SessionConfig()
        )

    # Thread-safe singleton initialization
    if _session_manager is None:
        with _session_manager_lock:
            if _session_manager is None:  # Double-check locking
                _session_manager = SessionManager(
                    storage=InMemorySessionStorage(),
                    config=SessionConfig()
                )

    return _session_manager
