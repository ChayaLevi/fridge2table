"""T2.1: the agent runs with scripted models (no network) on a fixture inventory and returns an AgentReply.

Latency fix (2026-10-13): the reply names meals by id (meal_ids), suggest_meals checks its candidates
itself, and every model/tool call is timed (TurnResult.steps).
"""

from datetime import datetime
from pathlib import Path

import pytest
from pydantic_ai import UsageLimits
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import (
    ModelMessage, ModelRequest, ModelResponse, RetryPromptPart, ToolCallPart, ToolReturnPart, UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app import agent as agent_module
from app.agent import Deps, USAGE_LIMITS, agent, fill_meals, run_turn, user_prompt
from app.models import AgentReply, InventoryChange, Preference, Recipe, SuggestResult
from app.store import Store
from app.tools.inventory import get_inventory, update_inventory

FIXTURE_IMAGE = Path(__file__).parent / "fixtures" / "coffee.jpg"


# --- scripted models -------------------------------------------------------------------------------

def scripted(*steps):
    """A FunctionModel that answers call k with step k: ("tool", args) -> tool call, dict -> final AgentReply.

    Records what the model saw: `seen` holds (instructions, last request parts) per call.
    """
    seen: list[tuple[str | None, list]] = []

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append((info.instructions, list(messages[-1].parts)))
        k = len(seen) - 1
        if k >= len(steps):
            raise AssertionError(f"model called {k + 1} times, only {len(steps)} steps scripted")
        step = steps[k]
        if isinstance(step, dict):
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, step)])
        name, args = step
        return ModelResponse(parts=[ToolCallPart(name, args)])

    return FunctionModel(fn), seen


def structured(output: dict):
    """A FunctionModel that always returns `output` as the structured result (for the recipe/vision tools)."""

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    return FunctionModel(fn)


def ing(name, category="other", essential=True):
    return {"name": name, "amount": "1", "essential": essential, "category": category}


def dish(name, *ingredients, minutes=20):
    return {"name": name, "ingredients": list(ingredients), "time_minutes": minutes}


OMELETTE = dish("Spinach omelette", ing("egg", "egg"), ing("spinach", "vegetable"), ing("salt", "spice"))
CARBONARA = dish("Carbonara", ing("pasta", "pasta"), ing("egg", "egg"), ing("cream", "dairy"))
LASAGNA = dish("Lasagna", ing("pasta", "pasta"), ing("ricotta", "dairy"), ing("ground beef", "meat"),
               ing("egg", "egg"), minutes=60)

RECIPE_MODEL = structured({"recipes": [OMELETTE, CARBONARA]})
LASAGNA_MODEL = structured(LASAGNA)
VISION_MODEL = structured({"items": [
    {"name": "milk", "display_name": "Milk", "category": "dairy", "qty_level": "some", "confidence": 0.9},
    {"name": "white container", "display_name": "white container", "category": "other", "qty_level": "some",
     "confidence": 0.3, "note": "possibly leftover rice"},
]})


def reply(**kw) -> dict:
    return {"message": "here you go", **kw}


def ids_by_name(parts) -> dict[str, str]:
    """dish name -> recipe id, from the suggest_meals / get_recipe returns the model saw."""
    out = {}
    for p in parts:
        if not isinstance(p, ToolReturnPart):
            continue
        if isinstance(p.content, SuggestResult):
            out.update({c.name: c.id for c in p.content.passed + p.content.failed})
        elif hasattr(p.content, "id"):
            out[p.content.name] = p.content.id
    return out


def tool_returns(parts) -> dict[str, object]:
    return {p.tool_name: p.content for p in parts if isinstance(p, ToolReturnPart)}


@pytest.fixture
def store():
    s = Store(":memory:")
    s.mark_scanned("fridge")
    update_inventory(s, [
        InventoryChange(op="add", name="spinach", category="vegetable", use_soon=True),
        InventoryChange(op="add", name="eggs", category="egg", qty_level="plenty"),
        InventoryChange(op="add", name="cottage cheese", category="dairy"),
    ])
    s.add_preference(Preference(id="p1", text="kids dislike eggplant", avoid=["eggplant"],
                                created_at=datetime(2026, 10, 13)))
    yield s
    s.close()


# --- instructions and prompt -----------------------------------------------------------------------

async def test_instructions_carry_rules_inventory_scan_state_and_preferences(store):
    model, seen = scripted(reply())
    await run_turn(store, "s1", "hi", model=model)
    instructions, _ = seen[0]
    assert "Mode A" in instructions and "Mode B" in instructions and "check_first" in instructions
    assert "spinach (some, USE SOON)" in instructions
    assert "pantry (NOT SCANNED)" in instructions and "fridge (scanned" in instructions
    assert "staples (assumed present)" in instructions
    assert "kids dislike eggplant (avoid: eggplant)" in instructions
    assert "The user attached" not in instructions  # no photos on this turn


async def test_instructions_are_rebuilt_each_run(store):
    model, seen = scripted(reply(), reply())
    await run_turn(store, "s1", "hi", model=model)
    update_invent = update_inventory(store, [InventoryChange(op="add", name="tofu", category="other")])
    assert any(i.name == "tofu" for i in update_invent)
    await run_turn(store, "s1", "again", model=model)
    assert "tofu" not in seen[0][0] and "tofu" in seen[1][0]


def test_user_prompt_mentions_photos():
    assert user_prompt("dinner?", []) == "dinner?"
    imgs = [(FIXTURE_IMAGE, "fridge"), (FIXTURE_IMAGE, "fridge"), (FIXTURE_IMAGE, "pantry")]
    assert user_prompt("", imgs) == "[user attached 3 photos (fridge, pantry)]"
    assert user_prompt("here", [(FIXTURE_IMAGE, "fridge")]) == "[user attached 1 photo (fridge)]\nhere"


async def test_turn_needs_message_or_photos(store):
    with pytest.raises(ValueError):
        await run_turn(store, "s1", "   ", model=scripted()[0])


# --- Mode A ----------------------------------------------------------------------------------------

async def test_mode_a_update_then_suggest_checks_candidates_itself(store):
    model, seen = scripted(
        ("update_inventory", {"changes": [{"op": "remove", "name": "eggs"}]}),
        ("suggest_meals", {"request": "quick", "max_minutes": 30}),
        ("validate_suggestion", {"recipe_id": "Carbonara"}),  # a name is accepted as a fallback
        reply(meal_ids=["__omelette__"]),
    )
    turn = await run_turn(store, "s1", "we're out of eggs, something quick", model=model, recipe_model=RECIPE_MODEL)

    assert isinstance(turn.reply, AgentReply)
    assert turn.latency_s >= 0
    # the inventory change was applied and reported back
    assert not any(i.name == "egg" for i in get_inventory(store))
    update_out = tool_returns(seen[1][1])["update_inventory"]
    assert update_out.startswith("Applied: remove eggs.") and "egg" not in update_out.split("Inventory now:")[1]
    # suggest_meals returned checked candidates (no steps, no full recipes): egg is gone, cream never
    # was there, pasta unconfirmed -> both failed, with the reason
    result = tool_returns(seen[2][1])["suggest_meals"]
    assert isinstance(result, SuggestResult) and result.passed == []
    assert [(f.name, f.reason) for f in result.failed] == [
        ("Spinach omelette", "missing: egg"),
        ("Carbonara", "missing: egg, cream; pantry not scanned: pasta not confirmed"),
    ]
    # validate_suggestion (by name here) gives the same verdict
    check = tool_returns(seen[3][1])["validate_suggestion"]
    assert check.ok is False and check.missing_essential == ["egg", "cream"] and check.check_first == ["pasta"]
    # an id the run never produced is dropped by fill_meals (T2.2 will make it a retry)
    assert turn.reply.meals == [] and turn.reply.meal_ids == []


async def test_mode_a_reply_by_id_is_filled_from_the_cache(store):
    captured: dict[str, str] = {}

    def fn(messages, info):
        if sum(1 for m in messages if isinstance(m, ModelRequest)) == 1:
            return ModelResponse(parts=[ToolCallPart("suggest_meals", {"request": "quick"})])
        ids = ids_by_name(messages[-1].parts)
        captured.update(ids)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
                                                 reply(meal_ids=[ids["Spinach omelette"], ids["Spinach omelette"]]))])

    turn = await run_turn(store, "s1", "dinner?", model=FunctionModel(fn), recipe_model=RECIPE_MODEL)
    # the model only sent ids; code filled the full recipes (deduped) from the run's cache
    assert [m.name for m in turn.reply.meals] == ["Spinach omelette"]
    assert turn.reply.meal_ids == [captured["Spinach omelette"]]
    assert isinstance(turn.reply.meals[0], Recipe) and turn.reply.meals[0].uses_from_inventory == ["spinach", "egg"]
    assert turn.reply.meals[0].steps == []  # steps come on demand (get_steps)
    # the candidates the model saw: omelette passed (egg + spinach present, salt is a staple), carbonara failed
    assert store.load_recipe(captured["Spinach omelette"]).name == "Spinach omelette"  # saved for get_steps
    # timing: every model call and tool call, in order
    kinds = [(s.kind, s.name) for s in turn.steps]
    assert kinds == [
        ("model", "agent function:fn:"), ("model", "recipe function:fn:"), ("tool", "suggest_meals"),
        ("model", "agent function:fn:"),
    ]
    assert all(s.seconds >= 0 for s in turn.steps)
    assert turn.steps[0].detail == "-> suggest_meals" and turn.steps[-1].detail == "-> reply"
    assert turn.steps[2].detail.startswith("passed")


def test_fill_meals_keeps_order_drops_unknown_and_duplicates():
    a = Recipe(name="A", ingredients=[], time_minutes=5)
    b = Recipe(name="B", ingredients=[], time_minutes=5)
    r = fill_meals(AgentReply(message="m", meal_ids=[b.id, "nope", a.id, b.id]), {a.id: a, b.id: b})
    assert [m.name for m in r.meals] == ["B", "A"] and r.meal_ids == [b.id, a.id]


def test_agent_reply_schema_has_meal_ids_not_meals():
    schema = AgentReply.model_json_schema()
    assert "meal_ids" in schema["properties"] and "meals" not in schema["properties"]


async def test_validate_unknown_recipe_asks_model_to_retry(store):
    model, seen = scripted(
        ("validate_suggestion", {"recipe_id": "Moussaka"}),
        ("suggest_meals", {}),
        ("validate_suggestion", {"recipe_id": "spinach OMELETTE"}),  # name fallback is case/space-insensitive
        reply(),
    )
    await run_turn(store, "s1", "dinner?", model=model, recipe_model=RECIPE_MODEL)
    retry = [p for p in seen[1][1] if isinstance(p, RetryPromptPart)]
    assert len(retry) == 1 and "Unknown recipe 'Moussaka'" in retry[0].content and "none yet" in retry[0].content
    assert tool_returns(seen[3][1])["validate_suggestion"].ok is True


# --- Mode B ----------------------------------------------------------------------------------------

async def test_mode_b_get_recipe_then_compute_missing(store):
    seen_ids: dict[str, str] = {}

    def fn(messages, info):
        parts = messages[-1].parts
        seen_ids.update(ids_by_name(parts))
        n = sum(1 for m in messages if isinstance(m, ModelRequest))
        if n == 1:
            return ModelResponse(parts=[ToolCallPart("get_recipe", {"dish": "lasagna"})])
        if n == 2:
            return ModelResponse(parts=[ToolCallPart("compute_missing", {"recipe_id": seen_ids["Lasagna"]})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, reply(
            meal_ids=[seen_ids["Lasagna"]], substitutions=[{"missing": "ricotta", "use_instead": "cottage cheese"}],
            shopping_list=["ground beef"], check_first=["pasta"]))])

    turn = await run_turn(store, "s1", "I want to make lasagna", model=FunctionModel(fn), recipe_model=LASAGNA_MODEL)
    # get_recipe gives the model a compact candidate (id, ingredients, time), not the Recipe
    candidate = next(p.content for m in turn.result.new_messages() if isinstance(m, ModelRequest)
                     for p in m.parts if isinstance(p, ToolReturnPart) and p.tool_name == "get_recipe")
    assert candidate.name == "Lasagna" and candidate.uses_from_inventory == ["egg"]
    assert "ricotta: 1" in candidate.ingredients and not hasattr(candidate, "steps")
    report = next(p.content for m in turn.result.new_messages() if isinstance(m, ModelRequest)
                  for p in m.parts if isinstance(p, ToolReturnPart) and p.tool_name == "compute_missing")
    assert report.missing_essential == ["ricotta", "ground beef"]
    assert report.check_first == ["pasta"]  # pantry not scanned
    assert turn.reply.substitutions[0].use_instead == "cottage cheese"
    assert [m.name for m in turn.reply.meals] == ["Lasagna"]  # filled from the cache by id


# --- photos ----------------------------------------------------------------------------------------

async def test_recognize_inventory_merges_and_marks_scanned(store):
    model, seen = scripted(
        ("recognize_inventory", {}),
        reply(questions=["Is the white container leftover rice?"]),
    )
    turn = await run_turn(store, "s1", "", images=[(FIXTURE_IMAGE, "pantry")], model=model, vision_model=VISION_MODEL)

    assert "The user attached 1 photo (pantry)" in seen[0][0]
    user = next(p for p in seen[0][1] if isinstance(p, UserPromptPart))
    assert user.content == "[user attached 1 photo (pantry)]"
    out = tool_returns(seen[1][1])["recognize_inventory"]
    assert out.startswith("Recognized 2 items in 1 photo(s) of: pantry.")
    assert "Uncertain (1): white container (possibly leftover rice)" in out
    assert "pantry (scanned" in out
    names = {i.name: i for i in get_inventory(store)}
    assert names["milk"].location == "pantry" and names["milk"].source == "photo"
    assert names["white container"].uncertain is True
    assert names["spinach"].use_soon is True  # recognition never clears existing data
    assert "pantry" in store.load_scan_state().scanned
    assert turn.reply.questions == ["Is the white container leftover rice?"]


async def test_recognize_inventory_without_photos_says_so(store):
    model, seen = scripted(("recognize_inventory", {}), reply())
    await run_turn(store, "s1", "scan my fridge", model=model)
    assert tool_returns(seen[1][1])["recognize_inventory"].startswith("No photos are attached")
    assert "fridge" in store.load_scan_state().scanned and len(store.load_scan_state().scanned) == 1


# --- preferences -----------------------------------------------------------------------------------

async def test_save_preference_saves_and_reports_duplicates(store):
    model, seen = scripted(
        ("save_preference", {"text": "no pork", "avoid": ["Pork", "bacon"]}),
        ("save_preference", {"text": "kids dislike eggplant", "avoid": ["aubergine"]}),
        reply(),
    )
    await run_turn(store, "s1", "we don't eat pork", model=model)
    assert tool_returns(seen[1][1])["save_preference"] == "Saved: no pork (avoid: pork, bacon)"
    assert tool_returns(seen[2][1])["save_preference"] == "Already noted: kids dislike eggplant (avoid: eggplant)"
    assert [p.avoid for p in store.load_preferences()] == [["eggplant"], ["pork", "bacon"]]


# --- session history and limits --------------------------------------------------------------------

async def test_history_is_persisted_per_session(store):
    model, seen = scripted(reply(message="first"), reply(message="second"), reply(message="other"))
    await run_turn(store, "s1", "hello", model=model)
    turn = await run_turn(store, "s1", "and again", model=model)
    assert turn.reply.message == "second"
    history = store.load_session_messages("s1")
    prompts = [p.content for m in history if isinstance(m, ModelRequest) for p in m.parts if isinstance(p, UserPromptPart)]
    assert prompts == ["hello", "and again"]
    assert len(turn.result.new_messages()) < len(turn.result.all_messages())
    # the second run saw the first turn in its messages
    assert any(isinstance(p, UserPromptPart) and p.content == "and again" for p in seen[1][1])
    other = await run_turn(store, "s2", "new session", model=model)
    assert other.reply.message == "other"
    assert len(other.result.all_messages()) == 3  # request, final_result call, its return: no s1 history


async def test_tool_calls_are_limited(store, monkeypatch):
    monkeypatch.setattr(agent_module, "USAGE_LIMITS", UsageLimits(tool_calls_limit=2))
    model, _ = scripted(*([("get_inventory", {})] * 5), reply())
    with pytest.raises(UsageLimitExceeded):
        await run_turn(store, "s1", "loop", model=model)


def test_default_limits_are_about_ten_tool_calls():
    assert USAGE_LIMITS.tool_calls_limit == 10


def test_agent_registers_the_planned_tools():
    deps = Deps(store=Store(":memory:"))
    names = set(agent_module.toolset.tools)
    assert names == {
        "recognize_inventory", "get_inventory", "update_inventory", "suggest_meals", "get_recipe",
        "compute_missing", "validate_suggestion", "save_preference",
    }
    assert deps.images == [] and deps.recipes == {}
