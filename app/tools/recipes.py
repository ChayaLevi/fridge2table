"""Recipe generation: meal ideas from the inventory (Mode A) and a standard recipe for a dish (Mode B).

One structured call to RECIPE_MODEL each. The output is never trusted: names are normalized,
categories coerced, `uses_from_inventory` filled by code, and the checks in `checks.py` decide.
"""

import logging
import time

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models import Model

from app.models import CATEGORIES, Constraints, Ingredient, Preference, Recipe
from app.store import Store
from app.tools.checks import fill_uses_from_inventory
from app.tools.inventory import get_inventory, inventory_summary
from app.tools.normalize import normalize
from app.tools.recognize import coerce_category

log = logging.getLogger(__name__)

INGREDIENT_RULES = """\
Ingredient rules:
- name: a plain generic English ingredient name, singular ("tomato", "pasta", "cheddar"), no amounts or \
preparation words in the name; put those in amount ("2, diced").
- essential: true if the dish fails or becomes a different dish without it; false for garnishes, toppings \
and "to taste" extras. Be honest: the user's shopping list is built from the essential ones.
- category: exactly one of {categories}.
- Staples: the staples line of the inventory lists what the household always has. Use them freely and \
list them as ingredients like any other; never use a staple that is not on that list without listing it.
"""

SUGGEST_PROMPT = """\
You suggest home-cooking dinner ideas built from what this household has.
Rules:
- Build each dish around the inventory items. Prefer items marked USE SOON.
- Every essential ingredient should be in the inventory or the staples. Avoid needing anything else; \
if a dish truly needs one extra ingredient, mark it essential honestly.
- Never use an ingredient the household avoids (see preferences).
- Places marked NOT SCANNED may hold things you cannot see; do not count on them.
- Simple home cooking, the kind a parent makes on a weekday. Realistic time_minutes (prep + cooking).
- Distinct dishes: do not repeat a dish or a near-variant of it.
- steps: short, numbered in order, 3 to 8 of them.
""" + INGREDIENT_RULES

RECIPE_PROMPT = """\
You write the standard home recipe for the dish the user names.
Rules:
- Write the usual version of the dish. Do not drop or replace ingredients because the household lacks \
them; the inventory is shown only so you name ingredients the same way.
- Leave out optional extras that conflict with the household's preferences.
- Realistic time_minutes (prep + cooking). steps: short, in order, 3 to 10 of them.
""" + INGREDIENT_RULES


class RecipeDraft(BaseModel):
    """What the model returns: a Recipe without the code-filled fields."""

    name: str
    ingredients: list[Ingredient]
    steps: list[str]
    time_minutes: int
    servings: int = 4


class MealIdeas(BaseModel):
    recipes: list[RecipeDraft] = Field(description="distinct dishes, in order of preference")


def _preferences_text(prefs: list[Preference]) -> str:
    if not prefs:
        return "none"
    return "; ".join(f"{p.text} (avoid: {', '.join(p.avoid)})" if p.avoid else p.text for p in prefs)


def _clean(draft: RecipeDraft) -> Recipe:
    """Normalized ingredient names (deduped, essential if any duplicate is), categories from CATEGORIES."""
    ingredients: dict[str, Ingredient] = {}
    for ing in draft.ingredients:
        name = normalize(ing.name)
        if not name:
            continue
        prev = ingredients.get(name)
        if prev is not None:
            if ing.essential and not prev.essential:
                ingredients[name] = prev.model_copy(update={"essential": True})
            continue
        ingredients[name] = ing.model_copy(update={"name": name, "category": coerce_category(ing.category)})
    return Recipe(
        name=draft.name.strip(), ingredients=list(ingredients.values()), steps=draft.steps,
        time_minutes=draft.time_minutes, servings=draft.servings,
    )


def _dish_key(name: str) -> str:
    return " ".join(name.lower().split())


def _context(store: Store) -> str:
    return (
        f"Inventory:\n{inventory_summary(get_inventory(store), store.load_scan_state())}\n\n"
        f"Preferences: {_preferences_text(store.load_preferences())}"
    )


async def _run(agent: Agent, prompt: str, what: str):
    start = time.perf_counter()
    result = await agent.run(prompt)
    usage = result.usage
    log.debug("recipe call (%s): %d chars, %.1fs, %s in / %s out tokens", what, len(prompt),
              time.perf_counter() - start, usage.input_tokens, usage.output_tokens)
    return result.output


def _model(model: Model | None) -> Model:
    if model is not None:
        return model
    from app.llm import recipe_model  # needs the API key, so only when no model is given

    return recipe_model()


async def suggest_meals(
    store: Store,
    constraints: Constraints | None = None,
    n: int = 5,
    exclude: list[str] | None = None,
    *,
    model: Model | None = None,
) -> list[Recipe]:
    """Up to `n` meal candidates built around the inventory. Not validated: run validate_suggestion on each.

    Code drops dishes named in `exclude`, duplicate names and dishes over `constraints.max_minutes`.
    """
    constraints = constraints or Constraints()
    exclude = exclude or []
    lines = [_context(store), "", f"Suggest {n} dishes."]
    if constraints.text.strip():
        lines.append(f"Request: {constraints.text.strip()}")
    if constraints.max_minutes:
        lines.append(f"Each dish must take at most {constraints.max_minutes} minutes in total.")
    if exclude:
        lines.append(f"Do not suggest these dishes (already proposed or rejected): {', '.join(exclude)}")
    agent = Agent(_model(model), output_type=MealIdeas,
                  instructions=SUGGEST_PROMPT.format(categories=", ".join(CATEGORIES)))
    ideas: MealIdeas = await _run(agent, "\n".join(lines), "suggest_meals")

    inventory = get_inventory(store)
    seen = {_dish_key(e) for e in exclude}
    out = []
    for draft in ideas.recipes:
        key = _dish_key(draft.name)
        if not key or key in seen:
            continue
        if constraints.max_minutes and draft.time_minutes > constraints.max_minutes:
            log.debug("suggest_meals: dropped %r (%d min > %d)", draft.name, draft.time_minutes, constraints.max_minutes)
            continue
        seen.add(key)
        out.append(fill_uses_from_inventory(_clean(draft), inventory))
    return out[:n]


async def get_recipe(store: Store, dish: str, *, model: Model | None = None) -> Recipe:
    """The standard home recipe for `dish`. Not checked: run compute_missing on it."""
    agent = Agent(_model(model), output_type=RecipeDraft,
                  instructions=RECIPE_PROMPT.format(categories=", ".join(CATEGORIES)))
    draft: RecipeDraft = await _run(agent, f"{_context(store)}\n\nDish: {dish.strip()}", "get_recipe")
    return fill_uses_from_inventory(_clean(draft), get_inventory(store))
