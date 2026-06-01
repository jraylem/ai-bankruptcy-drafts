"""Truly parallel bankruptcy petition reviewer using Claude Sonnet 4."""

import asyncio
from typing import Dict, Any, Optional, Callable
from anthropic import AsyncAnthropic

from .prompts import (
    AB_PROMPT, CD_PROMPT, IJ_CMI_PROMPT,
    SOFA_PROMPT, EF_PROMPT, GH_PROMPT,
    MASTER_AGENT_PROMPT
)
from .page_splitter import process_pdf_and_get_groups
from ..config import settings
from ..ai_models import CLAUDE_MODEL_STANDARD

SCHEDULE_PROMPTS = {
    "Schedule A/B": AB_PROMPT,
    "Schedule C & D": CD_PROMPT,
    "Schedule I, J & Summary": IJ_CMI_PROMPT,
    "Statement of Financial Affairs": SOFA_PROMPT,
    "Schedule E/F": EF_PROMPT,
    "Schedule G & H": GH_PROMPT,
}


def _progress_message_for_group(name: str, debtor_name: str = None) -> str:
    if name == "Schedule A/B":
        display_name = debtor_name or "the debtor"
        return f"Analyzing {display_name}'s petition for accuracy and completeness"
    if name == "Schedule C & D":
        return "Reviewing all schedules with detailed compliance checks"
    if name == "Schedule I, J & Summary":
        return "Calculating total asset value"
    if name == "Statement of Financial Affairs":
        return "Estimating potential liquidation outcomes"
    if name == "Schedule E/F":
        return "Consolidating notes and insights across all schedules"
    if name == "Schedule G & H":
        return ""
    return f"Analyzing {name}..."


class TrueParallelReviewer:
    """Runs all 6 schedules simultaneously for maximum speed using Claude."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    async def _review_schedule(self, name: str, text: str, prompt: str) -> Dict[str, Any]:
        """Review a single schedule asynchronously using Claude Sonnet 4.6."""
        try:
            collected = []
            async with self.client.messages.stream(
                model=CLAUDE_MODEL_STANDARD,
                max_tokens=8192,
                system=prompt,
                messages=[{"role": "user", "content": f"Review:\n\n{text}"}]
            ) as stream:
                async for token in stream.text_stream:
                    collected.append(token)

            return {
                "group_name": name,
                "review": "".join(collected),
                "status": "completed"
            }
        except Exception as e:
            return {
                "group_name": name,
                "review": f"Error: {e}",
                "status": "failed",
                "error": str(e)
            }

    async def _extract_client_info(self, progress_callback) -> tuple:
        """Extract debtor name and case number.

        Extraction order for case number:
        1. Database (already stored during upload)
        2. Direct PDF regex extraction (fast, reliable)
        3. AI agent via vectorstore (fallback)
        """
        from .agent import DebtorNameAgent, CaseNumberAgent
        from .database import get_session_chat_thread

        if progress_callback:
            progress_callback({"stage": "extract_client_info", "message": "Extracting client name and case number..."})

        loop = asyncio.get_event_loop()

        # Extract debtor name via AI agent
        debtor_agent = DebtorNameAgent(session_id=self.session_id)
        debtor_result = await loop.run_in_executor(None, debtor_agent.extract_debtor_name)
        debtor_name = debtor_result.get("debtor_name", "N/A") if debtor_result.get("status") == "completed" else "N/A"

        # 1. Check if case number is already in the database (from upload step)
        case_number = "N/A"
        try:
            chat_thread = await get_session_chat_thread(self.session_id)
            if chat_thread and chat_thread.case_number and chat_thread.case_number.strip() and chat_thread.case_number.strip() != "N/A":
                case_number = chat_thread.case_number.strip()
        except Exception:
            pass

        # 2. Direct PDF regex extraction fallback
        if case_number == "N/A":
            from ..courtdrive.service import _extract_case_number_from_pdf_directly
            direct_result = await loop.run_in_executor(
                None, _extract_case_number_from_pdf_directly, self.session_id
            )
            if direct_result.get("status") == "completed" and direct_result.get("case_number", "").strip() not in ("", "N/A"):
                case_number = direct_result["case_number"].strip()

        # 3. AI agent via vectorstore fallback
        if case_number == "N/A":
            case_agent = CaseNumberAgent(session_id=self.session_id)
            case_result = await loop.run_in_executor(None, case_agent.extract_case_number)
            case_number = case_result.get("case_number", "N/A") if case_result.get("status") == "completed" else "N/A"

        return debtor_name, case_number

    async def run_all_schedules(self, pdf_groups: dict, debtor_name: str, progress_callback) -> Dict[str, Any]:
        """Run ALL schedules in parallel."""
        tasks = []
        schedule_names = []

        for name, data in pdf_groups.items():
            prompt = SCHEDULE_PROMPTS.get(name)
            if prompt:
                schedule_names.append(name)
                tasks.append(self._review_schedule(name, data["text"], prompt))
                if progress_callback and name != "Schedule G & H":
                    msg = _progress_message_for_group(name, debtor_name)
                    if msg:
                        progress_callback({"stage": "start_group", "group": name, "message": msg})

        results = await asyncio.gather(*tasks, return_exceptions=True)

        group_reviews = {}
        for i, result in enumerate(results):
            name = schedule_names[i]
            if isinstance(result, Exception):
                group_reviews[name] = {"group_name": name, "status": "failed", "error": str(result)}
            else:
                group_reviews[name] = result

        return group_reviews

    async def run_master_review(self, all_reviews: dict, debtor_name: str, case_number: str, progress_callback) -> Dict[str, Any]:
        """Stream master review with all context using Claude."""
        context_lines = [f"For {debtor_name} ({case_number}):", "", "=" * 50, ""]

        for name, review_data in all_reviews.items():
            if review_data.get("status") == "completed":
                context_lines.append(f"REVIEW OF {name.upper()}:")
                context_lines.append(review_data.get("review", ""))
                context_lines.append("-" * 30)
                context_lines.append("")

        context = "\n".join(context_lines)

        if progress_callback:
            progress_callback({"stage": "start_master", "message": "Generating a clarity report on the petition's strength and accuracy"})

        collected = []
        async with self.client.messages.stream(
            model=CLAUDE_MODEL_STANDARD,
            max_tokens=16384,
            system=MASTER_AGENT_PROMPT,
            messages=[{"role": "user", "content": context}]
        ) as stream:
            async for token in stream.text_stream:
                collected.append(token)
                if progress_callback:
                    progress_callback({"stage": "token", "scope": "master", "token": token})

        if progress_callback:
            progress_callback({"stage": "end_master", "message": "Finished printing the clarity report."})

        return {
            "master_review": "".join(collected),
            "status": "completed"
        }

    async def run_complete_review(self, pdf_path: str, progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """Full review: parallel schedules -> master."""
        if progress_callback:
            progress_callback({"stage": "init", "message": "Starting bankruptcy review..."})

        pdf_groups = process_pdf_and_get_groups(pdf_path)
        if not pdf_groups:
            return {"is_skeleton": True}

        debtor_name, case_number = await self._extract_client_info(progress_callback)

        group_reviews = await self.run_all_schedules(pdf_groups, debtor_name, progress_callback)

        master_result = await self.run_master_review(group_reviews, debtor_name, case_number, progress_callback)

        if progress_callback:
            progress_callback({"stage": "master_result", "result": master_result})
            progress_callback({"stage": "done", "message": "Complete bankruptcy review finished!"})

        return {
            "group_reviews": group_reviews,
            "master_review": master_result,
            "debtor_name": debtor_name,
            "case_number": case_number
        }


async def run_parallel_bankruptcy_review_async(
    pdf_path: str,
    session_id: str,
    progress_callback: Optional[Callable] = None
) -> Dict[str, Any]:
    """Entry point for truly parallel bankruptcy review."""
    reviewer = TrueParallelReviewer(session_id)
    return await reviewer.run_complete_review(pdf_path, progress_callback)
