"""Session management routes for the chatbot module."""

from fastapi import APIRouter, HTTPException, Depends
from ..auth.models import User
from ..common.dependencies import get_current_firm_user
from .database import (
    list_sessions as db_list_sessions,
    create_session,
    create_or_update_chat_thread
)

router = APIRouter()


@router.get("/sessions")
async def list_sessions(current_user: User = Depends(get_current_firm_user)):
    """List all sessions for the current firm."""
    try:
        sessions = await db_list_sessions(firm_id=current_user.firm_id)
        return [
            {
                "id": s.id,
                "user_id": s.user_id,
                "created_at": s.created_at,
                "updated_at": s.updated_at,
                "is_active": s.is_active
            } for s in sessions
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list sessions: {str(e)}")


@router.post("/sessions")
async def create_new_session(current_user: User = Depends(get_current_firm_user)):
    """Create a new session for the current user."""
    try:
        sess = await create_session(user_id=current_user.id, firm_id=current_user.firm_id)
        # Create a default chat thread for this session
        thread = await create_or_update_chat_thread(sess.id)
        return {
            "id": sess.id, 
            "user_id": sess.user_id, 
            "created_at": sess.created_at, 
            "thread_id": thread.id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")


@router.get("/sessions/{session_id}/threads")
async def list_session_threads(session_id: str, current_user: User = Depends(get_current_firm_user)):
    """List all threads for a specific session."""
    try:
        from .database import list_threads as db_list_threads
        threads = await db_list_threads(session_id)
        return [
            {
                "id": t.id,
                "session_id": t.session_id,
                "openai_thread_id": t.openai_thread_id,
                "title": t.title,
                "summary": t.summary,
                "case_number": t.case_number,
                "created_at": t.created_at,
                "updated_at": t.updated_at,
                "is_active": t.is_active
            } for t in threads
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list threads: {str(e)}")

