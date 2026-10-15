"""Latency of the user-facing turns (T5.2): real models, sequential, a fresh store per run.

    uv run python eval/run_latency.py
    uv run python eval/run_latency.py --repeat 5 --only mode_a,mode_b
    uv run python eval/run_latency.py --write

Cases: photos -> inventory (1 and 4 photos), the proactive opening, Mode A (Only what I have and
Shopping OK), Mode B, and the recipe steps of a meal card. Each run's `TurnResult.steps` is split into
agent model time, recipe/vision model time and the rest (code, tools, network). Prints a markdown table
(median / max per case, with the targets of docs/PRODUCT.md §10) and saves the raw runs as JSON;
`--write` also puts the table into eval/RESULTS.md between the latency markers.

Run it alone: parallel load on the API inflates every number. To compare models, set the env var
(e.g. `set AGENT_MODEL=deepseek-flash`) and run again.
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

from app import config  # noqa: E402
from app.agent import TurnResult, run_opening, run_turn  # noqa: E402
from app.llm import setup_observability  # noqa: E402
from app.models import StepTiming  # noqa: E402
from app.store import Store  # noqa: E402
from app.tools import recipes  # noqa: E402
from run_scenarios import load_suite, seed_store  # noqa: E402

PHOTO = ROOT / "tests" / "fixtures" / "coffee.jpg"  # stand-in until eval/fridges has real photos (T5.1)
RESULTS_MD = ROOT / "eval" / "RESULTS.md"
BEGIN, END = "<!-- latency:begin -->", "<!-- latency:end -->"
# docs/PRODUCT.md §10: photo upload -> inventory < 30 s; meal request -> reply < 25 s.
TARGETS = {"photo_1": 30, "photo_4": 30, "opening": 25, "mode_a": 25, "mode_a_shop": 25, "mode_b": 25}


@dataclass
class Breakdown:
    """One run of a case: total seconds and where they went (from TurnResult.steps)."""

    total: float
    agent: float  # agent model calls
    tools_llm: float  # recipe and vision model calls (inside tools)
    agent_calls: int
    last_agent: float  # the final agent call, which writes the reply (what streaming could show earlier)
    retries: int  # failed output checks (each costs one more agent call)
    input_tokens: int
    output_tokens: int

    @property
    def other(self) -> float:
        """Code, tool bodies and waiting outside the model calls."""
        return max(0.0, self.total - self.agent - self.tools_llm)


def breakdown(total: float, steps: list[StepTiming]) -> Breakdown:
    agent = [s for s in steps if s.kind == "model" and s.name.startswith("agent")]
    llm = [s for s in steps if s.kind == "model" and not s.name.startswith("agent")]
    return Breakdown(
        total=round(total, 2),
        agent=round(sum(s.seconds for s in agent), 2),
        tools_llm=round(sum(s.seconds for s in llm), 2),
        agent_calls=len(agent),
        last_agent=agent[-1].seconds if agent else 0.0,
        retries=sum(1 for s in steps if s.kind == "check" and "failed" in s.detail),
        input_tokens=sum(s.input_tokens or 0 for s in steps if s.kind == "model"),
        output_tokens=sum(s.output_tokens or 0 for s in steps if s.kind == "model"),
    )


def summarize(runs: list[Breakdown]) -> dict:
    """Median and max of the total, medians of the parts, over the runs of one case."""
    med = lambda xs: round(statistics.median(xs), 1)  # noqa: E731
    return {
        "n": len(runs),
        "median": med([r.total for r in runs]),
        "max": round(max(r.total for r in runs), 1),
        "agent": med([r.agent for r in runs]),
        "tools_llm": med([r.tools_llm for r in runs]),
        "other": med([r.other for r in runs]),
        "agent_calls": med([r.agent_calls for r in runs]),
        "last_agent": med([r.last_agent for r in runs]),
        "retries": sum(r.retries for r in runs),
    }


def table(summaries: dict[str, dict], labels: dict[str, str]) -> str:
    rows = ["| Case | Runs | Median | Max | Target | Agent model | Recipe/vision model | Other | Agent calls "
            "| Final agent call | Retries |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    for case, s in summaries.items():
        target = TARGETS.get(case)
        verdict = "-" if target is None else f"< {target} s {'✓' if s['max'] < target else '✗'}"
        rows.append(f"| {labels.get(case, case)} | {s['n']} | {s['median']} s | {s['max']} s | {verdict} | "
                    f"{s['agent']} s | {s['tools_llm']} s | {s['other']} s | {s['agent_calls']:g} | "
                    f"{s['last_agent']} s | {s['retries']} |")
    return "\n".join(rows)


def write_results(md: str, path: Path = RESULTS_MD) -> None:
    """Replace the latency block of RESULTS.md (or append it), keeping everything else."""
    block = f"{BEGIN}\n{md}\n{END}"
    text = path.read_text(encoding="utf-8") if path.exists() else "# Evaluation results\n"
    if BEGIN in text and END in text:
        head, rest = text.split(BEGIN, 1)
        text = head + block + rest.split(END, 1)[1]
    else:
        text = text.rstrip("\n") + "\n\n" + block + "\n"
    path.write_text(text, encoding="utf-8")


# --- the cases -------------------------------------------------------------------------------------

def demo_store(inventories: dict) -> Store:
    store = Store(":memory:")
    seed_store(store, {"inventory": "demo", "scanned": ["fridge"]}, inventories)
    return store


async def timed(coro: Awaitable[TurnResult]) -> Breakdown:
    turn = await coro
    return breakdown(turn.latency_s, turn.steps)


async def steps_case(inventories: dict) -> Breakdown:
    """What a tap on a meal card waits for: one recipe call (GET /recipe/{id}/steps)."""
    store = demo_store(inventories)
    [meal] = await recipes.suggest_meals(store, n=1)
    start = time.perf_counter()
    await recipes.get_steps(store, meal.id)
    total = time.perf_counter() - start
    return Breakdown(total=round(total, 2), agent=0.0, tools_llm=round(total, 2), agent_calls=0, last_agent=0.0,
                     retries=0, input_tokens=0, output_tokens=0)


def cases(inventories: dict, run_tag: str) -> dict[str, tuple[str, Callable[[], Awaitable[Breakdown]]]]:
    def turn(message: str, cook_mode: str = "home") -> Callable[[], Awaitable[Breakdown]]:
        return lambda: timed(run_turn(demo_store(inventories), run_tag, message, cook_mode=cook_mode))

    def photos(n: int) -> Callable[[], Awaitable[Breakdown]]:
        return lambda: timed(run_turn(Store(":memory:"), run_tag, "", [(PHOTO, "fridge")] * n))

    return {
        "photo_1": ("Photo -> inventory (1 photo)", photos(1)),
        "photo_4": ("Photo -> inventory (4 photos)", photos(4)),
        "opening": ("Opening (app opens)", lambda: timed(run_opening(demo_store(inventories), run_tag))),
        "mode_a": ("Mode A, Only what I have", turn("What can I cook tonight?")),
        "mode_a_shop": ("Mode A, Shopping OK", turn("What can I cook tonight?", "shop")),
        "mode_b": ("Mode B (lasagna)", turn("I want to make lasagna")),
        "steps": ("Recipe steps (tap a card)", lambda: steps_case(inventories)),
    }


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--repeat", type=int, default=3)
    p.add_argument("--only", help="comma-separated case names")
    p.add_argument("--write", action="store_true", help="put the table into eval/RESULTS.md")
    p.add_argument("--out", type=Path, default=ROOT / "eval" / "results")
    args = p.parse_args()
    setup_observability()

    inventories, _ = load_suite()
    run_tag = f"latency-{datetime.now():%H%M%S}"
    chosen = cases(inventories, run_tag)
    if args.only:
        chosen = {k: v for k, v in chosen.items() if k in args.only.split(",")}
    models = f"agent {config.AGENT_MODEL}, recipes {config.RECIPE_MODEL}, vision {config.VISION_MODEL}"
    print(f"{models}; {len(chosen)} cases x {args.repeat}, sequential")

    raw: dict[str, list[dict]] = {}
    summaries: dict[str, dict] = {}
    for case, (label, run) in chosen.items():
        runs = []
        for k in range(args.repeat):
            try:
                b = await run()
            except Exception as e:  # an API error is reported, not hidden in the numbers
                print(f"  {case} run {k + 1}: error {type(e).__name__}: {e}")
                continue
            runs.append(b)
            print(f"  {case} run {k + 1}: {b.total:.1f} s (agent {b.agent:.1f} s in {b.agent_calls} calls, "
                  f"recipe/vision {b.tools_llm:.1f} s, retries {b.retries})")
        if runs:
            raw[case] = [r.__dict__ for r in runs]
            summaries[case] = summarize(runs)

    labels = {k: v[0] for k, v in chosen.items()}
    md = (f"## Latency (T5.2), {datetime.now():%Y-%m-%d}\n\n{models}; thinking off; {args.repeat} sequential "
          f"runs per case; photo cases use the stand-in photo `tests/fixtures/coffee.jpg`.\n\n"
          f"{table(summaries, labels)}")
    print()
    print(md)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"latency_{datetime.now():%Y%m%d_%H%M%S}.json"
    path.write_text(json.dumps({"models": models, "summaries": summaries, "runs": raw}, indent=2), encoding="utf-8")
    print(f"\nsaved {path.relative_to(ROOT)}")
    if args.write:
        write_results(md)
        print(f"written to {RESULTS_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
