"""Agent scenario suite: real models, scripted conversations, expectations checked in code.

    uv run python eval/run_scenarios.py
    uv run python eval/run_scenarios.py --only 4,10 --repeat 3
    uv run python eval/run_scenarios.py --jobs 4

Scenarios are in eval/scenarios.yaml (format at the top of that file). Each scenario gets a fresh
in-memory store (or the store of the scenario named in `after`), is seeded, then its turns run through
`run_turn` against AGENT_MODEL / RECIPE_MODEL / VISION_MODEL. Each turn's reply, trace and the store
after the turn are checked against `expect`. Prints one line per turn (pass/fail, latency, tool calls,
failures), a markdown summary table, and saves the results as JSON in --out.
"""

import argparse
import asyncio
import json
import re
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402
from app.agent import run_opening, run_turn  # noqa: E402
from app.llm import setup_observability  # noqa: E402
from app.models import MAX_TO_BUY, AgentReply, InventoryChange, ToolTraceItem  # noqa: E402
from app.store import Store  # noqa: E402
from app.tools.checks import validate_suggestion  # noqa: E402
from app.tools.inventory import get_inventory, update_inventory  # noqa: E402
from app.tools.normalize import normalize, same_ingredient  # noqa: E402
from app.tools.preferences import save_preference  # noqa: E402
from app.trace import format_trace  # noqa: E402

SCENARIOS = Path(__file__).resolve().parent / "scenarios.yaml"
LOCATIONS = ("fridge", "freezer", "pantry")
EXPECT_KEYS = {
    "tools_called", "first_tool", "tools_not_called", "failed_check", "min_meals", "max_meals", "max_minutes",
    "meals_valid", "meals_must_not_contain", "shopping_list_contains", "shopping_list_must_not_contain",
    "shopping_list_empty", "check_first_contains", "check_first_must_not_contain", "check_first_empty",
    "substitution_for", "preference_saved", "inventory_lacks", "max_questions", "message_matches", "asks_for_photo",
    "message_must_not_match", "off_topic", "shopping_list_not_empty", "meals_fit_shop", "offer_shop",
}


# --- loading and seeding ---------------------------------------------------------------------------

def parse_item(spec: str | list) -> InventoryChange:
    """"spinach, vegetable, some, soon" / "pasta, pasta, plenty, pantry" -> an add change."""
    parts = [p.strip() for p in (spec.split(",") if isinstance(spec, str) else map(str, spec))]
    if len(parts) < 3:
        raise ValueError(f"inventory item needs name, category, qty: {spec!r}")
    name, category, qty, *flags = parts
    unknown = [f for f in flags if f not in (*LOCATIONS, "soon")]
    if unknown:
        raise ValueError(f"unknown flags {unknown} in {spec!r}")
    location = next((f for f in flags if f in LOCATIONS), "fridge")
    return InventoryChange(op="add", name=name, category=category, qty_level=qty, location=location,
                           use_soon="soon" in flags)


def load_suite(path: Path = SCENARIOS) -> tuple[dict[str, list], list[dict]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    inventories = data.get("inventories") or {}
    scenarios = data["scenarios"]
    ids = [s["id"] for s in scenarios]
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate scenario ids: {ids}")
    for s in scenarios:
        if s.get("after") is not None and s["after"] not in ids[: ids.index(s["id"])]:
            raise ValueError(f"scenario {s['id']}: after={s['after']} must name an earlier scenario")
        if not s.get("turns"):
            raise ValueError(f"scenario {s['id']}: no turns")
        for t in s["turns"]:
            unknown = set(t.get("expect") or {}) - EXPECT_KEYS
            if unknown:
                raise ValueError(f"scenario {s['id']}: unknown expect keys {sorted(unknown)}")
    return inventories, scenarios


def seed_store(store: Store, seed: dict, inventories: dict[str, list]) -> None:
    inv = seed.get("inventory")
    items = inventories[inv] if isinstance(inv, str) else (inv or [])
    adds = [parse_item(i) for i in [*items, *(seed.get("add") or [])]]
    removes = [InventoryChange(op="remove", name=n) for n in seed.get("remove") or []]
    if adds or removes:
        update_inventory(store, adds + removes, source="manual")
    for place in seed.get("scanned") or []:
        store.mark_scanned(place)
    for p in seed.get("preferences") or []:
        save_preference(store, p["text"], p.get("avoid") or [])


# --- checking one turn (plain function, unit-tested) -----------------------------------------------

def _has(names: list[str], wanted: str) -> bool:
    """Is `wanted` in `names`? Same canonical ingredient, or a whole-word part of a longer name
    ("pasta" in "pasta sheet", "ricotta" in "ricotta cheese")."""
    w = normalize(wanted)
    for n in names:
        if same_ingredient(n, wanted) or re.search(rf"\b{re.escape(w)}\b", normalize(n)):
            return True
    return False


def _in_order(actual: list[str], wanted: list[str]) -> bool:
    it = iter(actual)
    return all(any(a == w for a in it) for w in wanted)


def check_turn(expect: dict[str, Any], reply: AgentReply, trace: list[ToolTraceItem], store: Store) -> list[str]:
    """Every expectation that does not hold, as one short line each (empty = pass)."""
    fails: list[str] = []
    tools = [t.tool for t in trace]
    called = [t for t in tools if t != "output check"]
    meals = reply.meals
    text = " ".join([reply.message, *reply.questions])

    def fail(msg: str) -> None:
        fails.append(msg)

    if (w := expect.get("tools_called")) and not _in_order(tools, w):
        fail(f"tools_called {w} not in order in {tools}")
    if (w := expect.get("first_tool")) and (not called or called[0] != w):
        fail(f"first tool {called[0] if called else None!r}, expected {w!r}")
    for t in expect.get("tools_not_called") or []:
        if t in tools:
            fail(f"{t} was called")
    if expect.get("failed_check") and not any(t.failed for t in trace):
        fail("no failed check in the trace")

    if (n := expect.get("min_meals")) is not None and len(meals) < n:
        fail(f"{len(meals)} meals < {n}")
    if (n := expect.get("max_meals")) is not None and len(meals) > n:
        fail(f"{len(meals)} meals > {n}")
    if (n := expect.get("max_minutes")) is not None:
        for m in meals:
            if m.time_minutes > n:
                fail(f"{m.name} takes {m.time_minutes} min > {n}")
    for bad in expect.get("meals_must_not_contain") or []:
        for m in meals:
            if _has([i.name for i in m.ingredients], bad) or _has([m.name], bad):
                fail(f"{m.name} contains {bad}")
    mode_b = bool(reply.shopping_list or reply.check_first or reply.substitutions)
    if expect.get("meals_valid"):
        if mode_b:
            fail("expected Mode A meals, got a Mode B answer")
        inv, prefs, scan = get_inventory(store), store.load_preferences(), store.load_scan_state()
        for m in meals:
            res = validate_suggestion(m, inv, prefs, scan)
            if not res.ok:
                fail(f"{m.name} invalid: {res.reason}")

    if expect.get("meals_fit_shop"):  # Shopping OK mode: no avoided ingredient, at most MAX_TO_BUY to buy
        inv, prefs, scan = get_inventory(store), store.load_preferences(), store.load_scan_state()
        substituted = {s.missing for s in reply.substitutions}
        for m in meals:
            res = validate_suggestion(m, inv, prefs, scan)
            need = [n for n in res.missing_essential + res.check_first if n not in substituted]
            if res.violated_preferences or len(need) > MAX_TO_BUY:
                fail(f"{m.name} does not fit Shopping OK: {res.reason}")
    if expect.get("shopping_list_not_empty") and not reply.shopping_list:
        fail("shopping_list is empty")
    if (want := expect.get("offer_shop")) is not None and reply.offer_shop != want:
        fail(f"offer_shop is {reply.offer_shop}, expected {want}")

    for key, items in (("shopping_list", reply.shopping_list), ("check_first", reply.check_first)):
        for w in expect.get(f"{key}_contains") or []:
            if not _has(items, w):
                fail(f"{key} {items} lacks {w}")
        for w in expect.get(f"{key}_must_not_contain") or []:
            if _has(items, w):
                fail(f"{key} {items} contains {w}")
        if expect.get(f"{key}_empty") and items:
            fail(f"{key} not empty: {items}")
    subs = [s.missing for s in reply.substitutions]
    in_meals = [i.name for m in meals for i in m.ingredients]
    for w in expect.get("substitution_for") or []:
        # Only when the recipe needs it: some lasagna recipes have no ricotta at all.
        if _has(in_meals, w) and not _has(subs, w):
            fail(f"no substitution for {w} (substitutions: {[(s.missing, s.use_instead) for s in reply.substitutions]})")

    avoided = [a for p in store.load_preferences() for a in p.avoid]
    for w in expect.get("preference_saved") or []:
        if not _has(avoided, w):
            fail(f"no stored preference avoids {w} (avoid lists: {avoided})")
    inv_names = [i.name for i in get_inventory(store)]
    for w in expect.get("inventory_lacks") or []:
        if any(same_ingredient(n, w) for n in inv_names):
            fail(f"{w} still in the inventory")

    if (n := expect.get("max_questions")) is not None and len(reply.questions) > n:
        fail(f"{len(reply.questions)} questions > {n}")
    if (rx := expect.get("message_matches")) and not re.search(rx, text, re.I):
        fail(f"message does not match /{rx}/: {text!r}")
    if (rx := expect.get("message_must_not_match")) and re.search(rx, text, re.I):
        fail(f"message matches /{rx}/: {text!r}")
    if (want := expect.get("off_topic")) is not None and reply.off_topic != want:
        fail(f"off_topic is {reply.off_topic}, expected {want}: {text!r}")
    if place := expect.get("asks_for_photo"):
        photo = r"photo|picture|pic\b|snap|scan|shot"
        if not (re.search(place, text, re.I) and re.search(photo, text, re.I)):
            fail(f"does not ask for a {place} photo: {text!r}")
        asked = [q for q in reply.questions if re.search(place, q, re.I)]
        if len(asked) > 1:
            fail(f"asks for the {place} {len(asked)} times")
    return fails


# --- running ---------------------------------------------------------------------------------------

def _reply_line(reply: AgentReply) -> str:
    parts = [f"msg: {reply.message!r}"]
    if reply.meals:
        parts.append("meals: " + ", ".join(f"{m.name} ({m.time_minutes} min)" for m in reply.meals))
    if reply.substitutions:
        parts.append("subs: " + ", ".join(f"{s.use_instead} for {s.missing}" for s in reply.substitutions))
    if reply.shopping_list:
        parts.append(f"to buy: {reply.shopping_list}")
    if reply.check_first:
        parts.append(f"check first: {reply.check_first}")
    if reply.questions:
        parts.append(f"questions: {reply.questions}")
    return "\n      ".join(parts)


async def run_scenario(scenario: dict, inventories: dict, stores: dict[int, Store], run_tag: str) -> dict:
    sid = scenario["id"]
    if scenario.get("after") is not None:
        store = stores[scenario["after"]]
    else:
        store = Store(":memory:")
    stores[sid] = store
    seed_store(store, scenario.get("seed") or {}, inventories)
    session = f"scenario-{sid}-{run_tag}"
    turns = []
    for i, turn in enumerate(scenario["turns"], 1):
        if turn.get("new_session"):
            session = f"scenario-{sid}-{run_tag}-t{i}"
        for place in turn.get("scan") or []:
            store.mark_scanned(place)
        photos = [(ROOT / p, loc) for p, loc in turn.get("photos") or []]
        message = "(opening)" if turn.get("opening") else turn.get("message") or ""
        start = time.perf_counter()
        out: dict[str, Any] = {"turn": i, "message": message, "photos": len(photos)}
        try:
            if turn.get("opening"):
                res = await run_opening(store, session)
            else:
                res = await run_turn(store, session, message, photos, cook_mode=turn.get("cook_mode", "home"))
            out["latency_s"] = round(res.usage.latency_s, 1)
            out["tools"] = [t.tool for t in res.trace]
            out["trace"] = format_trace(res.trace)
            out["reply"] = _reply_line(res.reply)
            out["reply_json"] = res.reply.model_dump(mode="json", exclude={"meals"}) | {
                "meals": [{"name": m.name, "time_minutes": m.time_minutes,
                           "ingredients": [i.name for i in m.ingredients]} for m in res.reply.meals]}
            out["usage"] = res.usage.model_dump()
            out["failures"] = check_turn(turn.get("expect") or {}, res.reply, res.trace, store)
        except Exception as e:  # a crash (retry limit, usage limit, API error) is a failed turn
            out["latency_s"] = round(time.perf_counter() - start, 1)
            out["tools"] = []
            out["failures"] = [f"error: {type(e).__name__}: {e}"]
            out["traceback"] = traceback.format_exc()
        turns.append(out)
    return {"id": sid, "name": scenario["name"], "passed": all(not t["failures"] for t in turns), "turns": turns}


def print_result(r: dict, verbose: bool) -> None:
    status = "PASS" if r["passed"] else "FAIL"
    total = sum(t["latency_s"] for t in r["turns"])
    print(f"[{status}] #{r['id']} {r['name']} ({total:.1f} s)")
    for t in r["turns"]:
        mark = "ok" if not t["failures"] else "!!"
        print(f"   {mark} turn {t['turn']}: {t['latency_s']} s  tools: {' > '.join(t['tools']) or '-'}")
        for f in t["failures"]:
            print(f"      FAIL: {f}")
        if verbose or t["failures"]:
            if t.get("reply"):
                print(f"      {t['reply']}")
            if t.get("trace"):
                print("      " + t["trace"].replace("\n", "\n      "))


def summary_table(runs: list[list[dict]]) -> str:
    """One row per scenario: passes over the repeats and mean latency per turn."""
    by_id: dict[int, list[dict]] = {}
    for run in runs:
        for r in run:
            by_id.setdefault(r["id"], []).append(r)
    lines = ["| # | Scenario | Pass | Mean latency / turn |", "|---|---|---|---|"]
    for sid, rs in by_id.items():
        lat = [t["latency_s"] for r in rs for t in r["turns"]]
        passed = sum(r["passed"] for r in rs)
        lines.append(f"| {sid} | {rs[0]['name']} | {passed}/{len(rs)} | {sum(lat) / len(lat):.1f} s |")
    total = sum(r["passed"] for rs in by_id.values() for r in rs)
    count = sum(len(rs) for rs in by_id.values())
    lines.append(f"| | **total** | **{total}/{count}** | |")
    return "\n".join(lines)


def select(scenarios: list[dict], only: list[int] | None) -> list[dict]:
    """The chosen scenarios plus the ones they depend on (`after`), in file order."""
    if not only:
        return scenarios
    by_id = {s["id"]: s for s in scenarios}
    wanted = set(only)
    for sid in list(only):
        while (dep := by_id[sid].get("after")) is not None:
            wanted.add(dep)
            sid = dep
    return [s for s in scenarios if s["id"] in wanted]


async def run_suite(scenarios: list[dict], inventories: dict, jobs: int, run_tag: str, report_ids: set[int]) -> list[dict]:
    """Scenarios without `after` run in groups (a scenario and those that build on it, in order)."""
    groups: list[list[dict]] = []
    for s in scenarios:
        if s.get("after") is None:
            groups.append([s])
        else:
            next(g for g in groups if any(x["id"] == s["after"] for x in g)).append(s)
    sem = asyncio.Semaphore(jobs)
    stores: dict[int, Store] = {}

    async def run_group(group: list[dict]) -> list[dict]:
        async with sem:
            out = []
            for s in group:
                r = await run_scenario(s, inventories, stores, run_tag)
                if s["id"] in report_ids:
                    out.append(r)
            return out

    results = [r for g in await asyncio.gather(*(run_group(g) for g in groups)) for r in g]
    return sorted(results, key=lambda r: [s["id"] for s in scenarios].index(r["id"]))


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--only", help="comma-separated scenario ids (dependencies run too, unreported)")
    p.add_argument("--repeat", type=int, default=1)
    p.add_argument("--jobs", type=int, default=1, help="scenario groups run in parallel (latency is then less clean)")
    p.add_argument("-v", "--verbose", action="store_true", help="print reply and trace of passing turns too")
    p.add_argument("--file", type=Path, default=SCENARIOS)
    p.add_argument("--out", type=Path, default=ROOT / "eval" / "results")
    args = p.parse_args()
    setup_observability()

    inventories, scenarios = load_suite(args.file)
    only = [int(x) for x in args.only.split(",")] if args.only else None
    chosen = select(scenarios, only)
    report_ids = set(only) if only else {s["id"] for s in scenarios}
    print(f"agent {config.AGENT_MODEL}, recipes {config.RECIPE_MODEL}, vision {config.VISION_MODEL}; "
          f"{len(report_ids)} scenarios x {args.repeat}")

    runs = []
    for k in range(args.repeat):
        if args.repeat > 1:
            print(f"\n=== run {k + 1}/{args.repeat}")
        start = time.perf_counter()
        results = await run_suite(chosen, inventories, args.jobs, f"{datetime.now():%H%M%S}-{k}", report_ids)
        for r in results:
            print_result(r, args.verbose)
        passed = sum(r["passed"] for r in results)
        print(f"{passed}/{len(results)} passed in {time.perf_counter() - start:.0f} s")
        runs.append(results)

    print()
    print(summary_table(runs))
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"scenarios_{datetime.now():%Y%m%d_%H%M%S}.json"
    path.write_text(json.dumps({"agent_model": config.AGENT_MODEL, "recipe_model": config.RECIPE_MODEL,
                                "vision_model": config.VISION_MODEL, "runs": runs}, indent=2), encoding="utf-8")
    print(f"\nsaved {path.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
