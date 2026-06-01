"""Chat routes for the chatbot module."""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
import asyncio
import os
from ..schema import ChatMessage, ChatResponse
from ..auth.models import User
from ..common.dependencies import get_current_firm_user
from .service import process_chat_endpoint
from .parallel_reviewer import run_parallel_bankruptcy_review_async
from ..billing.service import report_usage_event
from .database import (
    get_session,
    get_session_pdfs,
    create_session_with_id,
    create_or_update_chat_thread,
    save_chat_message,
    save_review_results,
    update_thread_metadata as db_update_thread_metadata,
    list_messages as db_list_messages,
    log_user_action,
)

router = APIRouter()

# Global dictionary to store RegularChatAgent instances per session
active_threads = {}

# Tracks in-progress analyses so they survive client disconnects
# session_id -> {"queue": asyncio.Queue, "task": asyncio.Task}
_active_analyses: dict = {}

# PDF storage directory
PDF_STORAGE_DIR = "uploads"
os.makedirs(PDF_STORAGE_DIR, exist_ok=True)


@router.post("/chat", response_model=ChatResponse)
async def chat_with_assistant(chat_data: ChatMessage, current_user: User = Depends(get_current_firm_user)):
    """
    Send a message to the AI Petition Reviewer assistant or handle bankruptcy review requests
    """
    try:
        session_id = chat_data.session_id
        user_message = chat_data.message
        
        # Try to get session, but don't require it for basic chat
        session = await get_session(session_id)
        current_pdf_path = None
        
        if session:
            # Session exists, get PDFs and chat thread
            chat_thread = await create_or_update_chat_thread(session_id)
            session_pdfs = await get_session_pdfs(session_id)
            if session_pdfs:
                current_pdf_path = session_pdfs[0].file_path
            else:
                current_pdf_path = None
        else:
            # If chat arrives with an unknown session, create it so we can persist
            session = await create_session_with_id(session_id, user_id=current_user.id, firm_id=current_user.firm_id)
            chat_thread = await create_or_update_chat_thread(session_id)
            current_pdf_path = None
        
        # Save user message if we have a thread
        if session:
            await save_chat_message(thread_id=chat_thread.id, role="user", content=user_message)

        # Load prior messages for agent context (exclude the one just saved)
        prior_messages = await db_list_messages(chat_thread.id)
        chat_history = [
            {"role": m.role, "content": m.content}
            for m in prior_messages[:-1]
        ] if prior_messages else []

        # Process the chat request using service function
        response = await process_chat_endpoint(
            user_message,
            session_id,
            current_pdf_path,
            active_threads,
            chat_history=chat_history,
        )
        
        # Save assistant message if we have a thread
        if session and isinstance(response, ChatResponse):
            await save_chat_message(thread_id=chat_thread.id, role="assistant", content=response.response)

        await log_user_action(
            action="chat_message",
            user_id=current_user.id,
            session_id=session_id,
            firm_id=current_user.firm_id,
            metadata={"channel": "chat"},
        )
        asyncio.create_task(report_usage_event(current_user.firm_id, "chat"))

        return response

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in chat endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")


@router.post("/chat-stream")
async def chat_stream_regular(chat_data: ChatMessage, current_user: User = Depends(get_current_firm_user)):
    """
    Stream regular chat responses with token-level streaming via Server-Sent Events (SSE).
    """
    try:
        session_id = chat_data.session_id
        user_message = chat_data.message
        
        # Get or create session
        session = await get_session(session_id)
        if not session:
            session = await create_session_with_id(session_id, user_id=current_user.id, firm_id=current_user.firm_id)
        
        chat_thread = await create_or_update_chat_thread(session_id)

        # Save user message
        await save_chat_message(thread_id=chat_thread.id, role="user", content=user_message)

        # Load prior messages for agent context (exclude the one just saved)
        prior_messages = await db_list_messages(chat_thread.id)
        chat_history = [
            {"role": m.role, "content": m.content}
            for m in prior_messages[:-1]
        ] if prior_messages else []

        # Get or create regular chat agent
        from .agent import RegularChatAgent
        if session_id not in active_threads:
            active_threads[session_id] = RegularChatAgent(session_id=session_id)
        agent = active_threads[session_id]

        async def event_generator():
            import json
            queue: asyncio.Queue = asyncio.Queue()

            def progress(event: dict):
                try:
                    queue.put_nowait(event)
                except Exception:
                    pass

            loop = asyncio.get_event_loop()

            async def run_chat():
                try:
                    # Call the streaming version of chat
                    result = await loop.run_in_executor(
                        None,
                        lambda: agent.chat(user_message, session_id, progress_callback=progress, chat_history=chat_history)
                    )
                    
                    # Save final response to database
                    if result.get("status") == "completed":
                        await save_chat_message(thread_id=chat_thread.id, role="assistant", content=result.get("response", ""))
                    
                    await queue.put({"stage": "final", "result": result})
                    
                except Exception as e:
                    await queue.put({"stage": "error", "message": str(e)})

            chat_task = asyncio.create_task(run_chat())

            try:
                while True:
                    event = await queue.get()
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("stage") in ("final", "error"):
                        break
            finally:
                try:
                    chat_task.cancel()
                except Exception:
                    pass

        await log_user_action(
            action="chat_message",
            user_id=current_user.id,
            session_id=session_id,
            firm_id=current_user.firm_id,
            metadata={"channel": "chat_stream"},
        )
        asyncio.create_task(report_usage_event(current_user.firm_id, "chat"))

        headers = {
            "Cache-Control": "no-cache, no-transform",
            "Pragma": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }

        return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)

    except Exception as e:
        print(f"Error in chat-stream: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Chat stream error: {str(e)}")


@router.get("/chat-stream/{session_id}")
async def chat_stream_master_review(session_id: str, current_user: User = Depends(get_current_firm_user)):
    """
    Stream progress updates for Master Agent Analysis via Server-Sent Events (SSE).
    The analysis runs as a persistent background task so it continues even if the
    client disconnects and reconnects mid-analysis.
    """
    try:
        import json

        session = await get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found or inactive")
        if session.firm_id != current_user.firm_id:
            raise HTTPException(status_code=403, detail="Access denied")

        session_pdfs = await get_session_pdfs(session_id)
        if not session_pdfs:
            raise HTTPException(status_code=400, detail="No uploaded PDFs found for session")

        current_pdf_path = session_pdfs[0].file_path

        from .agent import RegularChatAgent
        if session_id not in active_threads:
            active_threads[session_id] = RegularChatAgent(session_id=session_id)
        regular_agent = active_threads[session_id]

        # Start analysis only if not already running for this session.
        # On reconnect we reuse the existing queue so buffered events are delivered.
        if session_id not in _active_analyses:
            queue: asyncio.Queue = asyncio.Queue()

            def progress(event: dict):
                try:
                    queue.put_nowait(event)
                except Exception:
                    pass

            async def wait_for_completion():
                try:
                    results = await run_parallel_bankruptcy_review_async(
                        current_pdf_path,
                        session_id=session_id,
                        progress_callback=progress,
                    )

                    # Persist results to database
                    try:
                        if results:
                            await save_review_results(session_id, current_pdf_path, results)

                        if not results:
                            response_text = "❌ Bankruptcy review failed to complete. Please check the PDF file and try again."
                        elif isinstance(results, dict) and results.get("is_skeleton"):
                            response_text = "It looks like this petition is a skeleton, we will give you a full review once the updated schedules are filed or inputted."
                        else:
                            response_text = "✅ Complete bankruptcy review completed!\n\n"
                            response_text += "📋 Schedule Reviews:\n"
                            try:
                                for schedule_name, review_data in (results.get("group_reviews") or {}).items():
                                    status = review_data.get("status", "unknown")
                                    if status == "completed":
                                        response_text += f"  ✓ {schedule_name}\n"
                                    else:
                                        response_text += f"  ✗ {schedule_name} ({status})\n"
                            except Exception:
                                pass

                            response_text += "\n🎯 Master Analysis:\n"
                            master_review = results.get("master_review", {}) or {}
                            if master_review.get("status") == "completed":
                                response_text += "  ✓ Master review completed\n"
                                master_text = master_review.get("master_review", "")
                                response_text += f"\n📝 Complete Master Review:\n\n{master_text}"
                            else:
                                response_text += f"  ✗ Master review failed: {master_review.get('error', 'Unknown error')}"

                            response_text += "\n\n📁 Results saved for further analysis."

                        chat_thread_persist = await create_or_update_chat_thread(session_id)
                        try:
                            if not (chat_thread_persist.title and chat_thread_persist.title.strip()):
                                await db_update_thread_metadata(chat_thread_persist.id, title="Review Bankruptcy Petition")
                        except Exception:
                            pass

                        await save_chat_message(thread_id=chat_thread_persist.id, role="user", content="Review Bankruptcy Petition")
                        await save_chat_message(thread_id=chat_thread_persist.id, role="assistant", content=response_text)
                    except Exception as e:
                        try:
                            queue.put_nowait({"stage": "warn", "message": f"Persistence warning: {str(e)}"})
                        except Exception:
                            pass

                    queue.put_nowait({"stage": "final", "results": results})
                except Exception as e:
                    queue.put_nowait({"stage": "error", "message": str(e)})
                finally:
                    # Remove from tracking once done so a future call starts fresh
                    _active_analyses.pop(session_id, None)

            completion_task = asyncio.create_task(wait_for_completion())
            _active_analyses[session_id] = {"queue": queue, "task": completion_task}

        queue = _active_analyses[session_id]["queue"]

        async def event_generator():
            async def heartbeat():
                try:
                    while True:
                        await asyncio.sleep(10)
                        queue.put_nowait({"stage": "heartbeat", "ts": int(asyncio.get_event_loop().time() * 1000)})
                except asyncio.CancelledError:
                    pass

            heartbeat_task = asyncio.create_task(heartbeat())

            try:
                while True:
                    event = await queue.get()
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("stage") in ("final", "error"):
                        break
            finally:
                # Only stop the heartbeat — never cancel the analysis task
                heartbeat_task.cancel()

        headers = {
            "Cache-Control": "no-cache, no-transform",
            "Pragma": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }

        return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in chat-stream: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Stream error: {str(e)}")

