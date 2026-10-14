"""Deterministic checks on recipes against the inventory and preferences (no LLM).

`inventory` is what get_inventory() returns: stored items plus the staples the user has not
removed. A staple counts as available only through that list, so a removed staple is missing.
"""

from dataclasses import dataclass, field

from app.models import (
    PANTRY_CATEGORIES, AgentReply, FailedCandidate, InventoryItem, MealCandidate, MissingReport, Preference, Recipe,
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
) -> SuggestResult:
    """Run validate_suggestion on every candidate: passed ones as MealCandidates, failed ones with the reason."""
    passed, failed = [], []
    for recipe in recipes:
        result = validate_suggestion(recipe, inventory, preferences, scan_state)
        if result.ok:
            passed.append(MealCandidate.from_recipe(recipe))
        else:
            failed.append(FailedCandidate(id=recipe.id, name=recipe.name, reason=result.reason))
    return SuggestResult(passed=passed, failed=failed)


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
) -> ReplyCheck:
    """Re-check the agent's final reply against the run's recipe cache and the current inventory (no LLM).

    - Every id in meal_ids must be in `recipes` (the run's cache); at most 3 meals, at most 3 questions.
    - Every substitution's use_instead must be in the inventory.
    - Mode A (no shopping_list, check_first or substitutions): every meal must pass validate_suggestion.
    - Mode B (any of them present): shopping_list and check_first are recomputed from compute_missing of
      the meals, minus the substituted items; the model's lists are replaced (code wins).
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

    mode_b = bool(reply.shopping_list or reply.check_first or reply.substitutions)
    if not mode_b:
        for meal in meals:
            res = validate_suggestion(meal, inventory, preferences, scan_state)
            if not res.ok:
                problems.append(f"{meal.name} {_why(res)}. Replace it or move it to a Mode B answer with a shopping list")
    else:
        substituted = {normalize(s.missing) for s in reply.substitutions}
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

    reply = reply.model_copy(update={"meal_ids": [m.id for m in meals]})
    return ReplyCheck(reply=reply, problems=problems, fixes=fixes)


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
