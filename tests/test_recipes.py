from datetime import datetime

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.models import Constraints, InventoryChange, Preference
from app.store import Store
from app.tools.inventory import update_inventory
from app.tools.recipes import RECIPE_PROMPT, STEPS_PROMPT, SUGGEST_PROMPT, get_recipe, get_steps, suggest_meals
from app.tools.recognize import coerce_category


def ing(name, category="other", essential=True, amount="1"):
    return {"name": name, "amount": amount, "essential": essential, "category": category}


def dish(name, *ingredients, minutes=20):
    return {"name": name, "ingredients": list(ingredients), "time_minutes": minutes}


def fake_model(output):
    """FunctionModel that returns `output` as the structured result; records (instructions, prompt) per call."""
    calls = []

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        prompt = next(p.content for m in messages for p in m.parts if isinstance(p, UserPromptPart))
        calls.append((info.instructions, prompt))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    return FunctionModel(fn), calls


@pytest.fixture
def store():
    s = Store(":memory:")
    s.mark_scanned("fridge")
    update_inventory(s, [
        InventoryChange(op="add", name="spinach", category="vegetable", location="fridge", use_soon=True),
        InventoryChange(op="add", name="eggs", category="egg", location="fridge", qty_level="plenty"),
        InventoryChange(op="add", name="cheddar cheese", category="dairy", location="fridge"),
    ])
    s.add_preference(Preference(id="p1", text="kids dislike eggplant", avoid=["eggplant"],
                                created_at=datetime(2026, 10, 13)))
    yield s
    s.close()


# --- suggest_meals --------------------------------------------------------------------------------

async def test_suggest_meals_parses_and_normalizes(store):
    model, _ = fake_model({"recipes": [
        dish("Spinach Omelette", ing("Eggs", "egg"), ing("fresh spinach", "Vegetables"),
             ing("Cheddar Cheese", "cheese"), ing("salt", "spice"), ing("chopped chives", "herb", essential=False)),
    ]})
    [r] = await suggest_meals(store, model=model)
    assert r.name == "Spinach Omelette"
    assert [i.name for i in r.ingredients] == ["egg", "spinach", "cheddar", "salt", "chive"]
    assert [i.category for i in r.ingredients] == ["egg", "vegetable", "dairy", "spice", "vegetable"]
    assert r.ingredients[-1].essential is False
    assert r.time_minutes == 20 and r.servings == 4


async def test_suggest_meals_fills_uses_from_inventory_use_soon_first(store):
    model, _ = fake_model({"recipes": [
        dish("Frittata", ing("egg", "egg"), ing("cheddar", "dairy"), ing("spinach", "vegetable"), ing("salt", "spice")),
    ]})
    [r] = await suggest_meals(store, model=model)
    # spinach is use-soon so it comes first; salt is a staple so it is not listed
    assert r.uses_from_inventory == ["spinach", "egg", "cheddar"]


async def test_model_cannot_set_uses_from_inventory(store):
    model, _ = fake_model({"recipes": [dish("Toast", ing("bread", "grain"))]})
    [r] = await suggest_meals(store, model=model)
    assert r.uses_from_inventory == []


async def test_suggest_meals_prompt_has_inventory_preferences_constraints_and_exclude(store):
    model, calls = fake_model({"recipes": []})
    await suggest_meals(store, Constraints(text="kids are eating", max_minutes=30), n=4,
                        exclude=["Spinach omelette", "Pancakes"], model=model)
    instructions, prompt = calls[0]
    assert "spinach (some, USE SOON)" in prompt
    assert "pantry (NOT SCANNED)" in prompt
    assert "staples (assumed present): salt" in prompt
    assert "kids dislike eggplant (avoid: eggplant)" in prompt
    assert "kids are eating" in prompt and "at most 30 minutes" in prompt
    assert "Suggest 4 dishes" in prompt
    assert "Do not suggest these dishes" in prompt and "Spinach omelette, Pancakes" in prompt
    assert "Prefer items marked USE SOON" in instructions and "vegetable, fruit, meat" in instructions


async def test_suggest_meals_without_constraints_or_exclude(store):
    model, calls = fake_model({"recipes": []})
    assert await suggest_meals(store, model=model) == []
    _, prompt = calls[0]
    assert "Suggest 5 dishes" in prompt
    assert "Do not suggest" not in prompt and "Request:" not in prompt and "minutes in total" not in prompt


async def test_suggest_meals_drops_excluded_and_duplicate_dishes(store):
    model, _ = fake_model({"recipes": [
        dish("Spinach omelette", ing("egg", "egg")),
        dish("  spinach   OMELETTE ", ing("egg", "egg")),
        dish("Cheese omelette", ing("egg", "egg")),
        dish("Cheese Omelette", ing("egg", "egg")),
        dish("Egg fried rice", ing("egg", "egg")),
    ]})
    out = await suggest_meals(store, exclude=["spinach omelette"], model=model)
    assert [r.name for r in out] == ["Cheese omelette", "Egg fried rice"]


async def test_suggest_meals_drops_dishes_over_max_minutes(store):
    model, _ = fake_model({"recipes": [dish("Quick", minutes=25), dish("Slow", minutes=90), dish("Exact", minutes=30)]})
    out = await suggest_meals(store, Constraints(max_minutes=30), model=model)
    assert [r.name for r in out] == ["Quick", "Exact"]


async def test_suggest_meals_caps_at_n(store):
    model, _ = fake_model({"recipes": [dish(f"Dish {k}") for k in range(7)]})
    assert len(await suggest_meals(store, n=5, model=model)) == 5


async def test_duplicate_ingredients_merge_and_stay_essential(store):
    model, _ = fake_model({"recipes": [dish("Eggy", ing("eggs", "egg", essential=False), ing("egg", "egg"),
                                            ing("", "other"))]})
    [r] = await suggest_meals(store, model=model)
    assert [(i.name, i.essential) for i in r.ingredients] == [("egg", True)]


# --- get_recipe -----------------------------------------------------------------------------------

async def test_get_recipe_parses_normalizes_and_fills(store):
    model, calls = fake_model(dish(
        "Lasagna", ing("lasagne sheets", "pasta"), ing("minced beef", "meat"), ing("ricotta", "dairy"),
        ing("Tomatoes, canned", "canned goods"), ing("eggs", "egg"), ing("fresh basil", "garnish", essential=False),
        minutes=90,
    ))
    r = await get_recipe(store, "  lasagna ", model=model)
    assert r.name == "Lasagna" and r.time_minutes == 90
    names = [i.name for i in r.ingredients]
    assert "ground beef" in names and "canned tomato" in names and "egg" in names
    cats = {i.name: i.category for i in r.ingredients}
    assert cats["canned tomato"] == "canned" and cats["basil"] == "other"
    assert r.uses_from_inventory == ["egg"]
    instructions, prompt = calls[0]
    assert prompt.endswith("Dish: lasagna")
    assert "spinach (some, USE SOON)" in prompt and "kids dislike eggplant" in prompt
    assert "standard home recipe" in instructions


def test_prompts_have_the_rules():
    for rule in ("around the inventory", "USE SOON", "essential", "Staples", "NOT SCANNED", "preferences"):
        assert rule in SUGGEST_PROMPT
    for rule in ("usual version", "Do not drop or replace", "essential", "Staples"):
        assert rule in RECIPE_PROMPT
    assert "{categories}" in SUGGEST_PROMPT and "{categories}" in RECIPE_PROMPT


# --- category lookup ------------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("vegetable", "vegetable"), ("Vegetables", "vegetable"), ("  SPICES ", "spice"), ("produce", "vegetable"),
    ("Poultry", "meat"), ("seafood", "fish"), ("cheese", "dairy"), ("noodles", "pasta"), ("rice", "grain"),
    ("oil", "condiment"), ("legumes", "canned"), ("Canned goods", "canned"), ("dried herb", "spice"), ("eggs", "egg"),
    ("garnish", "other"), ("", "other"), ("Eggs!", "other"),
])
def test_coerce_category(raw, expected):
    assert coerce_category(raw) == expected


# --- no steps in candidates; get_steps on demand -------------------------------------------------

async def test_candidates_have_ids_no_steps_and_are_saved(store):
    model, _ = fake_model({"recipes": [dish("Omelette", ing("egg", "egg")), dish("Salad", ing("tomato", "vegetable"))]})
    meals = await suggest_meals(store, model=model)
    assert [m.steps for m in meals] == [[], []]
    assert len({m.id for m in meals}) == 2 and all(len(m.id) == 6 for m in meals)
    for m in meals:
        assert store.load_recipe(m.id) == m
    r = await get_recipe(store, "lasagna", model=fake_model(dish("Lasagna", ing("pasta", "pasta")))[0])
    assert r.steps == [] and store.load_recipe(r.id) == r


async def test_get_steps_generates_once_then_reads_from_the_store(store):
    [m] = await suggest_meals(store, model=fake_model({"recipes": [dish("Omelette", ing("egg", "egg", amount="3"))]})[0])
    steps_model, calls = fake_model({"steps": ["Whisk the eggs. ", "  Cook   them."]})
    r = await get_steps(store, m.id, model=steps_model)
    assert r.id == m.id and r.steps == ["Whisk the eggs.", "Cook them."]
    instructions, prompt = calls[0]
    assert "cooking steps" in instructions and "Recipe: Omelette" in prompt and "- egg: 3" in prompt
    # second call: no model call, same steps
    again = await get_steps(store, m.id, model=fake_model({"steps": ["other"]})[0])
    assert again.steps == ["Whisk the eggs.", "Cook them."] and len(calls) == 1
    assert store.load_recipe(m.id).steps == ["Whisk the eggs.", "Cook them."]


async def test_get_steps_unknown_id_and_empty_steps(store):
    with pytest.raises(KeyError):
        await get_steps(store, "nope", model=fake_model({"steps": ["x"]})[0])
    [m] = await suggest_meals(store, model=fake_model({"recipes": [dish("Omelette", ing("egg", "egg"))]})[0])
    with pytest.raises(ValueError):
        await get_steps(store, m.id, model=fake_model({"steps": ["  "]})[0])


def test_steps_prompt_has_the_rules():
    assert "3 to 8" in STEPS_PROMPT and "only the ingredients listed" in STEPS_PROMPT
    assert "Do not write cooking steps" in SUGGEST_PROMPT and "Do not write cooking steps" in RECIPE_PROMPT
