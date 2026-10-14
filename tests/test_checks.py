from datetime import datetime

import pytest

from app.models import AgentReply, Ingredient, InventoryChange, InventoryItem, Preference, Recipe, ScanState, Substitution
from app.store import Store
from app.tools.checks import (
    check_candidates, check_reply, compute_missing, fill_uses_from_inventory, validate_suggestion,
)
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


# --- check_reply (T2.2: the output validator's logic) ------------------------------------------

OMELETTE = recipe(ing("egg", "egg"), ing("spinach", "vegetable"), name="Spinach omelette")
PEANUT = recipe(ing("chicken", "meat"), ing("peanut", "snack"), name="Kung pao chicken")
EGGPLANT = recipe(ing("aubergine", "vegetable"), name="Baba ganoush")
LASAGNA = recipe(ing("pasta", "pasta"), ing("ricotta", "dairy"), ing("ground beef", "meat"),
                 ing("basil", "vegetable", essential=False), name="Lasagna")
CACHE = {r.id: r for r in (OMELETTE, PEANUT, EGGPLANT, LASAGNA)}
INV = [item("egg"), item("spinach"), item("chicken"), item("cottage cheese"), item("aubergine")]
KIDS = [pref("kids dislike eggplant", "eggplant")]


def check(**kw):
    return check_reply(AgentReply(message="m", **kw), CACHE, INV, KIDS, ALL_SCANNED)


def test_check_reply_valid_mode_a_passes_and_dedupes_ids():
    res = check(meal_ids=[OMELETTE.id, f" {OMELETTE.id} "])
    assert res.ok and res.fixes == [] and res.reply.meal_ids == [OMELETTE.id]


def test_check_reply_unknown_id_lists_known_ids():
    res = check(meal_ids=["abc123"])
    assert not res.ok
    assert "unknown meal id(s) abc123" in res.problems[0]
    assert f"{OMELETTE.id} (Spinach omelette)" in res.problems[0]


def test_check_reply_unknown_id_with_empty_cache():
    res = check_reply(AgentReply(message="m", meal_ids=["x"]), {}, INV, [], ALL_SCANNED)
    assert "call suggest_meals or get_recipe first" in res.problems[0]


def test_check_reply_mode_a_meal_missing_an_ingredient():
    res = check(meal_ids=[OMELETTE.id, PEANUT.id])
    assert res.problems == [
        "Kung pao chicken needs peanut, not in inventory. Replace it or move it to a Mode B answer with a shopping list"
    ]


def test_check_reply_mode_a_meal_checked_against_current_inventory():
    res = check_reply(AgentReply(message="m", meal_ids=[OMELETTE.id]), CACHE, [item("spinach")], [], ALL_SCANNED)
    assert "Spinach omelette needs egg, not in inventory" in res.problems[0]


def test_check_reply_mode_a_pantry_not_scanned():
    r = recipe(ing("pasta", "pasta"), ing("egg", "egg"), name="Egg pasta")
    res = check_reply(AgentReply(message="m", meal_ids=[r.id]), {r.id: r}, INV, [], FRIDGE_ONLY)
    assert "Egg pasta needs pasta, not confirmed (pantry not scanned)" in res.problems[0]


def test_check_reply_mode_a_preference_violation():
    res = check(meal_ids=[EGGPLANT.id])
    assert "Baba ganoush violates preferences: eggplant (kids dislike eggplant)" in res.problems[0]


def test_check_reply_too_many_meals_and_questions():
    res = check(meal_ids=[OMELETTE.id] * 1, questions=["a?", "b?", "c?", "d?"])
    assert res.problems == ["4 questions; ask at most 3"]
    r = [recipe(ing("egg"), name=f"d{i}") for i in range(4)]
    res = check_reply(AgentReply(message="m", meal_ids=[x.id for x in r]), {x.id: x for x in r}, INV, [], ALL_SCANNED)
    assert res.problems == ["4 meals; show at most 3"]


def test_check_reply_mode_b_lists_recomputed_in_code():
    res = check_reply(AgentReply(
        message="m", meal_ids=[LASAGNA.id],
        substitutions=[Substitution(missing="ricotta", use_instead="cottage cheese")],
        shopping_list=["ground beef", "parmesan", "ricotta"], check_first=[],
    ), CACHE, INV, KIDS, FRIDGE_ONLY)
    assert res.ok
    assert res.reply.shopping_list == ["ground beef"]  # ricotta substituted, parmesan invented, basil optional
    assert res.reply.check_first == ["pasta"]  # pantry not scanned
    assert res.fixes == ["shopping_list ['ground beef', 'parmesan', 'ricotta'] -> ['ground beef']",
                         "check_first [] -> ['pasta']"]


def test_check_reply_mode_b_correct_lists_need_no_fix():
    # names are compared after normalize: "Ground beef" / "spaghetti" match the canonical names
    res = check_reply(AgentReply(message="m", meal_ids=[LASAGNA.id], shopping_list=["spaghetti", "ricotta", "Ground beef"]),
                      CACHE, INV, KIDS, ALL_SCANNED)
    assert res.ok and res.fixes == []
    assert res.reply.shopping_list == ["pasta", "ricotta", "ground beef"]


def test_check_reply_mode_b_with_empty_lists_is_checked_as_mode_a():
    # the model forgot the shopping list: the dish fails like a Mode A meal, so the model must add it
    res = check(meal_ids=[LASAGNA.id])
    assert "Lasagna needs pasta, ricotta, ground beef, not in inventory" in res.problems[0]


def test_check_reply_substitute_must_be_in_inventory():
    res = check(meal_ids=[LASAGNA.id], substitutions=[Substitution(missing="ricotta", use_instead="mascarpone")],
                shopping_list=["ground beef"])
    assert res.problems == ["substitute 'mascarpone' (for ricotta) is not in the inventory; "
                            "use an inventory item or put the missing item on the shopping list"]


# --- Mode B message must not list the shopping lists (T4.2) ------------------------------------------

@pytest.mark.parametrize("message, names, dishes, expected", [
    ("You need to buy ground beef and ricotta.", ["ground beef", "ricotta"], [], ["ground beef", "ricotta"]),
    ("Check your pantry for lasagna noodles.", ["lasagna noodle"], [], ["lasagna noodle"]),
    ("Grab some tomatoes.", ["tomato"], [], ["tomato"]),
    ("Use ground-beef or not.", ["ground beef"], [], ["ground beef"]),
    ("The eggplant is fine.", ["egg"], [], []),  # whole words only
    ("For the Beef lasagna you need 2 things.", ["beef"], ["Beef lasagna"], []),  # dish names do not count
    ("You can make it with your cottage cheese instead; 2 things to buy.", ["ground beef", "pasta"], [], []),
])
def test_items_named_in(message, names, dishes, expected):
    from app.tools.checks import items_named_in

    assert items_named_in(message, names, dishes) == expected


def test_check_reply_mode_b_message_listing_the_shopping_list_is_a_problem():
    res = check_reply(AgentReply(
        message="For lasagna you need to buy ground beef and ricotta.", meal_ids=[LASAGNA.id],
        substitutions=[Substitution(missing="ricotta", use_instead="cottage cheese")], shopping_list=["ground beef"],
    ), CACHE, INV, KIDS, ALL_SCANNED)
    assert len(res.problems) == 1 and "message names items of the shopping lists (pasta, ground beef)" not in res.problems[0]
    assert "message names items of the shopping lists (ground beef)" in res.problems[0]  # ricotta is substituted


def test_check_reply_mode_b_short_message_with_substitution_passes():
    res = check_reply(AgentReply(
        message="You can make lasagna with your cottage cheese instead of ricotta; you need 2 things from the shop.",
        meal_ids=[LASAGNA.id], substitutions=[Substitution(missing="ricotta", use_instead="cottage cheese")],
        shopping_list=["ground beef", "pasta"],
    ), CACHE, INV, KIDS, ALL_SCANNED)
    assert res.ok, res.problems
