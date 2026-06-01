"""Shared extractor tool-loop base for v2.

The four v2 extractor agents (`DraftAgentV2`, `DropdownAgentV2`,
`RecoChipsAgentV2`, `MultiSelectAgentV2`) all share the SAME loop:

  1. Build the system + initial user message from the field + tool
     context.
  2. `bind_tools(toolset + [submit_tool])` and `ainvoke`.
  3. If the model called `submit_*`, parse the args into the
     subclass's `output_type` and return — done.
  4. Else for each LOCAL tool call (gmail_search / case_vector_query /
     vision_fallback), execute the tool and append the result as a
     ToolMessage; loop.
  5. Cap iterations to bound runaway tool-call cost; on exhaustion,
     return `None` (caller handles failure by emitting a low-confidence
     ResolvedTemplateValueV2).

The agents differ ONLY in:
- Their `output_type` (the structured-output Pydantic schema).
- Their `submit_tool_name` (the tool name used to discriminate the
  final call from intermediate tool calls).
- Their prompt template (per `prompts.py`).

Cost attribution flows through the same `CostTrackingCallback` pattern
v1's Agent base uses — the orchestrator's `cost_attribution(...)`
context manager owns the bucket; this loop just attaches the callback.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, ClassVar, Generic, TypeVar

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from pydantic import BaseModel

from src.core.common.constants import CLAUDE_MODEL_ADVANCED
from src.core.common.cost_tracking import (
    CostTrackingCallback,
    build_cost_context_for_agent,
)

from ...observability import langfuse_callback

logger = logging.getLogger(__name__)

TOutput = TypeVar("TOutput", bound=BaseModel)


@dataclass(frozen=True)
class ExtractorRunResult(Generic[TOutput]):
    """What `ExtractorAgentV2._run_loop` returns to the subclass.

    `output` is the parsed `submit_*` payload (the subclass's
    structured-output schema) — `None` when the loop exhausted
    `max_iterations` without the agent calling `submit_*`.

    `tool_call_count` is the number of intermediate tool calls
    (gmail_search / case_vector_query / vision_fallback) the agent
    made before finalizing — useful for cost diagnostics + a hint to
    the subclass about confidence.
    """

    output: TOutput | None
    tool_call_count: int
    iterations: int


class ExtractorAgentV2(Generic[TOutput]):
    """Tool-loop base for v2 extractor agents.

    Subclasses declare:
      output_type   — Pydantic class for the submit_* args / final result
      submit_tool_name — Anthropic tool name (matches output_type's __name__)
      model         — Claude model (default CLAUDE_MODEL_ADVANCED)
      max_tokens    — per-call cap (default 4000)
      max_iterations — loop cap (default 8)
      tags          — LangChain run tags
      cost_kind     — llm_cost_logs.kind bucket label

    and implement `_build_messages(field, params, ctx, dependency_values)`
    to compose the initial system + human messages.
    """

    output_type: ClassVar[type[BaseModel]]
    submit_tool_name: ClassVar[str]
    model: ClassVar[str] = CLAUDE_MODEL_ADVANCED
    max_tokens: ClassVar[int] = 4000
    temperature: ClassVar[float] = 0
    max_iterations: ClassVar[int] = 8
    tags: ClassVar[list[str]] = ["core", "agent", "studio_v2"]
    cost_kind: ClassVar[str] = "extractor_v2"

    @classmethod
    async def _run_loop(
        cls,
        *,
        messages: list[BaseMessage],
        tools: list[Any],
        agent_name: str,
        metadata: dict[str, str] | None = None,
    ) -> ExtractorRunResult[TOutput]:
        """Drive the tool loop until the agent calls submit_* or
        iterations exhaust.

        `tools` MUST include the submit tool (typically `cls.output_type`
        passed as the last entry) — the loop checks every iteration's
        `tool_calls` for one whose name matches `cls.submit_tool_name`
        and uses its args as the final structured output.

        `messages` is the initial conversation — typically
        `[SystemMessage(...), HumanMessage(...)]` from the subclass's
        `_build_messages`. The loop appends each iteration's
        `AIMessage` + `ToolMessage`s as it goes.

        Real tools (gmail_search / case_vector_query / vision_fallback)
        in `tools` MUST be LangChain `BaseTool` instances or
        `@tool`-decorated coroutines so `ainvoke({"args": ...})` works.
        """
        # `cls.output_type` is the submit tool's Pydantic schema. We
        # also bind the real action tools so the model can call them.
        llm = ChatAnthropic(
            model=cls.model,
            temperature=cls.temperature,
            max_tokens=cls.max_tokens,
        )
        cost_ctx = build_cost_context_for_agent(
            kind=cls.cost_kind,
            agent_name=agent_name,
        )
        callbacks: list[Any] = [CostTrackingCallback(cost_context=cost_ctx)]
        # Langfuse tracing — opt-in via env. Returns None when keys
        # aren't set; we skip the append and the LLM runs untraced.
        lf_handler = langfuse_callback()
        if lf_handler is not None:
            callbacks.append(lf_handler)
        # Lift `template_variable` (when present) into the run_name so
        # Langfuse traces show "DraftAgentV2:debtor_name" instead of
        # bare "DraftAgentV2". Falls back to bare agent_name when the
        # call site didn't supply a template_variable.
        run_name = agent_name
        if metadata and metadata.get("template_variable"):
            run_name = f"{agent_name}:{metadata['template_variable']}"
        llm = llm.bind_tools(tools).with_config(
            {
                "run_name": run_name,
                "tags": cls.tags,
                "metadata": metadata or {},
                "callbacks": callbacks,
            },
        )

        # Tools index keyed by name so we can dispatch the model's
        # tool_calls to the right callable.
        tool_index: dict[str, Any] = {}
        for tool in tools:
            name = _get_tool_name(tool)
            if name is None:
                continue
            tool_index[name] = tool

        running_messages: list[BaseMessage] = list(messages)
        tool_call_count = 0

        for iteration in range(1, cls.max_iterations + 1):
            try:
                ai_message: AIMessage = await llm.ainvoke(running_messages)
            except Exception as err:  # noqa: BLE001
                logger.warning(
                    "%s: LLM ainvoke failed at iteration %d (%s)",
                    agent_name, iteration, err,
                )
                return ExtractorRunResult(
                    output=None, tool_call_count=tool_call_count, iterations=iteration,
                )

            running_messages.append(ai_message)

            tool_calls = list(ai_message.tool_calls or [])

            # Check for the submit_* call — if present, parse it as the
            # final structured output and exit the loop.
            submit_call = next(
                (tc for tc in tool_calls if tc.get("name") == cls.submit_tool_name),
                None,
            )
            if submit_call is not None:
                output = cls._parse_submit_call(submit_call, agent_name)
                return ExtractorRunResult(
                    output=output,
                    tool_call_count=tool_call_count,
                    iterations=iteration,
                )

            # No submit_* call — dispatch every other tool_call as a
            # real action tool and feed results back.
            if not tool_calls:
                # Model returned text without calling any tool — treat
                # as a soft failure; emit no output. Caller degrades.
                logger.info(
                    "%s: model finished without calling %s "
                    "(iteration %d) — likely couldn't extract.",
                    agent_name, cls.submit_tool_name, iteration,
                )
                return ExtractorRunResult(
                    output=None, tool_call_count=tool_call_count, iterations=iteration,
                )

            for tc in tool_calls:
                tool_call_count += 1
                tool_msg = await cls._dispatch_one_tool_call(
                    tc, tool_index, agent_name,
                )
                running_messages.append(tool_msg)

        logger.info(
            "%s: exhausted max_iterations=%d without calling %s",
            agent_name, cls.max_iterations, cls.submit_tool_name,
        )
        return ExtractorRunResult(
            output=None,
            tool_call_count=tool_call_count,
            iterations=cls.max_iterations,
        )

    @classmethod
    def _parse_submit_call(
        cls,
        tool_call: dict,
        agent_name: str,
    ) -> TOutput | None:
        """Validate the submit_* call's args against `cls.output_type`."""
        args = tool_call.get("args") or {}
        try:
            return cls.output_type.model_validate(args)  # type: ignore[return-value]
        except Exception as err:  # noqa: BLE001
            logger.warning(
                "%s: submit_* args failed validation (%s); args=%s",
                agent_name, err, args,
            )
            return None

    @classmethod
    async def _dispatch_one_tool_call(
        cls,
        tool_call: dict,
        tool_index: dict[str, Any],
        agent_name: str,
    ) -> ToolMessage:
        """Run a single tool call and wrap the result as a ToolMessage."""
        name = tool_call.get("name", "")
        args = tool_call.get("args") or {}
        call_id = tool_call.get("id", "")

        tool = tool_index.get(name)
        if tool is None:
            logger.warning(
                "%s: model called unknown tool %s (call_id=%s); ignoring",
                agent_name, name, call_id,
            )
            return ToolMessage(
                content=json.dumps({"error": f"Tool {name!r} is not available."}),
                tool_call_id=call_id,
                name=name,
            )

        try:
            result = await tool.ainvoke(args)
        except Exception as err:  # noqa: BLE001
            logger.warning(
                "%s: tool %s raised (%s); returning error to model",
                agent_name, name, err,
            )
            return ToolMessage(
                content=json.dumps({"error": str(err)}),
                tool_call_id=call_id,
                name=name,
            )

        # ToolMessage requires str content; serialize non-strings.
        if isinstance(result, str):
            content: str = result
        else:
            try:
                content = json.dumps(result, default=str)
            except Exception:  # noqa: BLE001
                content = str(result)

        return ToolMessage(
            content=content,
            tool_call_id=call_id,
            name=name,
        )


def _get_tool_name(tool: Any) -> str | None:
    """Best-effort tool-name resolution across:

    - LangChain BaseTool instances (`tool.name`)
    - Pydantic BaseModel subclasses used as structured-output tools
      (`tool.__name__`)
    - `@tool`-decorated coroutines (also have `.name`)
    """
    name_attr = getattr(tool, "name", None)
    if isinstance(name_attr, str) and name_attr:
        return name_attr
    if isinstance(tool, type):
        return tool.__name__
    return None


def make_initial_messages(
    *,
    system_prompt: str,
    user_prompt: str,
) -> list[BaseMessage]:
    """Convenience constructor used by every extractor subclass."""
    return [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
