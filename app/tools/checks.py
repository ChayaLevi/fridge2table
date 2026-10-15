"""Deterministic checks on recipes against the inventory and preferences (no LLM).

`inventory` is what get_inventory() returns: stored items plus the staples the user has not
removed. A staple counts as available only through that list, so a removed staple is missing.
"""

import re
from dataclasses import dataclass, field

from app.models import (
    MAX_TO_BUY, PANTRY_CATEGORIES, AgentReply, CookMode, FailedCandidate, InventoryItem, MealCandidate, MissingReport, Preference, Recipe,
    ScanState, SuggestResult, ValidationResult,
)
from app.tools.normalize import normalize


def _dedupe(names: list[str]) -> list[str]:
    return list(dict.fromkeys(names))


def compute_missing(recipe: Recipe, inventory: list[InventoryItem], scan_state: ScanState) -> MissingReport:
    """Split the recipe's unavailable ingredients into to-buy, check-the-pantry-first and optional.

    Available = same canonical name as an inventory item (any qty_level, `low` included).
    If the pantry was never scanned, a missing essential of a pantry-type category goes to
    `check_first` instead of `missing_essential`.
    """
    have = {normalize(i.name) for i in inventory}
    pantry_scanned = "pantry" in scan_state.scanned
    missing, check_first, optional = [], [], []
    for ing in recipe.ingredients:
        name = normalize(ing.name)
        if not name or name in have:
            continue
        if not ing.essential:
            optional.append(name)
        elif not pantry_scanned and ing.category in PANTRY_CATEGORIES:
            check_first.append(name)
        else:
            missing.append(name)
    return MissingReport(
        missing_essential=_dedupe(missing), check_first=_dedupe(check_first), missing_optional=_dedupe(optional),
    )


def _violations(recipe: Recipe, preferences: list[Preference]) -> list[str]:
    """"<ingredient> (<preference text>)" for every recipe ingredient a preference avoids."""
    out = []
    for ing in recipe.ingredients:
        name = normalize(ing.name)
        for pref in preferences:
            if any(normalize(a) == name for a in pref.avoid):
                out.append(f"{name} ({pref.text})")
    return _dedupe(out)


def validate_suggestion(
    recipe: Recipe, inventory: list[InventoryItem], preferences: list[Preference], scan_state: ScanState,
) -> ValidationResult:
    """ok only if no essential is missing (check_first counts as missing) and no preference is violated."""
    report = compute_missing(recipe, inventory, scan_state)
    violated = _violations(recipe, preferences)
    parts = []
    if report.missing_essential:
        parts.append(f"missing: {', '.join(report.missing_essential)}")
    if report.check_first:
        parts.append(f"pantry not scanned: {', '.join(report.check_first)} not confirmed")
    if violated:
        parts.append(f"violates preferences: {', '.join(violated)}")
    return ValidationResult(
        ok=not parts,
        missing_essential=report.missing_essential,
        violated_preferences=violated,
        check_first=report.check_first,
        reason="; ".join(parts),
    )


def fill_uses_from_inventory(recipe: Recipe, inventory: list[InventoryItem]) -> Recipe:
    """Copy of the recipe with `uses_from_inventory` = the non-staple inventory items it uses, use-soon first."""
    by_name = {normalize(i.name): i for i in inventory if not i.is_staple}
    used = _dedupe([n for n in (normalize(ing.name) for ing in recipe.ingredients) if n in by_name])
    used.sort(key=lambda n: not by_name[n].use_soon)  # stable: recipe order within each group
    return recipe.model_copy(update={"uses_from_inventory": used})


def check_candidates(
    recipes: list[Recipe], inventory: list[InventoryItem], preferences: list[Preference], scan_state: ScanState,
    cook_mode: CookMode = "home",
) -> SuggestResult:
    """Check every suggest_meals candidate for the cooking mode: passed ones as MealCandidates, failed ones with the reason.

    home: a candidate passes only if validate_suggestion is ok (nothing to buy or confirm).
    shop: a candidate passes if it violates no preference and needs at most MAX_TO_BUY items to buy or
    confirm in the pantry; its to_buy / check_first say which.
    """
    passed, failed = [], []
    for recipe in recipes:
        result = validate_suggestion(recipe, inventory, preferences, scan_state)
        if cook_mode == "home":
            if result.ok:
                passed.append(MealCandidate.from_recipe(recipe))
            else:
                failed.append(FailedCandidate(id=recipe.id, name=recipe.name, reason=result.reason))
            continue
        reason = _shop_problem(result)
        if reason:
            failed.append(FailedCandidate(id=recipe.id, name=recipe.name, reason=reason))
        else:
            passed.append(MealCandidate.from_recipe(recipe, compute_missing(recipe, inventory, scan_state)))
    return SuggestResult(passed=passed, failed=failed)


def _shop_problem(res: ValidationResult, substituted: frozenset[str] = frozenset()) -> str:
    """Why a suggested meal fails in shop mode ("" if it passes): a violated preference, or too much to buy."""
    if res.violated_preferences:
        return f"violates preferences: {', '.join(res.violated_preferences)}"
    need = [n for n in res.missing_essential + res.check_first if n not in substituted]
    if len(need) > MAX_TO_BUY:
        return f"needs {len(need)} items to buy ({', '.join(need)}); at most {MAX_TO_BUY}"
    return ""


MAX_MEALS = 3
MAX_QUESTIONS = 3


@dataclass
class ReplyCheck:
    """Result of check_reply: the reply with code-fixed lists, what failed (for ModelRetry), what code fixed."""

    reply: AgentReply
    problems: list[str] = field(default_factory=list)  # non-empty -> the model must fix its reply
    fixes: list[str] = field(default_factory=list)  # lists code corrected silently (for the trace)

    @property
    def ok(self) -> bool:
        return not self.problems


def check_reply(
    reply: AgentReply,
    recipes: dict[str, Recipe],
    inventory: list[InventoryItem],
    preferences: list[Preference],
    scan_state: ScanState,
    cook_mode: CookMode = "home",
) -> ReplyCheck:
    """Re-check the agent's final reply against the run's recipe cache and the current inventory (no LLM).

    - Every id in meal_ids must be in `recipes` (the run's cache); at most 3 meals, at most 3 questions.
    - Every substitution's use_instead must be in the inventory.
    - A suggested meal (not `requested`): never violates a preference. In home mode it needs nothing to
      buy or confirm (substituted items aside); in shop mode at most MAX_TO_BUY items.
    - A dish the user named (`requested`): gets its lists in either mode.
    - shopping_list and check_first are always recomputed from compute_missing of the meals, minus the
      substituted items; the model's lists are replaced (code wins). When they are not empty, the message
      must not name their items (the app shows them; prose could contradict them).
    """
    problems: list[str] = []
    fixes: list[str] = []
    ids = list(dict.fromkeys(i.strip() for i in reply.meal_ids))
    unknown = [i for i in ids if i not in recipes]
    if unknown:
        known = ", ".join(f"{r.id} ({r.name})" for r in recipes.values()) or "none: call suggest_meals or get_recipe first"
        problems.append(f"unknown meal id(s) {', '.join(unknown)}; use only ids returned by tools in this turn or shown in your last reply: {known}")
    meals = [recipes[i] for i in ids if i in recipes]
    if len(ids) > MAX_MEALS:
        problems.append(f"{len(ids)} meals; show at most {MAX_MEALS}")
    if len(reply.questions) > MAX_QUESTIONS:
        problems.append(f"{len(reply.questions)} questions; ask at most {MAX_QUESTIONS}")

    have = {normalize(i.name) for i in inventory}
    for sub in reply.substitutions:
        if normalize(sub.use_instead) not in have:
            problems.append(f"substitute {sub.use_instead!r} (for {sub.missing}) is not in the inventory; "
                            "use an inventory item or put the missing item on the shopping list")
    substituted = frozenset(normalize(s.missing) for s in reply.substitutions)

    for meal in meals:
        if meal.requested:
            continue
        res = validate_suggestion(meal, inventory, preferences, scan_state)
        if cook_mode == "shop":
            why = _shop_problem(res, substituted)
            if why:
                problems.append(f"{meal.name} {why}. Replace it with a passed candidate")
            continue
        res = res.model_copy(update={
            "missing_essential": [n for n in res.missing_essential if n not in substituted],
            "check_first": [n for n in res.check_first if n not in substituted],
        })
        if res.missing_essential or res.check_first or res.violated_preferences:
            problems.append(f"{meal.name} {_why(res)}. The user chose \"Only what I have\": show only meals that "
                            "need nothing to buy (passed candidates), or none")

    to_buy, check_first = [], []
    for meal in meals:
        report = compute_missing(meal, inventory, scan_state)
        to_buy += [n for n in report.missing_essential if n not in substituted]
        check_first += [n for n in report.check_first if n not in substituted]
    to_buy, check_first = _dedupe(to_buy), _dedupe(check_first)
    if [normalize(n) for n in reply.shopping_list] != to_buy:
        fixes.append(f"shopping_list {reply.shopping_list} -> {to_buy}")
    if [normalize(n) for n in reply.check_first] != check_first:
        fixes.append(f"check_first {reply.check_first} -> {check_first}")
    reply = reply.model_copy(update={"shopping_list": to_buy, "check_first": check_first})
    named = items_named_in(reply.message, to_buy + check_first, [m.name for m in meals])
    if named:
        problems.append(
            f"message names items of the shopping lists ({', '.join(named)}): the app shows To buy and "
            "Check your pantry first under the recipe, and your words can contradict them. Write one "
            "sentence that names no ingredient except the substitution pairs, and no counts (\"You can "
            "make it with your cottage cheese instead of ricotta; the shopping list is below.\")")

    reply = reply.model_copy(update={"meal_ids": [m.id for m in meals]})
    return ReplyCheck(reply=reply, problems=problems, fixes=fixes)


def items_named_in(message: str, names: list[str], dish_names: list[str] = ()) -> list[str]:
    """The names (canonical, from the lists) that the message mentions as whole words, plural allowed.

    Dish names are removed from the message first, so "Beef lasagna" does not count as naming "beef".
    """
    text = message.lower()
    for dish in dish_names:
        text = text.replace(dish.lower(), " ")
    found = []
    for name in names:
        words = name.lower().split()
        if not words:
            continue
        pattern = r"\b" + r"[\s-]+".join(re.escape(w) for w in words) + r"(?:e?s)?\b"
        if re.search(pattern, text):
            found.append(name)
    return found


def _why(res: ValidationResult) -> str:
    """"needs peanut, not in inventory" / "uses eggplant, which the household avoids" for a ModelRetry."""
    parts = []
    if res.missing_essential:
        parts.append(f"needs {', '.join(res.missing_essential)}, not in inventory")
    if res.check_first:
        parts.append(f"needs {', '.join(res.check_first)}, not confirmed (pantry not scanned)")
    if res.violated_preferences:
        parts.append(f"violates preferences: {', '.join(res.violated_preferences)}")
    return "; ".join(parts)
