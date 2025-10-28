import logging
from typing import Dict, List
from datetime import datetime, timedelta
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

logger = logging.getLogger(__name__)

# Maximum number of messages to keep in memory (to prevent unlimited growth)
MAX_MESSAGES_PER_SESSION = 50


class SessionManager:
    """Manages chat sessions and conversation history using LangChain v1 patterns"""
    
    def __init__(self, session_timeout_minutes: int = 60):
        """Initialize session manager
        
        Args:
            session_timeout_minutes: Minutes before session expires (default: 60)
        """
        self._sessions: Dict[str, Dict] = {}
        self._session_timeout = timedelta(minutes=session_timeout_minutes)
        logger.info(f"SessionManager initialized with {session_timeout_minutes}min timeout")
    
    def get_messages(self, session_id: str) -> List[BaseMessage]:
        """Get or create message history for a session
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            List of messages (LangChain v1 message objects)
        """
        # Clean up expired sessions first
        self._cleanup_expired_sessions()
        
        # Create new session if doesn't exist
        if session_id not in self._sessions:
            logger.info(f"Creating new session: {session_id}")
            self._sessions[session_id] = {
                "messages": [],
                "created_at": datetime.utcnow(),
                "last_accessed": datetime.utcnow(),
                "message_count": 0
            }
        else:
            # Update last accessed time
            self._sessions[session_id]["last_accessed"] = datetime.utcnow()
        
        return self._sessions[session_id]["messages"]
    
    def add_message(self, session_id: str, role: str, content: str):
        """Add a message to session history
        
        Args:
            session_id: Session identifier
            role: 'user' or 'assistant'
            content: Message content
        """
        messages = self.get_messages(session_id)
        
        # Create appropriate message type
        if role == "user":
            message = HumanMessage(content=content)
        elif role == "assistant":
            message = AIMessage(content=content)
        else:
            logger.warning(f"Unknown role: {role}")
            return
        
        # Add message to session
        messages.append(message)
        self._sessions[session_id]["message_count"] += 1
        
        # Trim messages if exceeding max limit
        if len(messages) > MAX_MESSAGES_PER_SESSION:
            # Keep only the most recent messages
            self._sessions[session_id]["messages"] = messages[-MAX_MESSAGES_PER_SESSION:]
            logger.debug(f"Trimmed session {session_id} to {MAX_MESSAGES_PER_SESSION} messages")
        
        logger.debug(f"Added {role} message to session {session_id}")
    
    def get_chat_history(self, session_id: str) -> list:
        """Get formatted chat history for a session
        
        Args:
            session_id: Session identifier
            
        Returns:
            List of message dicts with role and content
        """
        if session_id not in self._sessions:
            return []
        
        messages = self._sessions[session_id]["messages"]
        
        return [
            {
                "role": "user" if isinstance(msg, HumanMessage) else "assistant",
                "content": msg.content
            }
            for msg in messages
        ]
    
    def clear_session(self, session_id: str):
        """Clear a specific session
        
        Args:
            session_id: Session identifier
        """
        if session_id in self._sessions:
            logger.info(f"Clearing session: {session_id}")
            del self._sessions[session_id]
    
    def _cleanup_expired_sessions(self):
        """Remove expired sessions to free memory"""
        now = datetime.utcnow()
        expired = []
        
        for session_id, data in self._sessions.items():
            if now - data["last_accessed"] > self._session_timeout:
                expired.append(session_id)
        
        for session_id in expired:
            logger.info(f"Expiring session: {session_id} (last accessed: {self._sessions[session_id]['last_accessed']})")
            del self._sessions[session_id]
        
        if expired:
            logger.info(f"Cleaned up {len(expired)} expired sessions")
    
    def get_session_stats(self) -> dict:
        """Get statistics about active sessions
        
        Returns:
            Dict with session stats
        """
        self._cleanup_expired_sessions()
        
        return {
            "active_sessions": len(self._sessions),
            "total_messages": sum(s["message_count"] for s in self._sessions.values()),
            "sessions": [
                {
                    "session_id": sid,
                    "message_count": data["message_count"],
                    "created_at": data["created_at"].isoformat(),
                    "last_accessed": data["last_accessed"].isoformat()
                }
                for sid, data in self._sessions.items()
            ]
        }


# Singleton instance
_session_manager = None


def get_session_manager() -> SessionManager:
    """Get or create the session manager singleton"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager(session_timeout_minutes=60)
    return _session_manager

