"""Manual check of the agent (T2.1) against the real models, on the demo inventory of try_recipes.py.

Usage: uv run python scripts/try_agent.py "What can I cook tonight?" "I want to make lasagna" ...
Each argument is one user turn in the same session. Uses an in-memory store (fridge scanned, pantry
not, eggplant preference), so nothing on disk changes. Prints the tool calls, retries and the reply of
each turn. The full REPL with photos comes in T2.4 (scripts/chat.py).
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pydantic_ai.messages import ModelRequest, ModelResponse, RetryPromptPart, ToolCallPart  # noqa: E402

from app.agent import run_turn  # noqa: E402
from app.llm import setup_observability  # noqa: E402
from app.timing import format_steps  # noqa: E402
from try_recipes import demo_store  # noqa: E402

DEFAULT_TURNS = ["What can I cook tonight? Something under 30 minutes, the kids are eating.", "I want to make lasagna"]


def show(turn) -> None:
    usage = turn.result.usage
    print(f"({turn.latency_s:.1f}s, {usage.requests} requests, {usage.tool_calls} tool calls, "
          f"{usage.input_tokens} in / {usage.output_tokens} out tokens)")
    for m in turn.result.new_messages():
        if isinstance(m, ModelResponse):
            for p in m.parts:
                if isinstance(p, ToolCallPart):
                    args = p.args_as_json_str()
                    print(f"  -> {p.tool_name}({args[:140]}{'...' if len(args) > 140 else ''})")
        elif isinstance(m, ModelRequest):
            for p in m.parts:
                if isinstance(p, RetryPromptPart):
                    print(f"  !! retry: {str(p.content)[:140]}")
    print("timing:")
    print(format_steps(turn.steps))
    r = turn.reply
    print(f"message: {r.message}")
    for meal in r.meals:
        print(f"meal: {meal.name} ({meal.time_minutes} min) uses: {', '.join(meal.uses_from_inventory)}")
    if r.substitutions:
        print("substitutions: " + ", ".join(f"{s.use_instead} for {s.missing}" for s in r.substitutions))
    if r.shopping_list or r.check_first:
        print(f"to buy: {r.shopping_list}  check your pantry first: {r.check_first}")
    if r.questions:
        print(f"questions: {r.questions}")


async def main(turns: list[str]) -> None:
    setup_observability()
    logging.getLogger("app.agent").setLevel(logging.DEBUG)
    store = demo_store()
    for i, text in enumerate(turns, 1):
        print(f"\n=== turn {i}: {text}")
        show(await run_turn(store, "try-agent", text))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or DEFAULT_TURNS))
