import logging
from fastapi import APIRouter, Depends
from app.services.session import get_session_manager, SessionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["sessions"])

# Dependency function for FastAPI Depends()
def get_session_manager_dep() -> SessionManager:
    """Dependency to get session manager"""
    return get_session_manager()


@router.delete("/session/{session_id}")
async def clear_session(
    session_id: str,
    session_manager: SessionManager = Depends(get_session_manager_dep)
):
    """Clear a specific chat session
    
    Args:
        session_id: Session ID to clear
        session_manager: Session manager (injected)
        
    Returns:
        Success message
    """
    session_manager.clear_session(session_id)
    logger.info(f"Cleared session: {session_id}")
    return {
        "status": "success",
        "message": f"Session {session_id} cleared",
        "session_id": session_id
    }


@router.get("/sessions/stats")
async def get_session_stats(
    session_manager: SessionManager = Depends(get_session_manager_dep)
):
    """Get statistics about active sessions (admin/debug endpoint)
    
    Args:
        session_manager: Session manager (injected)
    
    Returns:
        Session statistics including active sessions and message counts
    """
    stats = session_manager.get_session_stats()
    return stats

