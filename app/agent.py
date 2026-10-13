"""The kitchen agent: a Pydantic AI agent on AGENT_MODEL that decides which tools to call.

The agent decides, the code verifies. Every tool here is a thin wrapper around a plain function in
`app/tools/`; nothing that must be correct is left to the model. The instructions are rebuilt on every
run so the current inventory, scan state and preferences are always in the prompt.

Entry point: `run_turn(store, session_id, message, images)`; it loads the session history, runs one
turn and saves the history back. `agent` is built without a model so importing this module needs no
API key; `run_turn` passes `agent_model()` (or the `model` given, e.g. a FunctionModel in tests).
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from pydantic_ai import Agent, ModelRetry, RunContext, ToolOutput, UsageLimits
from pydantic_ai.models import Model
from pydantic_ai.run import AgentRunResult
from pydantic_ai.toolsets import FunctionToolset

from app import config, llm
from app.models import (
    AgentReply, Constraints, InventoryChange, Location, MealCandidate, MissingReport, Recipe, StepTiming,
    SuggestResult, ValidationResult,
)
from app.store import Store
from app.timing import TimedModel, TimedToolset
from app.tools import checks, inventory, preferences, recipes, recognize

log = logging.getLogger(__name__)

# About 8 tool calls per turn (PRODUCT §5); the limit is a hard stop a little above that.
USAGE_LIMITS = UsageLimits(tool_calls_limit=10, request_limit=16)

INSTRUCTIONS = """\
You are the kitchen agent of one household. You know what is in their fridge, freezer and pantry \
(the inventory below) and you help in two ways: Mode A, "what can I cook?" (meals from what is there), \
and Mode B, "I want to make X" (what is missing for that dish). Answer in English, briefly.

Today is {today}.

Rules:
1. The inventory below is the only truth. Never claim an item is present unless it is listed there or \
was returned by a tool in this turn. After update_inventory or recognize_inventory, go by the state the \
tool returned.
2. If the message says the inventory changed ("we're out of eggs", "I bought chicken"), call \
update_inventory first, then continue with the request.
3. Mode A: call suggest_meals with the user's constraints. It returns candidates already checked by \
code: "passed" ones may be shown as they are (put 1 to 3 of their ids in meal_ids); "failed" ones must \
not be shown as Mode A meals: drop them, or call suggest_meals again with exclude if fewer than 1 passed, \
or present one as a Mode B answer with a shopping list. Prefer meals that use items marked USE SOON.
4. Mode B: call get_recipe, then compute_missing. For each missing essential ingredient, look in the \
inventory for a reasonable substitute (cottage cheese for ricotta, yogurt for sour cream) and list it in \
substitutions; use_instead must be an inventory item. shopping_list = the report's missing_essential \
minus the substituted items; check_first = the report's check_first. Put the recipe's id in meal_ids (that \
one dish). If nothing is missing, say so.
5. Pantry rule: while the pantry is NOT SCANNED, never say that a pantry-type ingredient (grains, pasta, \
canned goods, baking items, sauces, condiments, spices, snacks) is missing; it goes under check_first \
("check your pantry first"). In Mode A without a pantry scan, rely only on what was scanned plus the \
staples, and mention once that a pantry photo would give more options.
6. Photos: when the message says the user attached photos, call recognize_inventory first (it takes no \
arguments). Then say briefly how many items were found, ask about at most 3 uncertain items (in \
questions), and if a place is still NOT SCANNED ask once for a photo of it. The freezer is optional: \
never ask for it again once the user declined.
7. Respect the stored preferences. When the user states a lasting like or dislike ("the kids hated the \
eggplant", "we don't eat pork"), call save_preference with the ingredients to avoid, then confirm in one \
sentence what you will remember.
8. When the inventory has UNCERTAIN items, you may ask about at most 3 of them, in one message.
9. Keep message short (1 to 3 sentences). Meals go in meal_ids as the ids the tools returned (at most \
3); never repeat a recipe's ingredients or steps in message: the user sees the cards. At most 3 questions.
10. Never order, buy, remove or change anything the user did not ask for.
11. Use at most about 8 tool calls per turn. If you are stuck, answer with what you have and say what \
is missing.
12. Always finish the turn by calling the reply tool, even for a short acknowledgement ("Got it, no \
eggplant from now on."). Never answer in plain text.
"""


@dataclass
class Deps:
    """Per-run dependencies: the store, the photos attached to this message, and a recipe cache."""

    store: Store
    images: list[tuple[Path, Location]] = field(default_factory=list)
    # Every recipe returned by suggest_meals / get_recipe in this run, by id. compute_missing and
    # validate_suggestion take an id, and AgentReply.meal_ids refers to these; run_turn fills
    # AgentReply.meals from here, so the model never copies recipe content.
    recipes: dict[str, Recipe] = field(default_factory=dict)
    # Model overrides for the two LLM tools (tests pass FunctionModels; None = from config).
    recipe_model: Model | None = None
    vision_model: Model | None = None
    # Timing of every model call and tool call in this run, in order (filled by app/timing.py).
    steps: list[StepTiming] = field(default_factory=list)


OUTPUT_TOOL_NAME = "reply"

# Explicit tool output. With the default "auto" mode pydantic-ai also tries to parse a plain-text
# answer as JSON and sends the model a confusing "Invalid JSON" retry; in tool mode a plain-text answer
# gets "Please include your response in a tool call", which the model follows.
# The tools live in their own toolset so that TimedToolset can time every call (see app/timing.py).
toolset: FunctionToolset[Deps] = FunctionToolset(max_retries=2)

agent: Agent[Deps, AgentReply] = Agent(
    None,
    deps_type=Deps,
    toolsets=[TimedToolset(toolset)],
    output_type=ToolOutput(
        AgentReply, name=OUTPUT_TOOL_NAME,
        description="Your final answer to the user. Every turn must end with a call to this tool, "
        "even for a one-line acknowledgement; never answer in plain text.",
    ),
    name="kitchen-agent",
    retries=2,
)


@agent.instructions
async def instructions(ctx: RunContext[Deps]) -> str:
    store = ctx.deps.store
    summary = inventory.inventory_summary(inventory.get_inventory(store), store.load_scan_state())
    lines = [
        INSTRUCTIONS.format(today=date.today().isoformat()),
        f"Inventory (what the household has now; places marked NOT SCANNED are unknown):\n{summary}",
        f"Preferences:\n{preferences.preferences_summary(store)}",
    ]
    if ctx.deps.images:
        lines.append(f"The user attached {_photos_text(ctx.deps.images)} to this message.")
    return "\n\n".join(lines)


def _photos_text(images: list[tuple[Path, Location]]) -> str:
    n = len(images)
    places = ", ".join(dict.fromkeys(loc for _, loc in images))
    return f"{n} photo{'s' if n != 1 else ''} ({places})"


def user_prompt(message: str, images: list[tuple[Path, Location]]) -> str:
    """The user turn as the model sees it: an attachment note, then the text."""
    message = message.strip()
    if not images:
        return message
    note = f"[user attached {_photos_text(images)}]"
    return f"{note}\n{message}" if message else note


def _dish_key(name: str) -> str:
    return " ".join(name.lower().split())


def _remember(ctx: RunContext[Deps], recipe: Recipe) -> Recipe:
    ctx.deps.recipes[recipe.id] = recipe
    return recipe


def _find_recipe(ctx: RunContext[Deps], ref: str) -> Recipe:
    """The run's recipe with that id; a dish name (case/space-insensitive) is accepted as a fallback."""
    ref = ref.strip()
    recipe = ctx.deps.recipes.get(ref)
    if recipe is None:
        recipe = next((r for r in ctx.deps.recipes.values() if _dish_key(r.name) == _dish_key(ref)), None)
    if recipe is None:
        known = ", ".join(f"{r.id} ({r.name})" for r in ctx.deps.recipes.values()) or "none yet"
        raise ModelRetry(
            f"Unknown recipe {ref!r}: call suggest_meals or get_recipe first and use the id it returned. "
            f"Recipes from this turn: {known}."
        )
    return recipe


def _recipe_model(ctx: RunContext[Deps]) -> Model:
    model = ctx.deps.recipe_model or llm.recipe_model()
    return TimedModel(model, ctx.deps.steps, f"recipe {model.model_name}")


def _vision_model(ctx: RunContext[Deps]) -> Model:
    model = ctx.deps.vision_model or llm.vision_model()
    return TimedModel(model, ctx.deps.steps, f"vision {model.model_name}")


def _inventory_text(store: Store) -> str:
    return inventory.inventory_summary(inventory.get_inventory(store), store.load_scan_state())


def _log(tool: str, args: object, result: object) -> None:
    log.debug("tool %s(%s) -> %s", tool, args, result)


# --- tools (thin wrappers; the docstrings are part of the prompt) ----------------------------------
# All async: pydantic-ai runs sync tools in a worker thread, and the store's SQLite connection belongs
# to the event loop's thread.

@toolset.tool
async def recognize_inventory(ctx: RunContext[Deps]) -> str:
    """Recognize the food in the photos the user attached to this message and merge it into the inventory.

    Call this first, once, whenever the message says the user attached photos. Takes no arguments: the
    photos and their place tags (fridge / freezer / pantry) are already known. Returns what was found,
    which items are uncertain, and the updated inventory.
    """
    images = ctx.deps.images
    if not images:
        _log("recognize_inventory", "", "no photos")
        return "No photos are attached to this message. Ask the user to attach photos of the fridge, freezer or pantry."
    items = await recognize.recognize_inventory(images, store=ctx.deps.store, model=_vision_model(ctx))
    inventory.merge_recognized(ctx.deps.store, items)
    ctx.deps.images = []  # the same photos are not processed twice in one run
    uncertain = [i.display_name for i in items if i.uncertain]
    places = ", ".join(dict.fromkeys(loc for _, loc in images))
    lines = [f"Recognized {len(items)} items in {len(images)} photo(s) of: {places}."]
    if uncertain:
        lines.append(f"Uncertain ({len(uncertain)}): {', '.join(uncertain)}")
    lines.append(f"Inventory now:\n{_inventory_text(ctx.deps.store)}")
    out = "\n".join(lines)
    _log("recognize_inventory", f"{len(images)} photos", f"{len(items)} items, {len(uncertain)} uncertain")
    return out


@toolset.tool
async def get_inventory(ctx: RunContext[Deps]) -> str:
    """Return the current inventory (items by place, scan state, staples).

    The inventory is already in your instructions; call this only when you need the fresh state after
    a change in this turn.
    """
    out = _inventory_text(ctx.deps.store)
    _log("get_inventory", "", f"{len(out)} chars")
    return out


@toolset.tool
async def update_inventory(ctx: RunContext[Deps], changes: list[InventoryChange]) -> str:
    """Apply inventory changes the user asked for and return the updated inventory.

    Ops: add (name; optional qty_level plenty|some|low, location fridge|freezer|pantry, category,
    use_soon), remove, set_qty (qty_level; omit it to mean "none left"), set_use_soon (use_soon),
    rename (new_name). Use it when the user says the inventory changed ("we're out of eggs" -> remove
    egg; "bought chicken" -> add chicken; "the spinach should be used soon" -> set_use_soon). Only
    change what the user said.
    """
    inventory.update_inventory(ctx.deps.store, changes, source="chat")
    ops = ", ".join(f"{c.op} {c.name}" for c in changes)
    out = f"Applied: {ops}.\nInventory now:\n{_inventory_text(ctx.deps.store)}"
    _log("update_inventory", ops, f"{len(changes)} changes")
    return out


@toolset.tool
async def suggest_meals(
    ctx: RunContext[Deps],
    request: str = "",
    max_minutes: int | None = None,
    n: int = 5,
    exclude: list[str] | None = None,
) -> SuggestResult:
    """Generate up to n meal candidates from the inventory (Mode A), already checked by code.

    request: the user's wishes in free text ("quick, kids are eating, vegetarian"). max_minutes: time
    limit if the user gave one. exclude: dish names already shown or rejected. Candidates are built
    around inventory items and prefer USE SOON ones. "passed" candidates use only inventory items and
    staples and respect the preferences: show them by putting their ids in meal_ids. "failed" ones say
    why (missing items, pantry not scanned, a violated preference) and must not be shown as Mode A meals.
    """
    constraints = Constraints(text=request, max_minutes=max_minutes)
    store = ctx.deps.store
    found = await recipes.suggest_meals(store, constraints, n=n, exclude=exclude, model=_recipe_model(ctx))
    for r in found:
        _remember(ctx, r)
    out = checks.check_candidates(found, inventory.get_inventory(store), store.load_preferences(), store.load_scan_state())
    _log("suggest_meals", f"{request!r} max={max_minutes} n={n} exclude={exclude}",
         f"passed {[c.name for c in out.passed]} failed {[(c.name, c.reason) for c in out.failed]}")
    return out


@toolset.tool
async def get_recipe(ctx: RunContext[Deps], dish: str) -> MealCandidate:
    """The standard home recipe for a dish the user named (Mode B). Not checked: call compute_missing next.

    dish: the dish name as the user said it ("lasagna", "spaghetti bolognese"). Returns the recipe's id,
    ingredients and time; put the id in meal_ids when you present the dish.
    """
    recipe = _remember(ctx, await recipes.get_recipe(ctx.deps.store, dish, model=_recipe_model(ctx)))
    _log("get_recipe", dish, f"{recipe.id} {recipe.name}: {len(recipe.ingredients)} ingredients, {recipe.time_minutes} min")
    return MealCandidate.from_recipe(recipe)


@toolset.tool
async def compute_missing(ctx: RunContext[Deps], recipe_id: str) -> MissingReport:
    """What the household lacks for a recipe returned by get_recipe or suggest_meals in this turn (code, exact).

    recipe_id: the id the tool returned. missing_essential = definitely missing ("to
    buy"); check_first = pantry-type ingredients not confirmed because the pantry was not scanned ("check
    your pantry first"); missing_optional = optional extras. Staples, synonyms and plurals are handled.
    """
    store = ctx.deps.store
    report = checks.compute_missing(_find_recipe(ctx, recipe_id), inventory.get_inventory(store), store.load_scan_state())
    _log("compute_missing", recipe_id, report)
    return report


@toolset.tool
async def validate_suggestion(ctx: RunContext[Deps], recipe_id: str) -> ValidationResult:
    """Re-check a recipe from this turn against the inventory and the preferences (code, exact).

    suggest_meals already checks its candidates; use this after the inventory changed in this turn, or
    for a get_recipe dish you want to show as a Mode A meal. recipe_id: the id the tool returned.
    ok=True means every essential ingredient is in the inventory (or a staple) and no avoided ingredient
    is used. If not ok, reason says why (missing items, "pantry not scanned", violated preferences).
    """
    store = ctx.deps.store
    result = checks.validate_suggestion(
        _find_recipe(ctx, recipe_id), inventory.get_inventory(store), store.load_preferences(), store.load_scan_state(),
    )
    _log("validate_suggestion", recipe_id, "ok" if result.ok else f"FAILED: {result.reason}")
    return result


@toolset.tool
async def save_preference(ctx: RunContext[Deps], text: str, avoid: list[str]) -> str:
    """Remember a lasting like or dislike of the household, for this and all future sessions.

    text: the preference in a few words ("kids dislike eggplant", "no pork"). avoid: the ingredients to
    keep out of every meal from now on (["eggplant"]); empty if the preference bans nothing specific.
    Use it only for lasting preferences, not for tonight's wishes.
    """
    before = {p.id for p in ctx.deps.store.load_preferences()}
    pref = preferences.save_preference(ctx.deps.store, text, avoid)
    status = "Saved" if pref.id not in before else "Already noted"
    out = f"{status}: {pref.text}" + (f" (avoid: {', '.join(pref.avoid)})" if pref.avoid else "")
    _log("save_preference", f"{text!r} avoid={avoid}", out)
    return out


# --- running one turn -----------------------------------------------------------------------------

def fill_meals(reply: AgentReply, cache: dict[str, Recipe]) -> AgentReply:
    """Replace AgentReply.meals with the cached recipes named in meal_ids (in that order, deduped).

    Ids the run never produced are dropped with a warning; T2.2's output validator turns them into a
    ModelRetry before we get here.
    """
    meals, seen = [], set()
    for ref in reply.meal_ids:
        recipe = cache.get(ref.strip())
        if recipe is None:
            log.warning("reply names unknown recipe id %r; dropped", ref)
            continue
        if recipe.id not in seen:
            seen.add(recipe.id)
            meals.append(recipe)
    reply.meal_ids = [m.id for m in meals]
    reply.meals = meals
    return reply


@dataclass
class TurnResult:
    reply: AgentReply
    result: AgentRunResult[AgentReply]  # messages and usage, for the trace (T2.3)
    latency_s: float
    steps: list[StepTiming]  # every model call and tool call of the turn, timed, in order


async def run_turn(
    store: Store,
    session_id: str,
    message: str = "",
    images: list[tuple[Path, Location]] | None = None,
    *,
    model: Model | None = None,
    recipe_model: Model | None = None,
    vision_model: Model | None = None,
) -> TurnResult:
    """One chat turn: load the session history, run the agent, save the history, return the reply.

    `images` are the photos uploaded with this message, each with the place the user tagged.
    """
    images = list(images or [])
    if not message.strip() and not images:
        raise ValueError("a turn needs a message or at least one photo")
    deps = Deps(store=store, images=images, recipe_model=recipe_model, vision_model=vision_model)
    history = store.load_session_messages(session_id)
    model = model or llm.agent_model()
    start = time.perf_counter()
    result = await agent.run(
        user_prompt(message, images),
        deps=deps,
        model=TimedModel(model, deps.steps, f"agent {model.model_name}"),
        message_history=history or None,
        usage_limits=USAGE_LIMITS,
        model_settings=llm.thinking_settings(config.AGENT_THINKING),
    )
    latency = time.perf_counter() - start
    fill_meals(result.output, deps.recipes)
    store.save_session_messages(session_id, result.all_messages())
    usage = result.usage
    log.info("agent turn %s: %.1fs, %d requests, %d tool calls, %s in / %s out tokens, %d meals",
             session_id, latency, usage.requests, usage.tool_calls, usage.input_tokens, usage.output_tokens,
             len(result.output.meals))
    return TurnResult(reply=result.output, result=result, latency_s=latency, steps=deps.steps)
