from datetime import datetime

import pytest

from app.models import Ingredient, InventoryChange, InventoryItem, Preference, Recipe, ScanState
from app.store import Store
from app.tools.checks import check_candidates, compute_missing, fill_uses_from_inventory, validate_suggestion
from app.tools.inventory import get_inventory, update_inventory

NOW = datetime(2026, 10, 13, 18, 0)
FRIDGE_ONLY = ScanState(scanned={"fridge": NOW})
ALL_SCANNED = ScanState(scanned={"fridge": NOW, "pantry": NOW})


def item(name, qty="some", use_soon=False, is_staple=False, category="other", location="fridge"):
    return InventoryItem(
        id=name, name=name, display_name=name, category=category, qty_level=qty, location=location,
        confidence=1.0, uncertain=False, use_soon=use_soon, is_staple=is_staple,
        source="staple" if is_staple else "manual", updated_at=NOW,
    )


def ing(name, category="other", essential=True):
    return Ingredient(name=name, amount="1", essential=essential, category=category)


def recipe(*ingredients, name="dish"):
    return Recipe(name=name, ingredients=list(ingredients), time_minutes=20)


def pref(text, *avoid):
    return Preference(id=text, text=text, avoid=list(avoid), created_at=NOW)


@pytest.fixture
def store():
    s = Store(":memory:")
    yield s
    s.close()


# --- compute_missing --------------------------------------------------------------------------

def test_all_available():
    r = recipe(ing("egg", "egg"), ing("spinach", "vegetable"))
    rep = compute_missing(r, [item("egg"), item("spinach")], ALL_SCANNED)
    assert rep.missing_essential == rep.check_first == rep.missing_optional == []


def test_missing_essential():
    r = recipe(ing("egg", "egg"), ing("cream", "dairy"))
    assert compute_missing(r, [item("egg")], ALL_SCANNED).missing_essential == ["cream"]


@pytest.mark.parametrize("recipe_name, inv_name", [
    ("scallions", "green onion"),
    ("spring onion", "green onion"),
    ("chicken thighs", "chicken"),
    ("heavy cream", "cream"),
    ("tomatoes", "tomato"),
    ("aubergine", "eggplant"),
])
def test_synonyms_and_plurals_count_as_available(recipe_name, inv_name):
    r = recipe(ing(recipe_name, "vegetable"))
    assert compute_missing(r, [item(inv_name)], ALL_SCANNED).missing_essential == []


def test_staples_count_as_available(store):
    r = recipe(ing("salt", "spice"), ing("olive oil", "condiment"), ing("chilli flakes", "spice"))
    rep = compute_missing(r, get_inventory(store), FRIDGE_ONLY)
    assert rep.missing_essential == rep.check_first == []


def test_removed_staple_is_missing(store):
    update_inventory(store, [InventoryChange(op="remove", name="soy sauce")])
    r = recipe(ing("soy sauce", "sauce"), ing("salt", "spice"))
    assert compute_missing(r, get_inventory(store), ALL_SCANNED).missing_essential == ["soy sauce"]


def test_removed_staple_unscanned_pantry_goes_to_check_first(store):
    update_inventory(store, [InventoryChange(op="remove", name="soy sauce")])
    rep = compute_missing(recipe(ing("soy sauce", "sauce")), get_inventory(store), FRIDGE_ONLY)
    assert rep.check_first == ["soy sauce"] and rep.missing_essential == []


def test_optional_missing_is_reported_but_not_essential():
    r = recipe(ing("egg", "egg"), ing("parsley", "vegetable", essential=False))
    rep = compute_missing(r, [item("egg")], ALL_SCANNED)
    assert rep.missing_essential == [] and rep.missing_optional == ["parsley"]


def test_optional_pantry_item_unscanned_is_optional_not_check_first():
    rep = compute_missing(recipe(ing("breadcrumbs", "baking", essential=False)), [], FRIDGE_ONLY)
    assert rep.missing_optional == ["breadcrumb"] and rep.check_first == []


def test_low_counts_as_available():
    assert compute_missing(recipe(ing("milk", "dairy")), [item("milk", qty="low")], ALL_SCANNED).missing_essential == []


def test_empty_inventory():
    r = recipe(ing("egg", "egg"), ing("spinach", "vegetable"), ing("pasta", "pasta"))
    rep = compute_missing(r, [], ALL_SCANNED)
    assert rep.missing_essential == ["egg", "spinach", "pasta"] and rep.check_first == []


def test_duplicate_ingredients_reported_once():
    r = recipe(ing("tomatoes", "vegetable"), ing("tomato", "vegetable"))
    assert compute_missing(r, [], ALL_SCANNED).missing_essential == ["tomato"]


# --- unscanned pantry rule --------------------------------------------------------------------

def test_pantry_unscanned_pasta_goes_to_check_first():
    r = recipe(ing("spaghetti", "pasta"), ing("canned tomatoes", "canned"), ing("ground beef", "meat"))
    rep = compute_missing(r, [], FRIDGE_ONLY)
    assert rep.check_first == ["pasta", "canned tomato"]
    assert rep.missing_essential == ["ground beef"]


def test_pantry_scanned_pasta_goes_to_missing_essential():
    rep = compute_missing(recipe(ing("spaghetti", "pasta")), [], ALL_SCANNED)
    assert rep.missing_essential == ["pasta"] and rep.check_first == []


def test_vegetable_is_never_check_first():
    rep = compute_missing(recipe(ing("onion", "vegetable")), [], ScanState(scanned={}))
    assert rep.missing_essential == ["onion"] and rep.check_first == []


@pytest.mark.parametrize("category", sorted({"grain", "pasta", "canned", "baking", "sauce", "condiment", "spice", "snack"}))
def test_every_pantry_category_goes_to_check_first(category):
    rep = compute_missing(recipe(ing("mystery thing", category)), [], FRIDGE_ONLY)
    assert rep.check_first == ["mystery thing"]


# --- validate_suggestion ----------------------------------------------------------------------

def test_valid_suggestion():
    res = validate_suggestion(recipe(ing("egg", "egg")), [item("egg")], [], ALL_SCANNED)
    assert res.ok and res.reason == "" and res.missing_essential == res.violated_preferences == []


def test_invalid_when_essential_missing():
    res = validate_suggestion(recipe(ing("egg", "egg"), ing("cream", "dairy")), [item("egg")], [], ALL_SCANNED)
    assert not res.ok and res.missing_essential == ["cream"] and "missing: cream" in res.reason


def test_optional_missing_still_ok():
    r = recipe(ing("egg", "egg"), ing("chive", "vegetable", essential=False))
    assert validate_suggestion(r, [item("egg")], [], ALL_SCANNED).ok


def test_check_first_only_fails_with_pantry_not_scanned_reason():
    r = recipe(ing("spaghetti", "pasta"), ing("egg", "egg"))
    res = validate_suggestion(r, [item("egg")], [], FRIDGE_ONLY)
    assert not res.ok
    assert res.missing_essential == [] and res.check_first == ["pasta"]
    assert res.reason.startswith("pantry not scanned")


def test_preference_violation_on_essential():
    r = recipe(ing("eggplant", "vegetable"), ing("egg", "egg"))
    res = validate_suggestion(r, [item("eggplant"), item("egg")], [pref("kids dislike eggplant", "eggplant")], ALL_SCANNED)
    assert not res.ok
    assert res.violated_preferences == ["eggplant (kids dislike eggplant)"]
    assert "violates preferences" in res.reason


def test_preference_violation_via_synonym_and_optional():
    # an optional ingredient also violates; "aubergines" and "eggplant" are the same ingredient
    r = recipe(ing("egg", "egg"), ing("aubergines", "vegetable", essential=False))
    res = validate_suggestion(r, [item("egg")], [pref("no eggplant", "eggplant")], ALL_SCANNED)
    assert not res.ok and res.violated_preferences == ["eggplant (no eggplant)"]


def test_unrelated_preference_is_ok():
    res = validate_suggestion(recipe(ing("egg", "egg")), [item("egg")], [pref("no fish", "salmon", "tuna")], ALL_SCANNED)
    assert res.ok


def test_empty_inventory_fails():
    res = validate_suggestion(recipe(ing("egg", "egg")), [], [], ALL_SCANNED)
    assert not res.ok and res.missing_essential == ["egg"]


def test_missing_and_violation_both_reported():
    r = recipe(ing("eggplant", "vegetable"), ing("cream", "dairy"))
    res = validate_suggestion(r, [item("eggplant")], [pref("no eggplant", "eggplant")], ALL_SCANNED)
    assert not res.ok and res.missing_essential == ["cream"] and res.violated_preferences


# --- fill_uses_from_inventory -----------------------------------------------------------------

def test_fill_uses_excludes_staples_and_puts_use_soon_first(store):
    update_inventory(store, [
        InventoryChange(op="add", name="egg", qty_level="plenty"),
        InventoryChange(op="add", name="spinach", qty_level="low", use_soon=True),
        InventoryChange(op="add", name="cheddar"),
    ])
    r = recipe(ing("eggs", "egg"), ing("cheddar", "dairy"), ing("salt", "spice"),
               ing("fresh spinach", "vegetable"), ing("cream", "dairy"))
    out = fill_uses_from_inventory(r, get_inventory(store))
    assert out.uses_from_inventory == ["spinach", "egg", "cheddar"]
    assert r.uses_from_inventory == []  # original untouched


def test_fill_uses_overwrites_model_values_and_handles_empty_inventory():
    r = recipe(ing("egg", "egg")).model_copy(update={"uses_from_inventory": ["caviar"]})
    assert fill_uses_from_inventory(r, []).uses_from_inventory == []


def test_fill_uses_skips_edited_staple():
    # a staple edited by the user is stored with is_staple=True: still not listed
    r = recipe(ing("salt", "spice"), ing("egg", "egg"))
    out = fill_uses_from_inventory(r, [item("salt", is_staple=True), item("egg")])
    assert out.uses_from_inventory == ["egg"]


def test_check_candidates_splits_passed_and_failed():
    inv = [item("egg", category="egg"), item("spinach", use_soon=True), item("salt", is_staple=True)]
    ok = recipe(ing("egg", "egg"), ing("spinach"), ing("parsley", essential=False), name="Omelette")
    bad = recipe(ing("egg", "egg"), ing("cream", "dairy"), ing("pasta", "pasta"), name="Carbonara")
    nope = recipe(ing("eggplant"), name="Moussaka")
    res = check_candidates([ok, bad, nope], inv + [item("eggplant")], [pref("no eggplant", "eggplant")], FRIDGE_ONLY)
    assert [c.name for c in res.passed] == ["Omelette"]
    cand = res.passed[0]
    assert cand.id == ok.id and cand.time_minutes == 20 and cand.uses_from_inventory == []
    assert cand.ingredients == ["egg: 1", "spinach: 1", "parsley: 1 (optional)"]
    assert [(f.id, f.name, f.reason) for f in res.failed] == [
        (bad.id, "Carbonara", "missing: cream; pantry not scanned: pasta not confirmed"),
        (nope.id, "Moussaka", "violates preferences: eggplant (no eggplant)"),
    ]
