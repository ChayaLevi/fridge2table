"""T0.4 smoke test against the real models (needs DEEPSEEK_API_KEY in .env).

    uv run python scripts/smoke.py [--image path/to/food.jpg]

Checks: VISION_MODEL lists items in a photo; AGENT_MODEL answers text, calls a tool and
returns a Pydantic output; RECIPE_MODEL returns a Pydantic output. Prints latency per call.
Exit code 1 if any check fails.
"""

import argparse
import io
import sys
import time
from pathlib import Path

from PIL import Image
from pydantic import BaseModel
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.messages import ToolCallPart

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.llm import agent_model, recipe_model, setup_observability, vision_model  # noqa: E402

DEFAULT_IMAGE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "coffee.jpg"
VISION_PROMPT = "List every food or drink item you can see in this photo, one per line, generic English names."


class ShelfCount(BaseModel):
    item: str
    count: int


class Dish(BaseModel):
    name: str
    ingredients: list[str]
    time_minutes: int


def count_on_shelf(item: str) -> int:
    """Return how many units of `item` are on the shelf."""
    return {"egg": 7, "eggs": 7}.get(item.lower().strip(), 0)


def load_jpeg(path: Path, max_side: int = 1600) -> bytes:
    img = Image.open(path).convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def timed(label: str, model_id: str, fn):
    start = time.perf_counter()
    try:
        result = fn()
    except Exception as e:  # report and carry on with the other checks
        print(f"[FAIL] {label} ({model_id}) {time.perf_counter() - start:.1f}s: {type(e).__name__}: {e}")
        return None
    usage = result.usage
    print(f"[ OK ] {label} ({model_id}) {time.perf_counter() - start:.1f}s, "
          f"{usage.input_tokens} in / {usage.output_tokens} out tokens")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    args = parser.parse_args()
    setup_observability()
    ok = True

    vision = Agent(vision_model())
    image = BinaryContent(data=load_jpeg(args.image), media_type="image/jpeg")
    r = timed("vision", config.VISION_MODEL, lambda: vision.run_sync([VISION_PROMPT, image]))
    if r:
        print("       " + r.output.strip().replace("\n", "\n       "))
    ok &= bool(r and r.output.strip())

    text = Agent(agent_model())
    r = timed("agent text", config.AGENT_MODEL,
              lambda: text.run_sync("In one sentence: a quick dinner with eggs and spinach?"))
    if r:
        print("       " + r.output.strip())
    ok &= bool(r and r.output.strip())

    tools = Agent(agent_model(), output_type=ShelfCount, tools=[count_on_shelf],
                  instructions="Always use the count_on_shelf tool; never guess counts.")
    r = timed("agent tool + structured output", config.AGENT_MODEL,
              lambda: tools.run_sync("How many eggs are on the shelf?"))
    if r:
        called = [p.tool_name for m in r.all_messages() for p in m.parts if isinstance(p, ToolCallPart)]
        print(f"       tool calls: {called}; output: {r.output!r}")
        passed = "count_on_shelf" in called and r.output.count == 7
        if not passed:
            print("[FAIL] expected a count_on_shelf call and count == 7")
        ok &= passed
    else:
        ok = False

    recipe = Agent(recipe_model(), output_type=Dish)
    r = timed("recipe structured output", config.RECIPE_MODEL,
              lambda: recipe.run_sync("A simple 15-minute spinach omelette."))
    if r:
        print(f"       {r.output!r}")
    ok &= bool(r and r.output.ingredients)

    print("ALL OK" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
