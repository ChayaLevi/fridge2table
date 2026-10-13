"""Per-step timing of an agent turn: every model call and every tool call, in seconds.

`TimedModel` wraps any pydantic-ai model and appends a `StepTiming` to a shared list after each request;
`TimedToolset` does the same around every tool call. `run_turn` in `app/agent.py` creates the list
(`Deps.steps`) and returns it in `TurnResult.steps`; the trace (T2.3) and the latency work (T5.2) read it.
"""

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ThinkingPart, ToolCallPart
from pydantic_ai.models import Model, ModelRequestParameters, StreamedResponse
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.settings import ModelSettings
from pydantic_ai.toolsets import ToolsetTool, WrapperToolset

from app.models import StepTiming


def response_detail(response: ModelResponse) -> str:
    """What a model response contained: "-> suggest_meals, validate_suggestion", "text", "thinking 840 chars"."""
    calls = [p.tool_name for p in response.parts if isinstance(p, ToolCallPart)]
    parts = []
    if calls:
        parts.append("-> " + ", ".join(calls))
    if any(isinstance(p, TextPart) and p.content.strip() for p in response.parts):
        parts.append("text")
    thinking = sum(len(p.content or "") for p in response.parts if isinstance(p, ThinkingPart))
    if thinking:
        parts.append(f"thinking {thinking} chars")
    return "; ".join(parts) or "empty"


def result_summary(result: Any, limit: int = 80) -> str:
    """A short, one-line summary of a tool result (also used by the trace in T2.3)."""
    if isinstance(result, BaseModel):
        if hasattr(result, "ok"):
            text = "ok" if result.ok else f"FAILED: {getattr(result, 'reason', '')}"
        elif hasattr(result, "summary"):
            text = result.summary()
        else:
            text = result.model_dump_json(exclude_defaults=True)
    elif isinstance(result, list):
        names = [getattr(r, "name", None) or str(r) for r in result]
        text = f"{len(result)} items: {', '.join(names)}"
    else:
        text = " ".join(str(result).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


class TimedModel(WrapperModel):
    """Appends a StepTiming(kind="model") to `steps` after every request (streaming included)."""

    def __init__(self, wrapped: Model, steps: list[StepTiming], label: str = "") -> None:
        super().__init__(wrapped)
        self.steps = steps
        self.step_name = label or wrapped.model_name

    def _record(self, start: float, response: ModelResponse | None, error: BaseException | None = None) -> None:
        seconds = round(time.perf_counter() - start, 2)
        if response is None:
            self.steps.append(StepTiming(kind="model", name=self.step_name, seconds=seconds,
                                         detail=f"error: {type(error).__name__}"))
            return
        self.steps.append(StepTiming(
            kind="model", name=self.step_name, seconds=seconds, detail=response_detail(response),
            input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens,
        ))

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        start = time.perf_counter()
        try:
            response = await super().request(messages, model_settings, model_request_parameters)
        except BaseException as e:
            self._record(start, None, e)
            raise
        self._record(start, response)
        return response

    @asynccontextmanager
    async def request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
        run_context: RunContext[Any] | None = None,
    ) -> AsyncGenerator[StreamedResponse]:
        start = time.perf_counter()
        stream: StreamedResponse | None = None
        try:
            async with super().request_stream(messages, model_settings, model_request_parameters, run_context) as stream:
                yield stream
        except BaseException as e:
            self._record(start, None, e)
            raise
        self._record(start, stream.get() if stream is not None else None)


@dataclass
class TimedToolset(WrapperToolset[Any]):
    """Appends a StepTiming(kind="tool") to `ctx.deps.steps` around every tool call (retries included)."""

    async def call_tool(self, name: str, tool_args: dict[str, Any], ctx: RunContext[Any], tool: ToolsetTool[Any]) -> Any:
        start = time.perf_counter()
        steps: list[StepTiming] = ctx.deps.steps
        call_id = ctx.tool_call_id
        try:
            result = await super().call_tool(name, tool_args, ctx, tool)
        except ModelRetry as e:
            steps.append(StepTiming(kind="tool", name=name, seconds=round(time.perf_counter() - start, 2),
                                    detail=f"retry: {result_summary(e.message)}", call_id=call_id))
            raise
        except BaseException as e:
            steps.append(StepTiming(kind="tool", name=name, seconds=round(time.perf_counter() - start, 2),
                                    detail=f"error: {type(e).__name__}", call_id=call_id))
            raise
        steps.append(StepTiming(kind="tool", name=name, seconds=round(time.perf_counter() - start, 2),
                                detail=result_summary(result), call_id=call_id))
        return result


def format_steps(steps: list[StepTiming]) -> str:
    """One line per step, for the terminal: `  12.3s  model  agent deepseek-v4-pro  -> suggest_meals  (1200 in / 80 out)`."""
    lines = []
    for s in steps:
        tokens = f"  ({s.input_tokens} in / {s.output_tokens} out)" if s.kind == "model" and s.input_tokens is not None else ""
        lines.append(f"  {s.seconds:6.1f}s  {s.kind:5}  {s.name:28}  {s.detail}{tokens}")
    # Recipe/vision model calls run inside a tool, so the tool step already contains their time.
    agent_s = sum(s.seconds for s in steps if s.kind == "model" and s.name.startswith("agent"))
    tools_s = sum(s.seconds for s in steps if s.kind == "tool")
    lines.append(f"  {agent_s + tools_s:6.1f}s  total ({agent_s:.1f}s agent model + {tools_s:.1f}s tools)")
    return "\n".join(lines)
