from typing import Dict, Any, Optional
from langchain.chat_models import init_chat_model
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from ..tools import context_tool, motion_modify_tool
from ...config import settings
from ...ai_models import CLAUDE_MODEL_STANDARD, CLAUDE_PROVIDER, CLAUDE_TEMPERATURE, TEMPERATURE_AGENTS
from .base import _build_agent_executor, _extract_last_ai_message_text


class CaseNumberAgent:
    def __init__(self, session_id: Optional[str] = None, memory_saver=None):
        """
        Agent dedicated to extracting ONLY the case number from the session's
        uploaded bankruptcy PDFs using the extract_case_no_modify tool.
        """
        self.api_key = settings.ANTHROPIC_API_KEY
        if not self.api_key:
            raise ValueError("Anthropic API key not found in config. Please check your .env file.")

        self.session_id = session_id or "case_number_default"
        self.memory_saver = memory_saver

        # Get the specific tool for case number extraction
        tools = motion_modify_tool(session_id=self.session_id)
        case_no_tool = None

        for tool in tools:
            if tool.name == "extract_case_no_modify":
                case_no_tool = tool
                break

        if not case_no_tool:
            raise ValueError("extract_case_no_modify tool not found")

        instruction = (
            "You are a precise extractor. Your sole task is to read the user's "
            "uploaded bankruptcy petition PDFs via tools and return ONLY the case number "
            "in the short format XX-XXXXX (year-number, e.g. 25-15244). "
            "Constraints:\n"
            "- Output the case number string only, no labels, punctuation, or extra text.\n"
            "- Look for patterns like '1:25-bk-15244', '26-bk-11993', '26-11993' etc. "
            "and convert to the short XX-XXXXX format by extracting just the year and number.\n"
            "- For example: '1:25-bk-15244' -> '25-15244', '26-bk-11993' -> '26-11993'.\n"
            "- Strip any chapter prefix, 'bk' segment, or judge suffix (e.g. KKS).\n"
            "- If uncertain, return 'N/A'."
        )

        self.agent_executor, _ = _build_agent_executor(
            system_prompt=instruction,
            tools=[case_no_tool],
            api_key=self.api_key,
            memory_saver=self.memory_saver
        )

    def extract_case_number(self) -> dict:
        try:
            response = self.agent_executor.invoke(
                {"messages": [
                    {"role": "user", "content": "From the uploaded PDFs, return ONLY the case number."}
                ]},
                config={"configurable": {"thread_id": self.session_id}}
            )

            case_number = _extract_last_ai_message_text(response)
            if not case_number:
                case_number = str(response).strip()

            # Post-trim to ensure single-line case number
            case_number = case_number.splitlines()[0].strip()

            return {"status": "completed", "case_number": case_number}
        except Exception as e:
            return {"status": "failed", "error": str(e)}


class DebtorNameAgent:
    def __init__(self, session_id: Optional[str] = None, memory_saver: MemorySaver = None):
        """
        Agent dedicated to extracting ONLY the debtor's name from the session's
        uploaded bankruptcy PDFs using the general context_tool.
        The agent is strictly instructed to return just the debtor name string.
        """
        self.api_key = settings.ANTHROPIC_API_KEY
        if not self.api_key:
            raise ValueError("Anthropic API key not found in config. Please check your .env file.")

        self.session_id = session_id or "debtor_name_default"
        self.memory_saver = memory_saver or MemorySaver()

        tools = context_tool(session_id=self.session_id)

        instruction = (
            "You are a precise extractor. Your sole task is to read the user's "
            "uploaded bankruptcy petition PDFs via tools and return ONLY the debtor's full legal name(s). "
            "Task: Extract the debtor's full legal name from Part 1 'Your full name', 'Debtor 1' and "
            "'Debtor 2' if there is a Debtor 2.\n"
            "Constraints:\n"
            "- Output a single name string only, no labels, punctuation, or extra text.\n"
            "- If there is only Debtor 1, return just Debtor 1's full name.\n"
            "- If there are Debtor 1 and Debtor 2, return both names in a single string joined with ' and ', "
            "for example: 'John Doe and Jane Doe'.\n"
            "- If uncertain or not found, return 'N/A'."
        )

        self.llm = init_chat_model(
            CLAUDE_MODEL_STANDARD,
            model_provider=CLAUDE_PROVIDER,
            api_key=self.api_key,
            temperature=CLAUDE_TEMPERATURE
        )
        self.agent_executor = create_react_agent(
            tools=tools,
            model=self.llm,
            prompt=instruction,
            checkpointer=self.memory_saver
        )

    def extract_debtor_name(self) -> dict:
        try:
            response = self.agent_executor.invoke(
                {"messages": [
                    {"role": "user", "content": (
                        "From the uploaded bankruptcy petition PDFs, return ONLY the debtor's full legal name(s). "
                        "If there is only Debtor 1, return just Debtor 1's full name. "
                        "If there are Debtor 1 and Debtor 2, return both names joined with ' and ' "
                        "in a single string (for example: 'John Doe and Jane Doe'). "
                        "Do not add labels, punctuation, or extra text. If uncertain, return 'N/A'."
                    )}
                ]},
                config={"configurable": {"thread_id": self.session_id}}
            )

            debtor_name = _extract_last_ai_message_text(response)
            if not debtor_name:
                debtor_name = str(response).strip()

            # Post-trim to ensure single-line name
            debtor_name = debtor_name.splitlines()[0].strip()

            return {"status": "completed", "debtor_name": debtor_name}
        except Exception as e:
            return {"status": "failed", "error": str(e)}
