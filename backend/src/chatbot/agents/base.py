from typing import Dict, Any
from langgraph.prebuilt import create_react_agent
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import MemorySaver

from ...ai_models import CLAUDE_MODEL_STANDARD, CLAUDE_PROVIDER, CLAUDE_TEMPERATURE


def _build_agent_executor(system_prompt: str, tools: list, api_key: str, memory_saver: MemorySaver = None):
    """Create a LangGraph ReAct agent executor with optional shared MemorySaver.

    Args:
        system_prompt: The system prompt to steer the agent.
        tools: List of tools the agent can use (can be empty).
        api_key: Model provider API key.
        memory_saver: Optional shared MemorySaver instance. If None, a new one is created.

    Returns:
        A tuple of (agent_executor, checkpointer)
    """
    llm = init_chat_model(
        CLAUDE_MODEL_STANDARD,
        model_provider=CLAUDE_PROVIDER,
        api_key=api_key,
        temperature=CLAUDE_TEMPERATURE
    )
    checkpointer = memory_saver or MemorySaver()
    agent_executor = create_react_agent(
        tools=tools,
        model=llm,
        prompt=system_prompt,
        checkpointer=checkpointer
    )
    return agent_executor, checkpointer


def _extract_text_content(value) -> str:
    if value is None:
        return ""

    if isinstance(value, str):
        return value

    if isinstance(value, list):
        parts = []
        for item in value:
            text = _extract_text_content(item)
            if text:
                parts.append(text)
        return "".join(parts)

    if isinstance(value, dict):
        item_type = value.get("type")

        if item_type in {"text", "text_delta"}:
            text = value.get("text")
            if text:
                return str(text)

        if item_type == "content_block_delta":
            delta = value.get("delta")
            if isinstance(delta, dict):
                return _extract_text_content(delta)

        if item_type in {"tool_use", "input_json_delta", "thinking", "server_tool_use"}:
            return ""

        if "content" in value:
            return _extract_text_content(value.get("content"))

        return ""

    if hasattr(value, "content"):
        return _extract_text_content(value.content)

    return ""


def _extract_last_ai_message_text(response: Dict[str, Any]) -> str:
    if "messages" not in response:
        return ""

    ai_messages = []
    for message in response["messages"]:
        if hasattr(message, "content") and hasattr(message, "__class__"):
            if "AIMessage" in str(message.__class__):
                text = _extract_text_content(message.content).strip()
                if text:
                    ai_messages.append(text)

    if ai_messages:
        return ai_messages[-1]

    return ""
