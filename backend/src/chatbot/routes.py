"""Consolidated routes for chatbot functionality."""

from fastapi import APIRouter
from .routes_chat import router as chat_router
from .routes_sessions import router as sessions_router
from .routes_threads import router as threads_router
from .routes_pdf import router as pdf_router

# Main router that combines all chatbot-related routes
router = APIRouter(tags=["Chatbot"])

# Include sub-routers
router.include_router(chat_router)
router.include_router(sessions_router)
router.include_router(threads_router)
router.include_router(pdf_router)

