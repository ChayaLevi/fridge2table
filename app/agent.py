"""The kitchen agent: a Pydantic AI agent on AGENT_MODEL that decides which tools to call.

The agent decides, the code verifies. Every tool here is a thin wrapper around a plain function in
`app/tools/`; nothing that must be correct is left to the model. The instructions are rebuilt on every
run so the current inventory, scan state and preferences are always in the prompt.

Entry points: `run_turn(store, session_id, message, images)` loads the session history, runs one turn
and saves the history back; `run_opening(store, session_id)` is the proactive greeting when the app
opens (T4.1). `agent` is built without a model so importing this module needs no
API key; `run_turn` passes `agent_model()` (or the `model` given, e.g. a FunctionModel in tests).
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from pydantic_ai import Agent, ModelRetry, RunContext, ToolOutput, UsageLimits
from pydantic_ai.messages import (
    ModelMessage, ModelRequest, ModelResponse, SystemPromptPart, ToolCallPart, UserPromptPart,
)
from pydantic_ai.models import Model
from pydantic_ai.run import AgentRunResult
from pydantic_ai.toolsets import FunctionToolset

from app import config, llm
from app.models import (
    AgentReply, Constraints, InventoryChange, Location, MealCandidate, MissingReport, Recipe, StepTiming,
    SuggestResult, ToolTraceItem, TurnUsage, ValidationResult,
)
from app.store import Store
from app.timing import TimedModel, TimedToolset
from app.trace import OUTPUT_CHECK, OUTPUT_TOOL_NAME, build_trace
from app.tools import checks, inventory, preferences, recipes, recognize

log = logging.getLogger(__name__)

# The reply to an off-topic message, written by code (the model only sets AgentReply.off_topic).
OFF_TOPIC_MESSAGE = (
    "I can only help with cooking: what to make from your kitchen, recipes, ingredients and your "
    "shopping list. Try \"What can I cook tonight?\""
)

# The opening (T4.1). An empty inventory gets WELCOME_MESSAGE (no model call); otherwise the agent runs
# on OPENING_PROMPT, which is stored in the history as a system note, never as a user turn.
WELCOME_MESSAGE = (
    "Welcome! Take a photo of your fridge and one of your pantry, tag each with its place (tap the tag "
    "on the photo), and I'll tell you what you can cook."
)
OPENING_PROMPT = """\
[Note from the app, not from the user: the user just opened the app and has not written anything yet.]
Greet them in one short sentence and offer exactly one meal they can make now. Call suggest_meals once \
(request: "one quick everyday dish built around the USE SOON items", n=3) and put the id of the best \
passed candidate in meal_ids (one id only). Say which USE SOON item it uses ("Your spinach needs using: \
how about ...?"). If no item is marked USE SOON, offer one quick idea instead. No questions about \
uncertain items in this message."""

# About 8 tool calls per turn (PRODUCT §5); the limit is a hard stop a little above that.
USAGE_LIMITS = UsageLimits(tool_calls_limit=10, request_limit=16)

INSTRUCTIONS = """\
You are the kitchen agent of one household. You know what is in their fridge, freezer and pantry \
(the inventory below) and you help in two ways: Mode A, "what can I cook?" (meals from what is there), \
and Mode B, "I want to make X" (what is missing for that dish). Answer in English, briefly.

Today is {today}.

Scope: you only talk about food and this kitchen: cooking, meals, recipes, ingredients and substitutes, \
the inventory, food storage and freshness, diets and preferences, and grocery shopping. Anything else \
(general knowledge, news, politics, people, maths, code, other advice) is off topic: do not answer it, \
not even briefly or "just this once", and call no tools; reply with off_topic=true and message="" (the \
app sends a fixed message). If a message mixes both ("what's the capital of France, and what can I cook?"), \
answer only the kitchen part, never mention the other part, and leave off_topic false. Greetings and \
thanks are fine: answer in one short sentence, off_topic false.

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
4. Mode B: call get_recipe, then compute_missing. Then, before writing the reply, go through each missing \
essential ingredient and look in the inventory for a substitute that plays the same role in the dish \
(cottage cheese for ricotta, greek yogurt for sour cream, butter for oil, one hard cheese for another). \
Do not swap the ingredient that defines the dish (no chicken in a beef bolognese, no other noodles for \
lasagna sheets). Every substitute you suggest goes in substitutions (use_instead must be an inventory \
item), never only in message. shopping_list = the report's missing_essential minus the substituted \
items; check_first = the report's check_first. Put the recipe's id in meal_ids (that one dish). The app \
shows To buy and Check your pantry first under the recipe. So in Mode B, message is one sentence that \
names no ingredient except the substitution pairs, and gives no counts: "You can make it with your \
cottage cheese instead of ricotta; the shopping list is below." / "You have everything for it." / "You \
need a few things for it; the list is below." If nothing is missing, say so.
5. Pantry rule: while the pantry is NOT SCANNED, never say that a pantry-type ingredient (grains, pasta, \
canned goods, baking items, sauces, condiments, spices, snacks) is missing; it goes under check_first \
("check your pantry first"). In Mode A without a pantry scan, rely only on what was scanned plus the \
staples, and mention once that a pantry photo would give more options.
6. Photos: when the message says the user attached photos, call recognize_inventory first (it takes no \
arguments). Then say briefly how many items were found, ask about at most 3 uncertain items (in \
questions), and if a place is still NOT SCANNED ask once for a photo of it. If the tool lists items not \
seen in these photos, say so in one sentence ("I didn't see the milk and the yogurt this time: tick or \
remove them in the list") with no question per item: the app shows the user a list to confirm. The \
freezer is optional: never ask for it again once the user declined.
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
            f"Recipes from this turn and your last reply: {known}."
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
    which items are uncertain, which earlier items of those places were not seen this time (kept, marked
    for the user to check), and the updated inventory.
    """
    images = ctx.deps.images
    if not images:
        _log("recognize_inventory", "", "no photos")
        return "No photos are attached to this message. Ask the user to attach photos of the fridge, freezer or pantry."
    items = await recognize.recognize_inventory(images, store=ctx.deps.store, model=_vision_model(ctx))
    scanned = list(dict.fromkeys(loc for _, loc in images))
    now = inventory.merge_recognized(ctx.deps.store, items, scanned)
    ctx.deps.images = []  # the same photos are not processed twice in one run
    uncertain = [i.display_name for i in items if i.uncertain]
    not_seen = [i.display_name for i in now if i.not_seen and i.location in scanned]
    lines = [f"Recognized {len(items)} items in {len(images)} photo(s) of: {', '.join(scanned)}."]
    if uncertain:
        lines.append(f"Uncertain ({len(uncertain)}): {', '.join(uncertain)}")
    if not_seen:
        lines.append(f"Not seen in these photos, kept and marked for the user to check ({len(not_seen)}): "
                     f"{', '.join(not_seen)}")
    lines.append(f"Inventory now:\n{_inventory_text(ctx.deps.store)}")
    out = "\n".join(lines)
    _log("recognize_inventory", f"{len(images)} photos",
         f"{len(items)} items, {len(uncertain)} uncertain, {len(not_seen)} not seen")
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


# --- output validator (the self-correction guarantee) ---------------------------------------------

@agent.output_validator
async def check_output(ctx: RunContext[Deps], reply: AgentReply) -> AgentReply:
    """Re-check the final reply in code (checks.check_reply); a failure goes back to the model as ModelRetry.

    An off-topic reply (off_topic=True) is replaced by OFF_TOPIC_MESSAGE, with no meals or lists.

    Meals are looked up by id in the run's recipe cache: an unknown id, a Mode A meal that no longer
    passes validate_suggestion, a substitute not in the inventory, or more than 3 meals / questions is a
    retry. Mode B lists (shopping_list, check_first) are recomputed and replaced in code. Every check is
    recorded in ctx.deps.steps ("output check failed: ..." for the trace).
    """
    if ctx.partial_output:
        return reply
    start = time.perf_counter()
    if reply.off_topic:  # the model's own text is never shown for an off-topic message
        ctx.deps.steps.append(StepTiming(kind="check", name=OUTPUT_CHECK, seconds=0.0,
                                         detail="ok (off topic: fixed reply)", call_id=ctx.tool_call_id))
        return AgentReply(message=OFF_TOPIC_MESSAGE, off_topic=True)
    store = ctx.deps.store
    result = checks.check_reply(
        reply, ctx.deps.recipes, inventory.get_inventory(store), store.load_preferences(), store.load_scan_state(),
    )

    def record(detail: str) -> None:
        ctx.deps.steps.append(StepTiming(kind="check", name=OUTPUT_CHECK,
                                         seconds=round(time.perf_counter() - start, 2), detail=detail,
                                         call_id=ctx.tool_call_id))

    if not result.ok:
        problems = "; ".join(result.problems)
        record(f"output check failed: {problems}")
        log.info("output check failed: %s", problems)
        raise ModelRetry(f"Your reply was not sent. Fix it and call {OUTPUT_TOOL_NAME} again: {problems}.")
    if result.fixes:
        log.info("output check fixed: %s", "; ".join(result.fixes))
    record("ok" + (f" (fixed {'; '.join(result.fixes)})" if result.fixes else ""))
    return result.reply


# --- running one turn -----------------------------------------------------------------------------

def fill_meals(reply: AgentReply, cache: dict[str, Recipe]) -> AgentReply:
    """Replace AgentReply.meals with the cached recipes named in meal_ids (in that order, deduped).

    Ids the run never produced are dropped with a warning; the output validator (check_output) already
    turned them into a ModelRetry, so this only matters for replies built outside a run.
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
    result: AgentRunResult[AgentReply] | None  # the run's messages and usage; None when no model ran
    latency_s: float
    steps: list[StepTiming]  # every model call and tool call of the turn, timed, in order
    trace: list[ToolTraceItem]  # one short line per tool call and output check, for the user
    usage: TurnUsage  # latency and tokens of the turn (T5.2)


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
    return await _run(store, session_id, user_prompt(message, images), images,
                      model=model, recipe_model=recipe_model, vision_model=vision_model)


def has_items(store: Store) -> bool:
    """True when the inventory has anything beyond the staples."""
    return any(i.source != "staple" for i in inventory.get_inventory(store))


async def run_opening(
    store: Store,
    session_id: str,
    *,
    model: Model | None = None,
    recipe_model: Model | None = None,
) -> TurnResult:
    """The proactive greeting when the app opens (T4.1).

    Empty inventory: WELCOME_MESSAGE, no model call, nothing stored. Otherwise the agent runs on
    OPENING_PROMPT (one validated meal, preferring USE SOON items); in the stored history that prompt
    becomes a system note, so the session holds no user turn the user did not write.
    """
    if not has_items(store):
        return TurnResult(reply=AgentReply(message=WELCOME_MESSAGE), result=None, latency_s=0.0, steps=[], trace=[],
                          usage=TurnUsage(latency_s=0.0, requests=0, tool_calls=0, input_tokens=0, output_tokens=0))
    return await _run(store, session_id, OPENING_PROMPT, [], model=model, recipe_model=recipe_model, hidden=True)


def last_reply_recipes(store: Store, history: list[ModelMessage]) -> dict[str, Recipe]:
    """The recipes of the session's last reply (its meal_ids), from the store, by id.

    Preloaded into the run's cache so "yes, that one" can reuse the id the user saw; the output check
    still re-validates such a meal against the current inventory.
    """
    for msg in reversed(history):
        if not isinstance(msg, ModelResponse):
            continue
        for part in msg.parts:
            if isinstance(part, ToolCallPart) and part.tool_name == OUTPUT_TOOL_NAME:
                ids = part.args_as_dict().get("meal_ids") or []
                recipes = {i: r for i in ids if isinstance(i, str) and (r := store.load_recipe(i.strip()))}
                return {r.id: r for r in recipes.values()}
    return {}


def _hide_prompt(messages: list[ModelMessage], prompt: str) -> None:
    """Turn the run's user prompt into a system note, in place (the opening is not a user turn)."""
    for msg in messages:
        if isinstance(msg, ModelRequest):
            for k, part in enumerate(msg.parts):
                if isinstance(part, UserPromptPart) and part.content == prompt:
                    msg.parts[k] = SystemPromptPart(content=prompt)
                    return


async def _run(
    store: Store,
    session_id: str,
    prompt: str,
    images: list[tuple[Path, Location]],
    *,
    model: Model | None,
    recipe_model: Model | None,
    vision_model: Model | None = None,
    hidden: bool = False,
) -> TurnResult:
    history = store.load_session_messages(session_id)
    deps = Deps(store=store, images=images, recipe_model=recipe_model, vision_model=vision_model,
                recipes=last_reply_recipes(store, history))
    model = model or llm.agent_model()
    start = time.perf_counter()
    result = await agent.run(
        prompt,
        deps=deps,
        model=TimedModel(model, deps.steps, f"agent {model.model_name}"),
        message_history=history or None,
        usage_limits=USAGE_LIMITS,
        model_settings=llm.thinking_settings(config.AGENT_THINKING),
    )
    latency = time.perf_counter() - start
    fill_meals(result.output, deps.recipes)
    messages = result.all_messages()
    if hidden:
        _hide_prompt(result.new_messages(), prompt)
    store.save_session_messages(session_id, messages)
    u = result.usage
    usage = TurnUsage(latency_s=round(latency, 2), requests=u.requests, tool_calls=u.tool_calls,
                      input_tokens=u.input_tokens, output_tokens=u.output_tokens)
    trace = build_trace(result.new_messages(), deps.steps, deps.recipes)
    log.info("agent %s %s: %.1fs, %d requests, %d tool calls, %s in / %s out tokens, %d meals",
             "opening" if hidden else "turn", session_id, latency, usage.requests, usage.tool_calls,
             usage.input_tokens, usage.output_tokens, len(result.output.meals))
    return TurnResult(reply=result.output, result=result, latency_s=latency, steps=deps.steps, trace=trace, usage=usage)
