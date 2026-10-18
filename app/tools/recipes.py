"""Recipe generation: meal ideas from the inventory (Mode A), a standard recipe for a dish (Mode B), and
the cooking steps of a recipe on demand (when the user opens a card).

One structured call to RECIPE_MODEL each. The output is never trusted: names are normalized,
categories coerced, `uses_from_inventory` filled by code, and the checks in `checks.py` decide.
Candidates carry no steps (they cost most of the generation time); `get_steps(store, recipe_id)` adds
them later. Every recipe returned is saved in the store by id, so steps can be generated after the run.
"""

import logging
import re
import time

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models import Model

from app import config
from app.llm import thinking_settings
from app.models import CATEGORIES, MAX_TO_BUY, Constraints, CookMode, Ingredient, Recipe, Substitution
from app.store import Store
from app.tools.checks import fill_uses_from_inventory
from app.tools.inventory import get_inventory, inventory_summary
from app.tools.normalize import normalize
from app.tools.preferences import preferences_summary
from app.tools.recognize import coerce_category

log = logging.getLogger(__name__)

INGREDIENT_RULES = """\
Ingredient rules:
- name: a plain generic English ingredient name, singular ("tomato", "pasta", "cheddar"), no amounts or \
preparation words in the name; put those in amount ("2, diced").
- amount: a number with g, kg, ml or l for what is weighed or measured ("300 g", "500 ml"), a bare count \
for whole items ("5" eggs, "2, diced" onions); spoons or "to taste" only for small amounts. Code compares \
these with the amounts the household entered.
- essential: true if the dish fails or becomes a different dish without it. Always essential: the main \
protein, the base (pasta, rice, bread, dough, tortilla), and every ingredient named in the dish. Optional \
(false) only for garnishes, decorative herbs, toppings and "to taste" extras. Examples:
  lasagna: lasagna noodle, ground beef, ricotta, mozzarella, tomato sauce = essential; basil on top = optional.
  chicken fried rice: chicken, rice, egg = essential; green onion to garnish = optional.
  spinach omelette: egg, spinach = essential; chive, black pepper to taste = optional.
  Be honest: the shopping list is built from the essential ones; a wrong "optional" means the user \
finds out at the stove.
- category: exactly one of {categories}.
- Staples: the staples line of the inventory lists what the household always has. Use them freely and \
list them as ingredients like any other; never use a staple that is not on that list without listing it.
"""

SUGGEST_PROMPT = """\
You suggest home-cooking dinner ideas built from what this household has.
Rules:
- Build each dish around the inventory items. Prefer items marked USE SOON.
{mode_rules}
- Never use an ingredient the household avoids (see preferences).
- Places marked NOT SCANNED may hold things you cannot see; do not count on them.
- Simple home cooking, the kind a parent makes on a weekday. Realistic time_minutes (prep + cooking).
- Distinct dishes: do not repeat a dish or a near-variant of it.
- The dish name must be honest: never name an ingredient in it ("cream pasta", "chicken soup") unless \
that ingredient is in the dish's ingredients.
- Do not write cooking steps: only name, ingredients, time and servings.
""" + INGREDIENT_RULES

# The cooking mode's rules for SUGGEST_PROMPT (T4.5); code checks the result either way.
SUGGEST_MODE_RULES = {
    "home": """\
- The user wants to cook only with what is at home: every essential ingredient must be in the inventory \
or the staples. If a dish would need anything else, choose another dish.
- If the request names a dish or a style the inventory cannot make (e.g. "alfredo" with no cream), \
suggest the closest dishes that can be made (e.g. a pasta with butter, parmesan and garlic).
- Only real dinners a family would eat. If the kitchen has too little for that, return fewer dishes, \
or none: never invent a dish (a dressing, a plain bread, a sauce on its own) just to fill the count.""",
    "shop": f"""\
- The user is happy to buy a few things: a dish may need up to {MAX_TO_BUY} essential ingredients the \
household lacks. List them and mark them essential honestly (code puts them on the shopping list). \
Prefer dishes that need fewer purchases; a dish that needs nothing is best.
- If the request names a dish or a style, make the first dish the classic version.""",
}

RECIPE_PROMPT = """\
You write the standard home recipe for the dish the user names.
Rules:
- Write the usual version of the dish. Do not drop or replace ingredients because the household lacks \
them; the inventory is shown only so you name ingredients the same way.
- Leave out optional extras that conflict with the household's preferences.
- Realistic time_minutes (prep + cooking). Do not write cooking steps: only name, ingredients, time and servings.
""" + INGREDIENT_RULES

STEPS_PROMPT = """\
You write the cooking steps for a home recipe whose name, ingredients, time and servings are given.
Rules:
- 3 to 8 short steps, in order, each one action a home cook can follow. Use only the ingredients listed.
- Fit the total time given. No introduction, no tips, no step numbers in the text.
- If substitutes are listed, the ingredient list already uses them: write the steps for the substitute and \
never mention the ingredient it replaces.
"""


class RecipeDraft(BaseModel):
    """What the model returns: a Recipe without the code-filled fields and without steps."""

    name: str
    ingredients: list[Ingredient]
    time_minutes: int
    servings: int = 4
    photo_query: str = Field("", description="2 or 3 English words to search a stock photo of the finished dish: "
                                             "its main ingredient, then the kind of dish as the LAST word, never an "
                                             "ingredient: 'spinach frittata', 'tomato pasta', 'lentil soup', "
                                             "'chicken skillet', 'beef taco'")


class StepsDraft(BaseModel):
    steps: list[str] = Field(description="the cooking steps in order, 3 to 8")


class MealIdeas(BaseModel):
    recipes: list[RecipeDraft] = Field(description="distinct dishes, in order of preference")


def dish_name_ingredients(*dish_names: str) -> set[str]:
    """Canonical names of every 1-3 word phrase in the dish names: "Spaghetti with Bell Peppers" ->
    {"pasta", "bell pepper", ...}. An ingredient in this set is named in the dish."""
    out: set[str] = set()
    for dish in dish_names:
        words = re.findall(r"[a-z]+", dish.lower())
        for n in (1, 2, 3):
            for k in range(len(words) - n + 1):
                name = normalize(" ".join(words[k:k + n]))
                if name:
                    out.add(name)
    return out


def force_named_essential(ingredients: list[Ingredient], *dish_names: str) -> list[Ingredient]:
    """Safety rule (code, not the model): an ingredient whose canonical name is named in the dish is
    essential ("Spinach omelette" without spinach is not that dish). Expects normalized ingredient names."""
    named = dish_name_ingredients(*dish_names)
    out = []
    for ing in ingredients:
        if not ing.essential and ing.name in named:
            log.debug("forced %r essential (named in %s)", ing.name, dish_names)
            ing = ing.model_copy(update={"essential": True})
        out.append(ing)
    return out


def _clean(draft: RecipeDraft, *dish_names: str) -> Recipe:
    """Normalized ingredient names (deduped, essential if any duplicate is), categories from CATEGORIES,
    and every ingredient named in the dish (draft.name or `dish_names`) forced to essential."""
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
        name=draft.name.strip(),
        ingredients=force_named_essential(list(ingredients.values()), draft.name, *dish_names),
        time_minutes=draft.time_minutes, servings=draft.servings, photo_query=" ".join(draft.photo_query.split()),
    )


def _dish_key(name: str) -> str:
    return " ".join(name.lower().split())


def _context(store: Store) -> str:
    return (
        f"Inventory:\n{inventory_summary(get_inventory(store), store.load_scan_state())}\n\n"
        f"Preferences:\n{preferences_summary(store)}"
    )


async def _run(agent: Agent, prompt: str, what: str):
    start = time.perf_counter()
    result = await agent.run(prompt, model_settings=thinking_settings(config.RECIPE_THINKING))
    usage = result.usage
    log.debug("recipe call (%s): %d chars, %.1fs, %s in / %s out tokens", what, len(prompt),
              time.perf_counter() - start, usage.input_tokens, usage.output_tokens)
    return result.output


def _model(model: Model | None) -> Model:
    if model is not None:
        return model
    from app.llm import recipe_model  # needs the API key, so only when no model is given

    return recipe_model()


def _finish(store: Store, recipe: Recipe) -> Recipe:
    """Fill uses_from_inventory and save the recipe by id (for get_steps later)."""
    recipe = fill_uses_from_inventory(recipe, get_inventory(store))
    store.save_recipe(recipe)
    return recipe


async def suggest_meals(
    store: Store,
    constraints: Constraints | None = None,
    n: int = 5,
    exclude: list[str] | None = None,
    *,
    cook_mode: CookMode = "home",
    model: Model | None = None,
) -> list[Recipe]:
    """Up to `n` meal candidates (no steps) built around the inventory, for the cooking mode.

    Not validated: run checks.check_candidates on them with the same cooking mode.

    Code drops dishes named in `exclude`, duplicate names and dishes over `constraints.max_minutes`.
    Each recipe is saved in the store by id.
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
                  instructions=SUGGEST_PROMPT.format(mode_rules=SUGGEST_MODE_RULES[cook_mode],
                                                     categories=", ".join(CATEGORIES)))
    ideas: MealIdeas = await _run(agent, "\n".join(lines), "suggest_meals")

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
        out.append(_finish(store, _clean(draft)))
    return out[:n]


async def get_recipe(store: Store, dish: str, *, model: Model | None = None) -> Recipe:
    """The standard home recipe for `dish` (no steps). Not checked: run compute_missing on it. Saved by id."""
    agent = Agent(_model(model), output_type=RecipeDraft,
                  instructions=RECIPE_PROMPT.format(categories=", ".join(CATEGORIES)))
    draft: RecipeDraft = await _run(agent, f"{_context(store)}\n\nDish: {dish.strip()}", "get_recipe")
    return _finish(store, _clean(draft, dish).model_copy(update={"requested": True}))


def _recipe_text(recipe: Recipe, subs: dict[str, str] | None = None) -> str:
    """The recipe for STEPS_PROMPT; with `subs` (missing -> use instead) the substitutes replace the originals."""
    subs = subs or {}
    ingredients = "\n".join(
        f"- {subs.get(i.name, i.name)}: {i.amount}" + ("" if i.essential else " (optional)")
        for i in recipe.ingredients
    )
    text = (f"Recipe: {recipe.name}\nTime: {recipe.time_minutes} minutes, serves {recipe.servings}\n"
            f"Ingredients:\n{ingredients}")
    if subs:
        text += "\nSubstitutes: " + "; ".join(f"{new} instead of {old}" for old, new in subs.items())
    return text


def _subs_for(recipe: Recipe, substitutions: list[Substitution] | None) -> dict[str, str]:
    """missing -> use_instead (canonical), only for ingredients this recipe has, in a stable order."""
    names = {i.name for i in recipe.ingredients}
    pairs = {normalize(s.missing): normalize(s.use_instead) for s in substitutions or []}
    return {old: new for old, new in sorted(pairs.items()) if old in names and new and new != old}


async def get_steps(
    store: Store,
    recipe_id: str,
    substitutions: list[Substitution] | None = None,
    *,
    model: Model | None = None,
) -> Recipe:
    """The recipe with its cooking steps: generated on first request (one LLM call), then stored.

    `substitutions` (from the agent's reply) are written into the steps ("mix the cottage cheese with the
    egg", never "the ricotta"). Steps with substitutes are stored under their own key, so the plain version
    and each substituted one are generated once each; the returned recipe keeps its id and ingredients.
    Raises KeyError if no recipe with that id was ever returned by suggest_meals / get_recipe.
    """
    recipe = store.load_recipe(recipe_id)
    if recipe is None:
        raise KeyError(recipe_id)
    subs = _subs_for(recipe, substitutions)
    key = recipe_id if not subs else f"{recipe_id}~" + "~".join(f"{old}>{new}" for old, new in subs.items())
    cached = store.load_recipe(key) if subs else recipe
    if cached is not None and cached.steps:
        return recipe.model_copy(update={"steps": cached.steps})
    agent = Agent(_model(model), output_type=StepsDraft, instructions=STEPS_PROMPT)
    draft: StepsDraft = await _run(agent, _recipe_text(recipe, subs), "get_steps")
    steps = [" ".join(s.split()) for s in draft.steps if s.strip()]
    if not steps:
        raise ValueError(f"the model returned no steps for {recipe.name!r}")
    store.save_recipe(recipe.model_copy(update={"id": key, "steps": steps}))
    return recipe.model_copy(update={"steps": steps})
