from .page_splitter import process_pdf_and_get_groups
from .parallel_reviewer import run_parallel_bankruptcy_review_async
import asyncio
import re
import os
import shutil
from ..config import settings
from ..schema import ChatResponse, PDFUploadResponse
import time

# Import database functions for review caching
from .database import get_review_results, save_review_results
from .vectorestore import process_uploaded_file, clear_collection

# Note: In-memory storage removed in favor of database storage
# Session memory and review cache are now handled by database

def _normalize_command(text: str) -> str:
    """Normalize user text for definitive command matching (case/whitespace insensitive)."""
    try:
        # Lowercase, trim, then collapse internal whitespace to single spaces
        lowered = (text or "").strip().lower()
        return re.sub(r"\s+", " ", lowered).strip()
    except Exception:
        return (text or "").strip().lower()

def detect_definitive_routing_command(message: str) -> tuple[str, str]:
    """
    Detect definitive routing commands to avoid conflicts with regular chat.

    Returns a tuple of (route_type, route_value):
      - ("master", "") when message is the definitive master review command
      - ("schedule", canonical_schedule_key) when message matches a definitive schedule command
      - ("", "") when no definitive command is detected

    Supported commands (case-insensitive, whitespace-insensitive):
      Master: "Review Bankruptcy Petition"
      Schedules:
        - "Schedule A/B"
        - "Schedule C/D"
        - "Schedule E/F"
        - "Schedule G/H"
        - "Schedule I/J/CMI"
        - "SOFA" (or "Statement of Financial Affairs")
    """
    normalized = _normalize_command(message)

    if normalized == "review bankruptcy petition":
        return "master", ""

    # Map normalized input to canonical schedule keys used downstream
    schedule_aliases = {
        "schedule a/b": "schedule a/b",
        "schedule c/d": "schedule c/d",
        "schedule e/f": "schedule e/f",
        "schedule g/h": "schedule g/h",
        "schedule i/j/cmi": "schedule i/j/cmi",
        "sofa": "sofa",
        "statement of financial affairs": "sofa",
    }

    if normalized in schedule_aliases:
        return "schedule", schedule_aliases[normalized]

    return "", ""

# Removed fuzzy schedule detection in favor of definitive routing commands

def extract_schedule_details(schedule_name: str, review_results: dict) -> str:
    """Extract details for a specific schedule from review results."""
    if not review_results or "group_reviews" not in review_results:
        return "No review results available."
    
    group_reviews = review_results["group_reviews"]
    
    # Map schedule names to actual group names in results
    schedule_mapping = {
        # Existing fine-grained keys
        "schedule a": "Schedule A/B",
        "schedule b": "Schedule A/B", 
        "schedule c": "Schedule C & D",
        "schedule d": "Schedule C & D",
        "schedule e": "Schedule E/F",
        "schedule f": "Schedule E/F",
        "schedule g": "Schedule G & H",
        "schedule h": "Schedule G & H",
        "schedule i": "Schedule I, J & Summary",
        "schedule j": "Schedule I, J & Summary",
        "sofa": "Statement of Financial Affairs",
        "summary": "Schedule I, J & Summary",
        # Definitive consolidated keys
        "schedule a/b": "Schedule A/B",
        "schedule c/d": "Schedule C & D",
        "schedule e/f": "Schedule E/F",
        "schedule g/h": "Schedule G & H",
        "schedule i/j/cmi": "Schedule I, J & Summary",
    }
    
    target_group = schedule_mapping.get(schedule_name.lower())
    if not target_group or target_group not in group_reviews:
        return f"Schedule {schedule_name} not found in review results."
    
    review_data = group_reviews[target_group]
    if review_data.get("status") == "completed":
        return review_data.get("review", "Review content not available.")
    else:
        return f"Schedule {schedule_name} review failed: {review_data.get('error', 'Unknown error')}"


def run_bankruptcy_review(pdf_path: str, regular_agent=None, progress_callback=None, session_id=None):
    """
    Run a complete bankruptcy review using the page splitter and agents.
    
    Args:
        pdf_path: Path to the PDF file
        regular_agent: Optional RegularChatAgent instance
        progress_callback: Optional callback function for progress updates
        
    Returns:
        Dictionary containing review results for all groups, or {"is_skeleton": True} if no groups found
    """
    try:
        # Check if PDF exists
        if not os.path.exists(pdf_path):
            print(f"ERROR: PDF file not found: {pdf_path}")
            return None
        
        reviewer_session_id = session_id
        if regular_agent and hasattr(regular_agent, "session_id"):
            reviewer_session_id = regular_agent.session_id

        return asyncio.run(
            run_parallel_bankruptcy_review_async(
                pdf_path,
                session_id=reviewer_session_id or "bankruptcy_review_default",
                progress_callback=progress_callback,
            )
        )
        
    except Exception as e:
        print(f"Error running bankruptcy review: {e}")
        import traceback
        traceback.print_exc()
        return None


def run_complete_bankruptcy_review(pdf_path: str, regular_agent=None, progress_callback=None, session_id=None):
    """
    Run a complete bankruptcy review including individual schedule reviews and master analysis.
    
    Args:
        pdf_path: Path to the PDF file
        regular_agent: Optional RegularChatAgent instance
        progress_callback: Optional callback function for progress updates
        session_id: Session ID to pass to MasterReviewAgent
        
    Returns:
        Dictionary containing:
        - group_reviews: Individual reviews for each bankruptcy schedule
        - master_review: Master analysis using OpenAI assistant
    """
    try:
        if callable(progress_callback):
            try:
                progress_callback({"stage": "init", "message": "Starting bankruptcy review..."})
            except Exception:
                pass
        
        reviewer_session_id = session_id
        if regular_agent and hasattr(regular_agent, "session_id"):
            reviewer_session_id = regular_agent.session_id

        return asyncio.run(
            run_parallel_bankruptcy_review_async(
                pdf_path,
                session_id=reviewer_session_id or "master_review_default",
                progress_callback=progress_callback,
            )
        )
        
    except Exception as e:
        print(f"Error running complete bankruptcy review: {e}")
        return None


def detect_bankruptcy_review_request(message: str, current_pdf_path: str) -> tuple[bool, str]:
    """
    Detect if the message is requesting a bankruptcy review.
    
    Args:
        message: User's message
        current_pdf_path: Path to the currently uploaded PDF
        
    Returns:
        Tuple of (is_review_request, pdf_path)
    """
    # Use definitive command only to avoid conflicts with regular chat
    normalized = _normalize_command(message)
    is_review_request = normalized == "review bankruptcy petition"
    
    if not is_review_request:
        return False, ""
    
    # Use the currently uploaded PDF if available, otherwise return error
    if current_pdf_path and os.path.exists(current_pdf_path):
        pdf_path = current_pdf_path
        return True, pdf_path
    else:
        # No PDF available - return error
        return False, ""


async def process_bankruptcy_review_request(pdf_path: str, session_id: str, regular_agent=None) -> ChatResponse:
    """
    Process a bankruptcy review request and return formatted response.
    
    Args:
        pdf_path: Path to the PDF file to review
        session_id: User's session ID
        
    Returns:
        ChatResponse with review results
    """
    try:
        # Check if we have cached review results first
        cached_results = await get_review_results(session_id, pdf_path)
        
        if cached_results:
            results = cached_results
        else:
            # Run complete bankruptcy review through the Claude reviewer path
            results = await run_parallel_bankruptcy_review_async(
                pdf_path,
                session_id=session_id,
            )
            
            if results:
                # Cache the results for future use
                await save_review_results(session_id, pdf_path, results)
        
        if results:
            # Check if this is a skeleton petition
            if isinstance(results, dict) and results.get("is_skeleton"):
                response_text = "It looks like this petition is a skeleton, we will give you a full review once the updated schedules are filed or inputted."
            else:
                response_text = "✅ Complete bankruptcy review completed!\n\n"
                response_text += "📋 Schedule Reviews:\n"
                for schedule_name, review_data in results["group_reviews"].items():
                    status = review_data.get("status", "unknown")
                    if status == "completed":
                        response_text += f"  ✓ {schedule_name}\n"
                    else:
                        response_text += f"  ✗ {schedule_name} ({status})\n"
                
                response_text += "\n🎯 Master Analysis:\n"
                master_review = results.get("master_review", {})
                if master_review.get("status") == "completed":
                    response_text += "  ✓ Master review completed\n"
                    # Include a preview of the master review with clean formatting
                    master_text = master_review.get("master_review", "")
                    # Clean up markdown and formatting
                    clean_master_text = master_text.replace("###", "").replace("**", "").replace("---", "")
                    
                    # Show the complete master review
                    response_text += f"\n📝 Complete Master Review:\n\n{clean_master_text}"
                else:
                    response_text += f"  ✗ Master review failed: {master_review.get('error', 'Unknown error')}"
                
                response_text += f"\n\n📁 Results saved for further analysis."
        else:
            response_text = "❌ Bankruptcy review failed to complete. Please check the PDF file and try again."
        
        # Create a simple thread ID for review responses
        thread_id = f"review_{session_id}_{int(time.time())}"
        
        response = ChatResponse(
            response=response_text,
            session_id=session_id,
            thread_id=thread_id
        )
        
        return response
        
    except Exception as e:
        print(f"Exception during bankruptcy review: {str(e)}")
        import traceback
        traceback.print_exc()
        
        error_response = f"❌ Error during bankruptcy review: {str(e)}"
        thread_id = f"error_{session_id}_{int(time.time())}"
        
        return ChatResponse(
            response=error_response,
            session_id=session_id,
            thread_id=thread_id
        )


def process_chat_request(user_message: str, session_id: str, active_threads: dict, chat_history: list = None) -> ChatResponse:
    """
    Process a regular chat request using the RegularChatAgent with tools access.

    Args:
        user_message: User's message
        session_id: User's session ID
        active_threads: Dictionary of active chat threads (kept for compatibility)
        chat_history: Prior messages from DB to inject when no MemorySaver checkpoint exists.
    Returns:
        ChatResponse with agent's response
    """
    try:
        # Import RegularChatAgent here to avoid circular imports
        from .agent import RegularChatAgent

        # Use active_threads to store RegularChatAgent instances per session
        # This maintains conversational context across messages via MemorySaver
        if session_id not in active_threads:
            # Create new chat agent for this session, pass session_id so tools are session-scoped
            active_threads[session_id] = RegularChatAgent(session_id=session_id)

        # Get the existing chat agent for this session
        chat_agent = active_threads[session_id]

        # Process the message using the agent (MemorySaver handles context automatically)
        result = chat_agent.chat(user_message, session_id, chat_history=chat_history)
        
        if result.get("status") == "completed":
            response_text = result.get("response", "No response generated")
        else:
            response_text = f"Chat failed: {result.get('error', 'Unknown error')}"
        
        # Create a simple thread ID for chat responses
        thread_id = f"chat_{session_id}_{int(time.time())}"
        
        return ChatResponse(
            response=response_text,
            session_id=session_id,
            thread_id=thread_id
        )
        
    except Exception as e:
        print(f"Error in chat request: {str(e)}")
        import traceback
        traceback.print_exc()
        
        error_response = f"❌ Error during chat: {str(e)}"
        thread_id = f"error_{session_id}_{int(time.time())}"
        
        return ChatResponse(
            response=error_response,
            session_id=session_id,
            thread_id=thread_id
        )

def process_pdf_upload(file, collection_name: str, current_pdf_path: str, pdf_storage_dir: str, session_id: str = None) -> tuple[PDFUploadResponse, str]:
    """
    Process PDF upload and return response with new PDF path.
    
    Args:
        file: Uploaded file object
        collection_name: Collection name for the file
        current_pdf_path: Current PDF path (to be updated)
        pdf_storage_dir: Directory to store PDFs
        session_id: Optional session ID to update memory
        
    Returns:
        Tuple of (PDFUploadResponse, new_pdf_path)
    """
    try:
        # Validate file type
        if not file.filename.lower().endswith('.pdf'):
            raise ValueError("Only PDF files are allowed")
        
        # Validate file size (configurable limit)
        max_size_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        if file.size > max_size_bytes:
            raise ValueError(f"File too large. Maximum size is {settings.MAX_FILE_SIZE_MB}MB")
        
        # Clear any existing PDF and save the new one
        if current_pdf_path and os.path.exists(current_pdf_path):
            os.remove(current_pdf_path)
            print(f"Removed previous PDF: {current_pdf_path}")
        
        # Keep platform-uploaded filename scheme stable per session.
        filename = f"bankruptcy_petition_{session_id}.pdf" if session_id else "bankruptcy_petition_upload.pdf"
        file_path = os.path.join(pdf_storage_dir, filename)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Verify the file was saved successfully
        if not os.path.exists(file_path):
            raise ValueError("Failed to save uploaded file")

        # Test if the PDF can be processed by the page splitter
        try:
            test_groups = process_pdf_and_get_groups(file_path)
            available_for_review = len(test_groups) > 0
        except Exception as e:
            print(f"Warning: PDF processing test failed: {e}")
            available_for_review = False

        # Ingest the uploaded PDF into a session-scoped vectorstore collection
        try:
            if session_id:
                session_collection = f"bankruptcy_knowledge_{session_id}"
                # Overwrite behavior: clear the collection before ingesting
                try:
                    clear_result = clear_collection(session_collection)
                    if not clear_result.get("success"):
                        print(f"⚠️ Failed to clear collection {session_collection}: {clear_result.get('error')}")
                except Exception as e:
                    print(f"⚠️ Error clearing collection {session_collection}: {e}")
                ingest_result = process_uploaded_file(file_path, file_type="pdf", collection_name=session_collection)
                if not ingest_result.get("success"):
                    print(f"⚠️ Vectorstore ingest failed for {session_collection}: {ingest_result.get('error')}")
                else:
                    print(f"✅ Ingested uploaded PDF into collection {session_collection}: {ingest_result.get('stored_count')} chunks")
        except Exception as e:
            print(f"Error ingesting uploaded PDF into vectorstore: {e}")
        
        # Update session memory if session_id is provided
        if session_id:
            # Note: Session management is now handled by database
            # This function only handles file processing
            pass
        
        # PDF uploaded successfully
        
        response = PDFUploadResponse(
            message=f"PDF '{file.filename}' uploaded successfully and is ready for bankruptcy review",
            filename=filename,
            file_path=file_path,
            size=file.size,
            available_for_review=available_for_review
        )
        
        return response, file_path
        
    except Exception as e:
        print(f"Error in PDF upload: {str(e)}")
        raise e


async def process_chat_endpoint(user_message: str, session_id: str, current_pdf_path: str, active_threads: dict, chat_history: list = None) -> ChatResponse:
    """
    Process chat endpoint logic, handling both regular chat and bankruptcy review requests.

    Args:
        user_message: User's message
        session_id: User's session ID
        current_pdf_path: Path to the currently uploaded PDF
        active_threads: Dictionary of active chat threads
        chat_history: Prior messages from DB to inject for context continuity.
    Returns:
        ChatResponse with appropriate response
    """
    try:
        # First, check for definitive routing commands to avoid ambiguity
        route_type, route_value = detect_definitive_routing_command(user_message)
        if route_type == "master":
            if not (current_pdf_path and os.path.exists(current_pdf_path)):
                response_text = "❌ No PDF available for bankruptcy review.\n\nPlease upload a PDF first using the upload button above, then send: 'Review Bankruptcy Petition'."
                thread_id = f"error_{session_id}_{int(time.time())}"
                return ChatResponse(
                    response=response_text,
                    session_id=session_id,
                    thread_id=thread_id
                )
            # Run complete bankruptcy review via master flow using RegularChatAgent for shared memory
            # Ensure a RegularChatAgent exists for this session (reuse from active_threads)
            from .agent import RegularChatAgent
            if session_id not in active_threads:
                active_threads[session_id] = RegularChatAgent(session_id=session_id)
            regular_agent = active_threads[session_id]
            return await process_bankruptcy_review_request(current_pdf_path, session_id, regular_agent=regular_agent)

        if route_type == "schedule":
            if not (current_pdf_path and os.path.exists(current_pdf_path)):
                response_text = "❌ No PDF available.\n\nPlease upload a PDF first, then run Master Agent Analysis first to have schedule reviews."
                thread_id = f"error_{session_id}_{int(time.time())}"
                return ChatResponse(
                    response=response_text,
                    session_id=session_id,
                    thread_id=thread_id
                )

            cached_results = await get_review_results(session_id, current_pdf_path)
            if cached_results:
                schedule_details = extract_schedule_details(route_value, cached_results)
                response_text = f"📋 **{route_value.upper()} Details:**\n\n{schedule_details}"
                thread_id = f"schedule_{session_id}_{int(time.time())}"
                return ChatResponse(
                    response=response_text,
                    session_id=session_id,
                    thread_id=thread_id
                )
            else:
                response_text = "❌ No bankruptcy review results available.\n\nPlease run Master Agent Analysis first to generate schedule reviews."
                thread_id = f"error_{session_id}_{int(time.time())}"
                return ChatResponse(
                    response=response_text,
                    session_id=session_id,
                    thread_id=thread_id
                )

        # Fuzzy schedule routing removed; only definitive commands are supported now
        
        # Check if this is a bankruptcy review request
        is_review_request, pdf_path = detect_bankruptcy_review_request(user_message, current_pdf_path)
        
        if is_review_request:
            # Handle bankruptcy review request - always use complete review
            if not pdf_path:
                # No PDF available for review
                response_text = "❌ No PDF available for bankruptcy review.\n\n"
                response_text += "Please upload a PDF first using the upload button above, then try your review request again."
                
                # Create a simple thread ID for review responses
                thread_id = f"error_{session_id}_{int(time.time())}"
                
                response = ChatResponse(
                    response=response_text,
                    session_id=session_id,
                    thread_id=thread_id
                )
                
                return response
            
            # Process the bankruptcy review request with RegularChatAgent for shared memory
            from .agent import RegularChatAgent
            if session_id not in active_threads:
                active_threads[session_id] = RegularChatAgent(session_id=session_id)
            regular_agent = active_threads[session_id]
            response = await process_bankruptcy_review_request(pdf_path, session_id, regular_agent=regular_agent)
            
            return response
        
        # If not a bankruptcy review request, use the OpenAI assistant
        response = process_chat_request(user_message, session_id, active_threads, chat_history=chat_history)
        
        return response
        
    except Exception as e:
        print(f"Error in chat endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        raise e
