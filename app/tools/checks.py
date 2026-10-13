"""Deterministic checks on recipes against the inventory and preferences (no LLM).

`inventory` is what get_inventory() returns: stored items plus the staples the user has not
removed. A staple counts as available only through that list, so a removed staple is missing.
"""

from app.models import (
    PANTRY_CATEGORIES, InventoryItem, MissingReport, Preference, Recipe, ScanState, ValidationResult,
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
