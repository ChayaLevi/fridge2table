"""The trace of one agent turn: one short line per tool call, for the user (CLAUDE.md rule 7).

`build_trace(messages, steps, recipes)` walks the run's new messages, pairs every tool call with its
return (or retry), and writes a short args summary and result summary per call. Calls of the output
tool (`reply`) become "output check" items: "ok", "ok (fixed ...)" or "output check failed: ...".
The seconds of each call come from `TurnResult.steps` (matched by tool call id).

A plain function over pydantic-ai messages: no agent, no store, no model.
"""

import json
import re
from collections import Counter
from typing import Any

from pydantic import BaseModel
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, RetryPromptPart, ToolCallPart, ToolReturnPart

from app.models import MealCandidate, MissingReport, Recipe, StepTiming, SuggestResult, ToolTraceItem, ValidationResult

OUTPUT_TOOL_NAME = "reply"  # the agent's output tool (app.agent uses this constant)
OUTPUT_CHECK = "output check"
LIMIT = 100  # characters per summary

_OP_WORDS = {"add": "added", "remove": "removed", "set_qty": "qty set", "set_use_soon": "use-soon set", "rename": "renamed",
             "set_amount": "amount set"}


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


def _amount_arg(change: dict[str, Any]) -> str:
    """" 6 pcs" for a set_amount change ("" for other ops; " cleared" when the amount is cleared)."""
    if change.get("op") != "set_amount":
        return ""
    if not change.get("amount"):
        return " cleared"
    return f" {change['amount']:g} {change.get('unit') or ''}".rstrip() if isinstance(change["amount"], (int, float)) else ""


def args_summary(tool: str, args: dict[str, Any], recipes: dict[str, Recipe]) -> str:
    """"remove egg, add chicken", "'quick' max 30 min", "Lasagna", "'no pork' avoid pork"."""
    if tool == "update_inventory":
        text = ", ".join(f"{c.get('op')} {c.get('name')}" + _amount_arg(c)
                         for c in args.get("changes") or [] if isinstance(c, dict))
    elif tool == "mark_bought":
        names = [str(i.get("name")) for i in args.get("items") or [] if isinstance(i, dict)]
        text = ", ".join(names + (["everything on the list"] if args.get("everything") else []))
    elif tool == "suggest_meals":
        parts = [repr(args["request"])] if args.get("request") else []
        if args.get("max_minutes"):
            parts.append(f"max {args['max_minutes']} min")
        if args.get("exclude"):
            parts.append("exclude " + ", ".join(args["exclude"]))
        text = " ".join(parts)
    elif tool == "get_recipe":
        text = str(args.get("dish", ""))
    elif tool in ("compute_missing", "validate_suggestion", "mark_made"):
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
    if tool == "mark_bought":
        return short(str(content).splitlines()[0] if content else "bought"), False
    if tool == "mark_made":
        first = str(content).splitlines()[0] if content else ""
        return short(first.split("Deducted: ", 1)[-1].rstrip(".") if "Deducted: " in first else "made"), False
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
            text = f"{res.name}, {len(res.ingredients)} ingredients, {res.time_minutes} min"
            missing = MissingReport(missing_essential=res.to_buy, check_first=res.check_first, missing_optional=[])
            return short(f"{text}; {missing.summary()}"), False
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


# --- plain-language labels: the collapsed trace line the user reads (T4.4) ---------------------------

def _or(items: str) -> str:
    """"cream, parmesan, egg" -> "cream, parmesan or egg"."""
    names = [n.strip() for n in items.split(",") if n.strip()]
    return names[0] if len(names) < 2 else f"{', '.join(names[:-1])} or {names[-1]}"


def short_reason(reason: str) -> str:
    """A check's reason in a few words: "missing: cream" -> "no cream", "violates preferences: eggplant (..)"
    -> "avoids eggplant", "pantry not scanned: pasta not confirmed" -> "pasta not confirmed"."""
    out = []
    for part in reason.split(";"):
        part = part.strip().removeprefix("output check failed:").strip()
        if not part:
            continue
        if m := re.match(r"(?:.*? )?(not enough [^(]+?) \(", part):  # "not enough egg (have 4, need 5)"
            out.append(m.group(1))
        elif m := re.match(r"(?:.*? )?needs (.+?), not in inventory", part):
            out.append(f"no {_or(m.group(1))}")
        elif m := re.match(r"(?:.*? )?needs (.+?), not confirmed", part):
            out.append(f"{m.group(1)} not confirmed")
        elif m := re.match(r"missing: (.+)", part):
            out.append(f"no {_or(m.group(1))}")
        elif m := re.match(r"pantry not scanned: (.+)", part):
            out.append(m.group(1))
        elif m := re.match(r"(?:.*? )?violates preferences: ([^(]+)", part):
            out.append(f"avoids {m.group(1).strip()}")
        elif part.startswith("unknown meal id"):
            out.append("old meal id")
        elif m := re.match(r"substitute '(.+?)'", part):
            out.append(f"{m.group(1)} not in the inventory")
        elif part.startswith("message names items"):
            out.append("message listed the shopping items")
        elif re.match(r"\d+ meals", part):
            out.append("too many meals")
        elif re.match(r"\d+ questions", part):
            out.append("too many questions")
        elif not out:  # unknown wording; later fragments are the rest of a known problem ("; use only ids ...")
            out.append(short(part, 40))
    return ", ".join(dict.fromkeys(out))


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _missing_words(report: MissingReport) -> str:
    """"2 missing, 1 not confirmed" / "nothing missing". Counts before substitutes: "to buy" would
    contradict the shorter To buy list under the recipe."""
    parts = []
    if report.missing_essential:
        parts.append(f"{len(report.missing_essential)} missing")
    if report.check_first:
        parts.append(f"{len(report.check_first)} not confirmed")
    return ", ".join(parts) if parts else "nothing missing"


def step_label(tool: str, args: dict[str, Any], content: Any, failed: bool, detail: str = "") -> str:
    """One plain phrase per step: "updated the inventory (removed egg)", "5 ideas, 1 failed check (no cream)".

    `detail` is the output check's verdict, or the retry text when the call was sent back.
    """
    if failed and tool != OUTPUT_TOOL_NAME and detail:  # a tool call that was sent back
        return "invalid tool call, retried" if "invalid arguments" in detail else f"{tool.replace('_', ' ')} retried"
    if tool == OUTPUT_TOOL_NAME:
        if failed:
            return f"answer sent back ({short_reason(detail)})" if detail else "answer sent back"
        if "off topic" in detail:
            return "off topic"
        return "lists fixed by code" if "fixed" in detail else "checked by code"
    if tool == "update_inventory":
        changes = ", ".join(f"{_OP_WORDS.get(c.get('op'), c.get('op'))} {c.get('name')}"
                            for c in args.get("changes") or [] if isinstance(c, dict))
        return short(f"updated the inventory ({changes})" if changes else "updated the inventory", 80)
    if tool == "mark_made":
        first = str(content).splitlines()[0] if content else ""
        what = first.split("Deducted: ", 1)[-1].rstrip(".") if "Deducted: " in first else ""
        return short(f"took the ingredients out ({what})" if what else "took the ingredients out", 80)
    if tool == "mark_bought":
        first = str(content).splitlines()[0] if content else ""
        names = first.removeprefix("Bought: ").removesuffix(" (now plenty).")
        return short(f"marked bought ({names})" if first.startswith("Bought: ") else "marked bought", 80)
    if tool == "suggest_meals":
        res = _as(SuggestResult, content)
        if isinstance(res, SuggestResult):
            text = _plural(len(res.passed) + len(res.failed), "idea")
            if res.failed:
                why = short_reason(res.failed[0].reason)
                text += f", {_plural(len(res.failed), 'failed check')} ({why})"
            return text
        return "ideas"
    if tool == "get_recipe":
        res = _as(MealCandidate, content)
        if not isinstance(res, MealCandidate):
            return "recipe"
        # get_recipe also reports what is missing (T5.2: one agent call less than with compute_missing)
        missing = MissingReport(missing_essential=res.to_buy, check_first=res.check_first, missing_optional=[])
        return f"recipe for {res.name}, {_missing_words(missing)}"
    if tool == "compute_missing":
        res = _as(MissingReport, content)
        return _missing_words(res) if isinstance(res, MissingReport) else "checked what is missing"
    if tool == "validate_suggestion":
        res = _as(ValidationResult, content)
        if isinstance(res, ValidationResult):
            return "checked: ok" if res.ok else f"failed check ({short_reason(res.reason)})"
        return "checked"
    if tool == "recognize_inventory":
        text = str(content)
        if m := re.search(r"Recognized (\d+) items in (\d+) photo", text):
            label = f"read {_plural(int(m.group(2)), 'photo')}: {_plural(int(m.group(1)), 'item')}"
            if u := re.search(r"Uncertain \((\d+)\)", text):
                label += f", {u.group(1)} unsure"
            if s := re.search(r"Not seen in these photos.*?\((\d+)\)", text):
                label += f", {s.group(1)} not seen"
            return label
        return "no photos to read"
    if tool == "get_inventory":
        return "looked at the inventory"
    if tool == "save_preference":
        text = str(content)
        if text.startswith("Already noted"):
            return "already remembered"
        avoid = args.get("avoid") or []
        return f"remembered: no {', '.join(avoid)}" if avoid else "remembered a preference"
    return tool.replace("_", " ")


def trace_sentence(trace: list[ToolTraceItem]) -> str:
    """The collapsed trace line: "3 steps · updated the inventory (removed egg) → 5 ideas → checked by code"."""
    if not trace:
        return ""
    return f"{_plural(len(trace), 'step')} · " + " → ".join(t.label or t.tool for t in trace)


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
            content = None
            if isinstance(outcome, RetryPromptPart):
                if isinstance(outcome.content, str):  # ModelRetry from the tool or the output validator
                    reason = step.detail if (is_output and step) else f"retry: {outcome.content}"
                else:
                    reason = "retry: invalid arguments"
                result, failed, detail = short(reason), True, reason
            elif is_output:
                result, failed = (short(step.detail) if step else "ok"), False
                detail = step.detail if step else ""
            else:
                content = outcome.content
                result, failed = result_summary(call.tool_name, args, content)
                detail = ""
            trace.append(ToolTraceItem(
                tool=OUTPUT_CHECK if is_output else call.tool_name,
                args_summary=args_summary(call.tool_name, args, recipes),
                result_summary=result, failed=failed, seconds=step.seconds if step else None,
                label=step_label(call.tool_name, args, content, failed, detail),
            ))
    return trace


def format_trace(trace: list[ToolTraceItem]) -> str:
    """One line per item, for the terminal: `  ! output check(Carbonara) -> output check failed: ... (0.0s)`."""
    lines = []
    for t in trace:
        secs = f" ({t.seconds:.1f}s)" if t.seconds is not None else ""
        lines.append(f"  {'!' if t.failed else '-'} {t.tool}({t.args_summary}) -> {t.result_summary}{secs}")
    return "\n".join(lines)
