from anthropic import Anthropic
from typing import Dict, Any, Optional
from langchain.chat_models import init_chat_model
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from ..tools import context_tool
from ..prompts import (
    AB_PROMPT, CD_PROMPT, IJ_CMI_PROMPT, SOFA_PROMPT, EF_PROMPT, GH_PROMPT,
    MASTER_AGENT_PROMPT,
)
from ...config import settings
from ...ai_models import CLAUDE_MODEL_STANDARD, CLAUDE_PROVIDER, CLAUDE_TEMPERATURE
from .extractors import DebtorNameAgent, CaseNumberAgent


class BankruptcyReviewAgent:
    def __init__(self, memory_saver: MemorySaver = None, session_id: Optional[str] = None, regular_agent: 'RegularChatAgent' = None):
        """Initialize the Bankruptcy Review Agent using a shared or isolated MemorySaver.

        If a MemorySaver and session_id are provided, reviews can share memory with
        other agents by using the same thread_id.
        """
        self.api_key = settings.ANTHROPIC_API_KEY
        if not self.api_key:
            raise ValueError("Anthropic API key not found in config. Please check your .env file.")

        self.memory_saver = memory_saver or MemorySaver()
        self.session_id = session_id or "bankruptcy_review_default"
        self.regular_agent = regular_agent

        # Map document groups to their corresponding prompts
        self.group_prompt_mapping = {
            "Schedule A/B": AB_PROMPT,
            "Schedule C & D": CD_PROMPT,
            "Schedule I, J & Summary": IJ_CMI_PROMPT,
            "Statement of Financial Affairs": SOFA_PROMPT,
            "Schedule E/F": EF_PROMPT,
            "Schedule G & H": GH_PROMPT
        }

        # Define the dependency order for cascading reviews
        self.dependency_order = [
            "Schedule A/B",           # Base - no dependencies
            "Schedule C & D",         # Depends on A/B
            "Schedule I, J & Summary", # Depends on C & D
            "Statement of Financial Affairs", # Depends on I, J & Summary
            "Schedule E/F",           # Depends on SOFA
            "Schedule G & H"          # Depends on E/F
        ]

    def review_document_group(self, group_name: str, pages_text: str, previous_reviews: Dict[str, Any] = None, progress_callback=None) -> Dict[str, Any]:
        """
        Review a specific document group using the appropriate prompt and previous reviews.

        Args:
            group_name: Name of the document group (e.g., "Schedule A/B")
            pages_text: Combined text from all pages in the group
            previous_reviews: Dictionary of previous review results to include as context

        Returns:
            Dictionary containing the review results
        """
        if group_name not in self.group_prompt_mapping:
            return {
                "error": f"Unknown document group: {group_name}",
                "group_name": group_name
            }

        prompt = self.group_prompt_mapping[group_name]

        # Build context from previous reviews
        context_text = ""
        if previous_reviews:
            context_text = "\n\nPREVIOUS REVIEWS FOR CONTEXT:\n"
            context_text += "=" * 50 + "\n"
            for review_group, review_data in previous_reviews.items():
                if review_data.get("status") == "completed":
                    context_text += f"\n{review_group}:\n{review_data.get('review', '')}\n"
                    context_text += "-" * 30 + "\n"

        try:
            # Stream tokens directly from Claude, but only accumulate locally.
            # We do NOT emit per-token progress updates for groups anymore –
            # the frontend will show only high-level group titles.
            collected_tokens = []
            client = Anthropic(api_key=self.api_key)
            with client.messages.stream(
                model=CLAUDE_MODEL_STANDARD,
                max_tokens=8192,
                system=prompt,
                messages=[{
                    "role": "user",
                    "content": f"Please review the following {group_name} documents:\n\n{pages_text}{context_text}"
                }]
            ) as stream:
                for token in stream.text_stream:
                    if token:
                        collected_tokens.append(token)
                        # Deliberately skip per-token progress_callback for groups

            review_content = "".join(collected_tokens).strip()

            result = {
                "group_name": group_name,
                "review": review_content,
                "status": "completed",
                "model_used": None,
                "tokens_used": None,
                "dependencies_used": list(previous_reviews.keys()) if previous_reviews else []
            }

            return result

        except Exception as e:
            result = {
                "group_name": group_name,
                "error": str(e),
                "status": "failed"
            }

            return result

    def review_all_groups_cascading(self, pdf_groups_data: Dict[str, Dict], progress_callback=None) -> Dict[str, Any]:
        """
        Review all document groups in dependency order, with each review including previous results.

        Args:
            pdf_groups_data: Dictionary from page_splitter.process_pdf_and_get_groups()
            progress_callback: Optional callback function for progress updates

        Returns:
            Dictionary containing reviews for all groups in dependency order
        """
        results = {}
        previous_reviews = {}

        # Best-effort debtor name extraction for use in progress messages
        debtor_name = None
        if callable(progress_callback):
            try:
                debtor_agent = DebtorNameAgent(session_id=self.session_id)
                debtor_result = debtor_agent.extract_debtor_name()
                if debtor_result.get("status") == "completed":
                    debtor_name = (debtor_result.get("debtor_name") or "").strip() or None
            except Exception:
                debtor_name = None

        # Helper to build human-facing progress message per group
        def _progress_message_for_group(name: str) -> str:
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
            # For Schedule G & H, do not reuse the master-agent title;
            # return an empty string so the frontend keeps the previous header.
            if name == "Schedule G & H":
                return ""
            # Fallback to original behavior for any other group
            return f"Analyzing {name}..."

        # Process groups in dependency order
        for group_name in self.dependency_order:
            if group_name in pdf_groups_data:
                # Get the text for this group
                pages_text = pdf_groups_data[group_name]["text"]

                # For Schedule G & H, do not emit a separate start_group event so its
                # analysis appears under the previous schedule's title in the UI.
                if group_name != "Schedule G & H":
                    if callable(progress_callback):
                        try:
                            progress_callback({
                                "stage": "start_group",
                                "group": group_name,
                                "message": _progress_message_for_group(group_name),
                            })
                        except Exception:
                            pass

                # Review this group with context from previous reviews
                review_result = self.review_document_group(
                    group_name,
                    pages_text,
                    previous_reviews,
                    progress_callback=progress_callback,
                )
                results[group_name] = review_result

                # Add this review to previous reviews for next iteration
                if review_result.get("status") == "completed":
                    previous_reviews[group_name] = review_result

        # Process any remaining groups not in dependency order
        for group_name, group_data in pdf_groups_data.items():
            if group_name not in self.dependency_order:
                pages_text = group_data["text"]

                if callable(progress_callback):
                    try:
                        progress_callback({
                            "stage": "start_group",
                            "group": group_name,
                            "message": _progress_message_for_group(group_name),
                        })
                    except Exception:
                        pass

                review_result = self.review_document_group(
                    group_name,
                    pages_text,
                    previous_reviews,
                    progress_callback=progress_callback,
                )
                results[group_name] = review_result

        return results

    def review_all_groups(self, pdf_groups_data: Dict[str, Dict], progress_callback=None) -> Dict[str, Any]:
        """
        Review all document groups using the processed data from page_splitter.
        This method maintains backward compatibility but uses cascading by default.

        Args:
            pdf_groups_data: Dictionary from page_splitter.process_pdf_and_get_groups()
            progress_callback: Optional callback function for progress updates

        Returns:
            Dictionary containing reviews for all groups
        """
        return self.review_all_groups_cascading(pdf_groups_data, progress_callback=progress_callback)


class MasterReviewAgent:
    def __init__(self, memory_saver: MemorySaver = None, session_id: Optional[str] = None, regular_agent: 'RegularChatAgent' = None):
        """Initialize the Master Review Agent with tools to query uploaded files."""
        self.api_key = settings.ANTHROPIC_API_KEY
        if not self.api_key:
            raise ValueError("Anthropic API key not found in config. Please check your .env file.")
        self.memory_saver = memory_saver or MemorySaver()
        self.session_id = session_id or "master_review_default"
        self.regular_agent = regular_agent

        # Initialize the LLM and agent executor with tools for extracting client info
        self.llm = init_chat_model(
            CLAUDE_MODEL_STANDARD,
            model_provider=CLAUDE_PROVIDER,
            api_key=self.api_key,
            temperature=CLAUDE_TEMPERATURE
        )
        self.agent_executor = create_react_agent(
            tools=context_tool(session_id=self.session_id),
            model=self.llm,
            prompt=MASTER_AGENT_PROMPT,
            checkpointer=self.memory_saver
        )

    def run_master_review(self, all_group_reviews: Dict[str, Any], progress_callback=None) -> Dict[str, Any]:
        """
        Run the master review using LangGraph agent with tools to extract client info.

        Args:
            all_group_reviews: Dictionary containing all group review results
            progress_callback: Optional callback function for progress updates

        Returns:
            Dictionary containing the master review results
        """
        try:
            # Extract debtor name and case number using dedicated agents
            if callable(progress_callback):
                try:
                    progress_callback({"stage": "extract_client_info", "message": "Extracting client name and case number..."})
                except Exception:
                    pass

            debtor_agent = DebtorNameAgent(session_id=self.session_id)
            debtor_result = debtor_agent.extract_debtor_name()
            debtor_name = debtor_result.get("debtor_name", "N/A") if debtor_result.get("status") == "completed" else "N/A"

            case_agent = CaseNumberAgent(session_id=self.session_id)
            case_result = case_agent.extract_case_number()
            case_number = case_result.get("case_number", "N/A") if case_result.get("status") == "completed" else "N/A"

            # Prepare the context message with all group reviews and extracted client info
            context_message = f"For {debtor_name} ({case_number}):\n\n"
            context_message += "Please review the following bankruptcy schedule reviews:\n\n"
            context_message += "=" * 80 + "\n\n"

            for group_name, review_data in all_group_reviews.items():
                if review_data.get("status") == "completed":
                    context_message += f"REVIEW OF {group_name.upper()}:\n"
                    context_message += f"{review_data.get('review', '')}\n\n"
                    context_message += "-" * 50 + "\n\n"
                elif review_data.get("status") == "failed":
                    context_message += f"REVIEW OF {group_name.upper()}: FAILED - {review_data.get('error', 'Unknown error')}\n\n"
                    context_message += "-" * 50 + "\n\n"

            # Stream tokens from Claude for the master review
            if callable(progress_callback):
                try:
                    progress_callback({
                        "stage": "start_master",
                        "message": "Generating a clarity report on the petition's strength and accuracy"
                    })
                except Exception:
                    pass

            collected_tokens = []
            client = Anthropic(api_key=self.api_key)
            with client.messages.stream(
                model=CLAUDE_MODEL_STANDARD,
                max_tokens=16384,
                system=MASTER_AGENT_PROMPT,
                messages=[{"role": "user", "content": context_message}]
            ) as stream:
                for token in stream.text_stream:
                    if token:
                        collected_tokens.append(token)
                        if callable(progress_callback):
                            try:
                                progress_callback({
                                    "stage": "token",
                                    "scope": "master",
                                    "token": token
                                })
                            except Exception:
                                pass

            master_review_content = "".join(collected_tokens).strip()

            result = {
                "master_review": master_review_content,
                "status": "completed",
                "model_used": None,
                "tokens_used": None
            }

            if callable(progress_callback):
                try:
                    progress_callback({"stage": "master_result", "result": result})
                    progress_callback({"stage": "end_master", "message": "Finished printing the clarity report."})
                except Exception:
                    pass

            return result

        except Exception as e:
            fail = {
                "master_review": f"Master review failed: {str(e)}",
                "status": "failed",
                "error": str(e)
            }
            if callable(progress_callback):
                try:
                    progress_callback({"stage": "master_result", "result": fail})
                except Exception:
                    pass
            return fail

    def _extract_master_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Helper method to extract AI response from LangGraph agent response.
        """
        ai_response = ""
        if "messages" in response:
            # Find the last AI message (most recent response)
            ai_messages = []
            for message in response["messages"]:
                if hasattr(message, 'content') and hasattr(message, '__class__'):
                    # Check if it's an AI message (not HumanMessage)
                    if 'AIMessage' in str(message.__class__):
                        ai_messages.append(message.content)

            # Get the last AI message
            if ai_messages:
                ai_response = ai_messages[-1]

        # Fallback if we couldn't extract the response
        if not ai_response:
            ai_response = str(response)

        return {
            "master_review": ai_response,
            "status": "completed",
            "model_used": None,
            "tokens_used": None
        }

    def _extract_master_response_from_token(self, token) -> Dict[str, Any]:
        """
        Helper method to extract AI response from a streaming token.
        """
        ai_response = ""

        # Handle different token formats from streaming
        if hasattr(token, 'content'):
            # Direct message object
            ai_response = token.content
        elif isinstance(token, dict):
            # Dictionary format - look for content or messages
            if 'content' in token:
                ai_response = token['content']
            elif 'messages' in token:
                # Extract from messages array
                for message in token['messages']:
                    if hasattr(message, 'content') and hasattr(message, '__class__'):
                        if 'AIMessage' in str(message.__class__):
                            ai_response = message.content
                            break
        elif isinstance(token, str):
            # Direct string
            ai_response = token

        # Fallback if we couldn't extract the response
        if not ai_response:
            ai_response = str(token)

        return {
            "master_review": ai_response,
            "status": "completed",
            "model_used": None,
            "tokens_used": None
        }
