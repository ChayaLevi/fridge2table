"""The trace of one agent turn: one short line per tool call, for the user (CLAUDE.md rule 7).

`build_trace(messages, steps, recipes)` walks the run's new messages, pairs every tool call with its
return (or retry), and writes a short args summary and result summary per call. Calls of the output
tool (`reply`) become "output check" items: "ok", "ok (fixed ...)" or "output check failed: ...".
The seconds of each call come from `TurnResult.steps` (matched by tool call id).

A plain function over pydantic-ai messages: no agent, no store, no model.
"""

import json
from collections import Counter
from typing import Any

from pydantic import BaseModel
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, RetryPromptPart, ToolCallPart, ToolReturnPart

from app.models import MealCandidate, MissingReport, Recipe, StepTiming, SuggestResult, ToolTraceItem, ValidationResult

OUTPUT_TOOL_NAME = "reply"  # the agent's output tool (app.agent uses this constant)
OUTPUT_CHECK = "output check"
LIMIT = 100  # characters per summary

_OP_WORDS = {"add": "added", "remove": "removed", "set_qty": "qty set", "set_use_soon": "use-soon set", "rename": "renamed"}


def short(text: str, limit: int = LIMIT) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _as(model: type[BaseModel], content: Any) -> Any:
    """Tool returns are models inside a run, dicts after a round trip through the store."""
    if isinstance(content, dict):
        try:
            return model.model_validate(content)
        except ValueError:
            return content
    return content


def _recipe_name(ref: Any, recipes: dict[str, Recipe]) -> str:
    recipe = recipes.get(str(ref).strip())
    return recipe.name if recipe else str(ref)


def args_summary(tool: str, args: dict[str, Any], recipes: dict[str, Recipe]) -> str:
    """"remove egg, add chicken", "'quick' max 30 min", "Lasagna", "'no pork' avoid pork"."""
    if tool == "update_inventory":
        text = ", ".join(f"{c.get('op')} {c.get('name')}" for c in args.get("changes") or [] if isinstance(c, dict))
    elif tool == "suggest_meals":
        parts = [repr(args["request"])] if args.get("request") else []
        if args.get("max_minutes"):
            parts.append(f"max {args['max_minutes']} min")
        if args.get("exclude"):
            parts.append("exclude " + ", ".join(args["exclude"]))
        text = " ".join(parts)
    elif tool == "get_recipe":
        text = str(args.get("dish", ""))
    elif tool in ("compute_missing", "validate_suggestion"):
        text = _recipe_name(args.get("recipe_id", ""), recipes)
    elif tool == "save_preference":
        text = repr(args.get("text", "")) + (f" avoid {', '.join(args['avoid'])}" if args.get("avoid") else "")
    elif tool == OUTPUT_TOOL_NAME:
        meals = [_recipe_name(i, recipes) for i in args.get("meal_ids") or []]
        text = ", ".join(meals) if meals else "no meals"
        if args.get("shopping_list"):
            text += f"; to buy {len(args['shopping_list'])}"
    else:
        text = ", ".join(f"{k}={v}" for k, v in args.items())
    return short(text)


def result_summary(tool: str, args: dict[str, Any], content: Any) -> tuple[str, bool]:
    """(summary, failed): "removed 1, added 2", "5 candidates: 4 passed, 1 failed (...)", "FAILED: missing: cream"."""
    if tool == "update_inventory":
        ops = Counter(c.get("op") for c in args.get("changes") or [] if isinstance(c, dict))
        return ", ".join(f"{_OP_WORDS.get(op, op)} {n}" for op, n in ops.items()) or "no changes", False
    if tool == "suggest_meals":
        res = _as(SuggestResult, content)
        if isinstance(res, SuggestResult):
            n = len(res.passed) + len(res.failed)
            text = f"{n} candidates"
            if res.failed:
                failed = "; ".join(f"{c.name}: {c.reason}" for c in res.failed)
                text += f": {len(res.passed)} passed, {len(res.failed)} failed ({failed})"
            return short(text), bool(res.failed)
    if tool == "get_recipe":
        res = _as(MealCandidate, content)
        if isinstance(res, MealCandidate):
            return short(f"{res.name}, {len(res.ingredients)} ingredients, {res.time_minutes} min"), False
    if tool == "compute_missing":
        res = _as(MissingReport, content)
        if isinstance(res, MissingReport):
            return short(res.summary()), False
    if tool == "validate_suggestion":
        res = _as(ValidationResult, content)
        if isinstance(res, ValidationResult):
            return ("ok", False) if res.ok else (short(f"FAILED: {res.reason}"), True)
    if tool == "recognize_inventory":
        lines = str(content).splitlines()
        text = lines[0] if lines else ""
        uncertain = next((line.split(":")[0] for line in lines if line.startswith("Uncertain")), "")
        return short(f"{text} {uncertain.lower()}".strip()), False
    if tool == "get_inventory":
        return "current inventory", False
    if isinstance(content, BaseModel):
        return short(content.model_dump_json(exclude_defaults=True)), False
    return short(str(content).splitlines()[0] if str(content) else ""), False


def _call_args(call: ToolCallPart) -> dict[str, Any]:
    try:
        return call.args_as_dict()
    except (ValueError, json.JSONDecodeError):
        return {}


def build_trace(
    messages: list[ModelMessage], steps: list[StepTiming] | None = None, recipes: dict[str, Recipe] | None = None,
) -> list[ToolTraceItem]:
    """One ToolTraceItem per tool call in `messages` (a run's new_messages()), in call order.

    `recipes` (the run's cache, Deps.recipes) turns recipe ids into dish names; `steps` adds seconds and
    the output check's verdict. A call whose args failed validation gets "retry: invalid arguments".
    """
    recipes = recipes or {}
    steps_by_id = {s.call_id: s for s in steps or [] if s.call_id and s.kind in ("tool", "check")}
    outcomes: dict[str, ToolReturnPart | RetryPromptPart] = {}
    for m in messages:
        if isinstance(m, ModelRequest):
            for p in m.parts:
                if isinstance(p, (ToolReturnPart, RetryPromptPart)) and p.tool_call_id:
                    outcomes[p.tool_call_id] = p

    trace = []
    for m in messages:
        if not isinstance(m, ModelResponse):
            continue
        for call in m.parts:
            if not isinstance(call, ToolCallPart):
                continue
            args = _call_args(call)
            outcome = outcomes.get(call.tool_call_id)
            step = steps_by_id.get(call.tool_call_id)
            is_output = call.tool_name == OUTPUT_TOOL_NAME
            if outcome is None:  # not executed (the run ended first, or a sibling call was the output)
                continue
            if isinstance(outcome, RetryPromptPart):
                if isinstance(outcome.content, str):  # ModelRetry from the tool or the output validator
                    reason = step.detail if (is_output and step) else f"retry: {outcome.content}"
                else:
                    reason = "retry: invalid arguments"
                result, failed = short(reason), True
            elif is_output:
                result, failed = (short(step.detail) if step else "ok"), False
            else:
                result, failed = result_summary(call.tool_name, args, outcome.content)
            trace.append(ToolTraceItem(
                tool=OUTPUT_CHECK if is_output else call.tool_name,
                args_summary=args_summary(call.tool_name, args, recipes),
                result_summary=result, failed=failed, seconds=step.seconds if step else None,
            ))
    return trace


def format_trace(trace: list[ToolTraceItem]) -> str:
    """One line per item, for the terminal: `  ! output check(Carbonara) -> output check failed: ... (0.0s)`."""
    lines = []
    for t in trace:
        secs = f" ({t.seconds:.1f}s)" if t.seconds is not None else ""
        lines.append(f"  {'!' if t.failed else '-'} {t.tool}({t.args_summary}) -> {t.result_summary}{secs}")
    return "\n".join(lines)
