from typing import Dict, Any, Optional
from langchain.chat_models import init_chat_model
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from ..tools import context_tool, loe_supporting_tool, petition_pdf_tool
from ..prompts import ASSISTANT_SYSTEM_PROMPT
from ...config import settings
from ...ai_models import CLAUDE_MODEL_STANDARD, CLAUDE_PROVIDER, CLAUDE_TEMPERATURE, CLAUDE_MAX_TOKENS_CHAT


class RegularChatAgent:
    def __init__(self, session_id: Optional[str] = None, memory_saver: MemorySaver = None):
        """Initialize the Regular Chat Agent with tools and model access.

        If a session_id is provided, tools will be configured to query the
        session-scoped vectorstore (bankruptcy_knowledge_<session_id>).
        """
        self.api_key = settings.ANTHROPIC_API_KEY
        if not self.api_key:
            raise ValueError("Anthropic API key not found in config. Please check your .env file.")
        self.session_id = session_id
        self.memory_saver = memory_saver or MemorySaver()

        # Initialize the LLM and agent executor with MemorySaver
        self.llm = init_chat_model(
            CLAUDE_MODEL_STANDARD,
            model_provider=CLAUDE_PROVIDER,
            api_key=self.api_key,
            temperature=CLAUDE_TEMPERATURE,
            max_tokens=CLAUDE_MAX_TOKENS_CHAT,
        )

        # Combine context tools with LOE supporting docs tool for querying user-uploaded documents
        all_tools = (
            context_tool(session_id=self.session_id)
            + loe_supporting_tool(session_id=self.session_id)
            + petition_pdf_tool(session_id=self.session_id)
        )
        self.agent_executor = create_react_agent(
            tools=all_tools,
            model=self.llm,
            prompt=ASSISTANT_SYSTEM_PROMPT,
            checkpointer=self.memory_saver
        )

    def chat(self, user_message: str, session_id: str = None, progress_callback=None, chat_history: list = None) -> Dict[str, Any]:
        """
        Process a user message using the regular chat agent with tools and MemorySaver context.

        Args:
            user_message: User's message
            session_id: Session ID to use as thread_id for MemorySaver
            progress_callback: Optional callback for streaming tokens
            chat_history: Prior messages from DB to inject when no MemorySaver checkpoint exists.
                          Each item should be {"role": "user"|"assistant", "content": "..."}

        Returns:
            Dictionary containing the agent's response
        """
        try:
            config = {"configurable": {"thread_id": session_id or "default"}}

            # If the MemorySaver has no checkpoint for this thread yet, inject DB history
            # so the agent has full conversation context even after a server restart.
            base_messages = [{"role": "user", "content": user_message}]
            if chat_history:
                try:
                    existing_checkpoint = self.memory_saver.get(config)
                    if existing_checkpoint is None and chat_history:
                        base_messages = chat_history + [{"role": "user", "content": user_message}]
                except Exception:
                    pass

            if callable(progress_callback):
                # Use LangGraph streaming with stream_mode="messages"
                import asyncio

                async def stream_chat():
                    collected_tokens = []
                    final_response = None
                    last_ai_state = None

                    try:
                        # Use stream_mode="messages" as per the example
                        async for token, metadata in self.agent_executor.astream(
                            {"messages": base_messages},
                            config=config,
                            stream_mode="messages"
                        ):
                            if not self._is_ai_message(token):
                                continue

                            content_str = self._extract_text_content(token)
                            if content_str:
                                collected_tokens.append(content_str)
                                try:
                                    progress_callback({
                                        "stage": "token",
                                        "scope": "chat",
                                        "token": content_str
                                    })
                                except Exception:
                                    pass

                            last_ai_state = token

                        # After streaming is complete, use the collected tokens for final response
                        final_text = "".join(collected_tokens).strip()
                        if final_text:
                            final_response = {
                                "response": final_text,
                                "status": "completed",
                                "agent_type": "regular_chat"
                            }
                        elif last_ai_state is not None:
                            final_response = self._extract_response_from_token(last_ai_state)
                        else:
                            response = self.agent_executor.invoke(
                                {"messages": base_messages},
                                config=config
                            )
                            final_response = self._extract_response(response)

                        return final_response

                    except Exception as stream_error:
                        # If streaming fails completely, fall back to non-streaming
                        response = self.agent_executor.invoke(
                            {"messages": base_messages},
                            config=config
                        )
                        return self._extract_response(response)

                # Run the async streaming function synchronously
                try:
                    # Check if we're already in an event loop
                    try:
                        loop = asyncio.get_running_loop()
                        # We're in an async context, need to handle this differently
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            future = executor.submit(asyncio.run, stream_chat())
                            return future.result()
                    except RuntimeError:
                        # No running loop, safe to use asyncio.run
                        return asyncio.run(stream_chat())
                except Exception as e:
                    # Final fallback to non-streaming
                    response = self.agent_executor.invoke(
                        {"messages": base_messages},
                        config=config
                    )
                    return self._extract_response(response)
            else:
                # Original non-streaming approach using LangGraph
                response = self.agent_executor.invoke(
                    {"messages": base_messages},
                    config=config
                )
                return self._extract_response(response)

        except Exception as e:
            return {
                "response": f"Chat failed: {str(e)}",
                "status": "failed",
                "error": str(e),
                "agent_type": "regular_chat"
            }

    def _is_ai_message(self, value) -> bool:
        return hasattr(value, '__class__') and 'AIMessage' in str(value.__class__)

    def _extract_text_content(self, value) -> str:
        if value is None:
            return ""

        if isinstance(value, str):
            return value

        if isinstance(value, list):
            parts = []
            for item in value:
                text = self._extract_text_content(item)
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
                    return self._extract_text_content(delta)

            if item_type in {"tool_use", "input_json_delta", "thinking", "server_tool_use"}:
                return ""

            if "content" in value:
                return self._extract_text_content(value.get("content"))

            if "messages" in value:
                parts = []
                for message in value["messages"]:
                    if hasattr(message, 'content') and hasattr(message, '__class__'):
                        if 'AIMessage' in str(message.__class__):
                            text = self._extract_text_content(message.content)
                            if text:
                                parts.append(text)
                return "".join(parts)

            return ""

        if hasattr(value, 'content'):
            return self._extract_text_content(value.content)

        return ""

    def _extract_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
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
                        ai_messages.append(self._extract_text_content(message.content))

            # Get the last AI message
            if ai_messages:
                ai_response = ai_messages[-1]

        # Fallback if we couldn't extract the response
        if not ai_response:
            ai_response = self._extract_text_content(response) or str(response)

        return {
            "response": ai_response,
            "status": "completed",
            "agent_type": "regular_chat"
        }

    def _extract_response_from_token(self, token) -> Dict[str, Any]:
        """
        Helper method to extract AI response from a streaming token.
        """
        ai_response = ""

        # Handle different token formats from streaming
        ai_response = self._extract_text_content(token)

        # Fallback if we couldn't extract the response
        if not ai_response:
            ai_response = str(token)

        return {
            "response": ai_response,
            "status": "completed",
            "agent_type": "regular_chat"
        }
