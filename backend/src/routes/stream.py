"""Stream routes for objection-sustain upload workflow."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import asyncio
import json
import time
from ..chatbot.database import get_session
from ..gmail.service import generate_payload_objection_sustain_for_session_gmail


router = APIRouter(tags=["Motion Drafter - Streams"])


@router.get("/motion-objection-sustain-stream/{session_id}")
async def motion_objection_sustain_progress_stream(session_id: str):
    """
    Stream progress updates for Motion Objection Sustain generation via SSE (with upload version).
    This endpoint directly extracts fields from the uploaded objection PDF.
    """
    try:
        session = await get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found or inactive")

        async def event_generator():
            start_time = time.time()
            messages = [
                "Sorry, something went wrong with the auto drafting",
                "Saving hours. Drafting in minutes.",
                "Every motion built from verified filings. No guesswork.",
                "From docket to draft—without missing a detail.",
                "The paperwork part just got smarter.",
                "Review-ready motions are on the way."
            ]
            message_rotation_interval = 10

            def get_current_message():
                elapsed = time.time() - start_time
                index = int(elapsed // message_rotation_interval) % 5 + 1
                return {"message": messages[index], "message_index": index}

            work_complete = False
            error_occurred = False
            final_result = None

            async def do_work():
                nonlocal work_complete, error_occurred, final_result
                try:

                    loop = asyncio.get_event_loop()
                    payload_result = await loop.run_in_executor(
                        None,
                        lambda: generate_payload_objection_sustain_for_session_gmail(session_id)
                    )

                    if payload_result.get("status") != "success":
                        msg = payload_result.get("error") or "Failed to generate objection sustain payload"
                        raise RuntimeError(msg)

                    final_result = {
                        "status": "success",
                        "payload": payload_result.get("payload"),
                        "message": "Generated objection sustain payload successfully from objection PDF.",
                    }
                    work_complete = True
                except Exception as e:
                    error_occurred = True
                    work_complete = True
                    raise

            work_task = asyncio.create_task(do_work())
            try:
                while not work_complete:
                    msg_data = get_current_message()
                    yield f'data: {json.dumps({"stage":"info","message":msg_data["message"],"message_index":msg_data["message_index"]})}\n\n'
                    await asyncio.sleep(2)
                if error_occurred:
                    yield f'data: {json.dumps({"stage":"error","message":messages[0],"message_index":0})}\n\n'
                else:
                    final_event = {"stage": "final", "results": final_result}
                    yield f"data: {json.dumps(final_event)}\n\n"
            except Exception as e:
                work_task.cancel()
                yield f'data: {json.dumps({"stage":"error","message":messages[0],"message_index":0})}\n\n'
                return

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
        print(f"Error in motion-objection-sustain-stream: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Stream error: {str(e)}")
