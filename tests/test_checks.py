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


def recipe(*ingredients, name="dish", requested=False):
    return Recipe(name=name, ingredients=list(ingredients), time_minutes=20, requested=requested)


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
                 ing("basil", "vegetable", essential=False), name="Lasagna", requested=True)
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
        'Kung pao chicken needs peanut, not in inventory. The user chose "Only what I have": show only meals '
        "that need nothing to buy (passed candidates), or none"
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


def test_check_reply_named_dish_with_empty_lists_gets_them_from_code():
    # the model forgot the shopping list of a dish the user named: code fills it in, no retry
    res = check(meal_ids=[LASAGNA.id])
    assert res.ok, res.problems
    assert res.reply.shopping_list == ["pasta", "ricotta", "ground beef"]
    assert res.fixes == ["shopping_list [] -> ['pasta', 'ricotta', 'ground beef']"]


# --- cooking mode (T4.5) ----------------------------------------------------------------------------

CARBONARA = recipe(ing("egg", "egg"), ing("bacon", "meat"), ing("cream", "dairy"), ing("pasta", "pasta"),
                   name="Carbonara")
FEAST = recipe(ing("egg", "egg"), ing("bacon", "meat"), ing("cream", "dairy"), ing("pasta", "pasta"),
               ing("leek"), name="Feast")
MODE_CACHE = {r.id: r for r in (OMELETTE, CARBONARA, FEAST, EGGPLANT, LASAGNA)}


def check_mode(mode, **kw):
    return check_reply(AgentReply(**{"message": "m", **kw}), MODE_CACHE, INV, KIDS, ALL_SCANNED, mode)


def test_home_mode_suggested_meal_with_every_missing_item_substituted_passes():
    r = recipe(ing("egg", "egg"), ing("ricotta", "dairy"), name="Ricotta omelette")
    res = check_reply(AgentReply(message="m", meal_ids=[r.id],
                                 substitutions=[Substitution(missing="ricotta", use_instead="cottage cheese")]),
                      {r.id: r}, INV, [], ALL_SCANNED, "home")
    assert res.ok, res.problems
    assert res.reply.shopping_list == []


def test_home_mode_suggested_meal_cannot_hide_behind_a_shopping_list():
    # before T4.5 a failed candidate could be shown with a shopping list; in home mode it is a retry
    res = check_mode("home", meal_ids=[CARBONARA.id], shopping_list=["bacon", "cream"])
    assert res.problems and res.problems[0].startswith("Carbonara needs bacon, cream, pasta, not in inventory")
    assert '"Only what I have"' in res.problems[0]


def test_home_mode_named_dish_still_gets_its_shopping_list():
    res = check_mode("home", meal_ids=[LASAGNA.id])
    assert res.ok and res.reply.shopping_list == ["pasta", "ricotta", "ground beef"]


def test_shop_mode_suggested_meals_get_one_list_built_by_code():
    res = check_mode("shop", meal_ids=[OMELETTE.id, CARBONARA.id], shopping_list=["cream"])
    assert res.ok, res.problems
    assert res.reply.shopping_list == ["bacon", "cream", "pasta"]
    assert res.fixes == ["shopping_list ['cream'] -> ['bacon', 'cream', 'pasta']"]


def test_shop_mode_too_much_to_buy_is_a_retry():
    res = check_mode("shop", meal_ids=[FEAST.id])
    assert res.problems == ["Feast needs 4 items to buy (bacon, cream, pasta, leek); at most 3. "
                            "Replace it with a passed candidate"]


def test_shop_mode_substituted_items_do_not_count():
    res = check_mode("shop", meal_ids=[FEAST.id], substitutions=[Substitution(missing="cream", use_instead="cottage cheese")])
    assert res.ok, res.problems
    assert res.reply.shopping_list == ["bacon", "pasta", "leek"]


def test_shop_mode_preferences_still_hold():
    res = check_mode("shop", meal_ids=[EGGPLANT.id])
    assert res.problems == ["Baba ganoush violates preferences: eggplant (kids dislike eggplant). "
                            "Replace it with a passed candidate"]


def test_shop_mode_message_must_not_name_the_items_to_buy():
    res = check_mode("shop", meal_ids=[CARBONARA.id], message="Carbonara: just pick up some cream.")
    assert any("message names items of the shopping lists (cream)" in p for p in res.problems)


def test_check_candidates_shop_mode_allows_a_few_items_to_buy():
    inv = [item("egg", category="egg"), item("spinach")]
    ok = recipe(ing("egg", "egg"), ing("spinach"), name="Omelette")
    buy = recipe(ing("egg", "egg"), ing("cream", "dairy"), ing("pasta", "pasta"), name="Carbonara")
    many = recipe(ing("cream"), ing("leek"), ing("bacon"), ing("pasta", "pasta"), name="Feast")
    nope = recipe(ing("eggplant"), name="Moussaka")
    res = check_candidates([ok, buy, many, nope], inv, [pref("no eggplant", "eggplant")], FRIDGE_ONLY, "shop")
    assert [(c.name, c.to_buy, c.check_first) for c in res.passed] == [
        ("Omelette", [], []), ("Carbonara", ["cream"], ["pasta"])]
    assert [(f.name, f.reason) for f in res.failed] == [
        ("Feast", "needs 4 items to buy (cream, leek, bacon, pasta); at most 3"),
        ("Moussaka", "violates preferences: eggplant (no eggplant)"),
    ]


def test_check_candidates_home_mode_is_the_default():
    inv = [item("egg", category="egg")]
    buy = recipe(ing("egg", "egg"), ing("cream", "dairy"), name="Custard")
    assert check_candidates([buy], inv, [], ALL_SCANNED).passed == []
    assert [c.to_buy for c in check_candidates([buy], inv, [], ALL_SCANNED, "shop").passed] == [["cream"]]


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


# --- amounts (T6.3b): compared only when both sides are known in units of the same kind ----------------

def amt(name, amount, unit, category="other", location="fridge", qty="some"):
    return item(name, qty=qty, category=category, location=location).model_copy(update={"amount": amount, "unit": unit})


def need(name, amount, category="other", essential=True):
    return Ingredient(name=name, amount=amount, essential=essential, category=category)


@pytest.mark.parametrize("have, unit, want, short", [
    (4, "pcs", "5", True),           # 4 eggs, need 5
    (6, "pcs", "5", False),
    (5, "pcs", "5", False),          # exactly enough
    (1, "kg", "300 g", False),
    (200, "g", "300 g", True),
    (1.5, "l", "500 ml", False),
    (300, "ml", "0.5 l", True),
    (4, "pcs", "5 large", True),     # size word: still a count
])
def test_amounts_compared_when_both_known(have, unit, want, short):
    inv = [amt("egg", have, unit, category="egg")]
    rep = compute_missing(recipe(need("egg", want, "egg")), inv, ALL_SCANNED)
    assert (rep.missing_essential == ["egg"]) is short
    assert bool(rep.not_enough) is short


def test_shortfall_reads_have_and_need():
    rep = compute_missing(recipe(need("egg", "5", "egg")), [amt("egg", 4, "pcs", category="egg")], ALL_SCANNED)
    assert [(s.name, s.have, s.need) for s in rep.not_enough] == [("egg", "4", "5")]
    assert rep.not_enough[0].text() == "not enough egg (have 4, need 5)"
    rep = compute_missing(recipe(need("chicken", "1.5 kg", "meat")), [amt("chicken", 500, "g", "meat")], ALL_SCANNED)
    assert (rep.not_enough[0].have, rep.not_enough[0].need) == ("500 g", "1.5 kg")


@pytest.mark.parametrize("inv_item, want", [
    (item("egg", qty="plenty", category="egg"), "5"),     # no exact amount: presence only
    (amt("milk", 1, "l", "dairy"), "2 cups"),            # unparsable recipe amount
    (amt("milk", 1, "l", "dairy"), "a splash"),
    (amt("butter", 1, "pack", "dairy"), "200 g"),        # pack: presence only
    (amt("butter", 1, "pack", "dairy"), "2 pack"),
    (amt("milk", 100, "g", "dairy"), "500 ml"),          # mass vs volume
    (amt("egg", 2, "pcs", "egg"), "100 g"),              # pcs vs mass
])
def test_presence_only_otherwise(inv_item, want):
    rep = compute_missing(recipe(need(inv_item.name, want)), [inv_item], ALL_SCANNED)
    assert rep.missing_essential == [] and rep.not_enough == []


def test_same_ingredient_twice_adds_up():
    r = recipe(need("egg", "3", "egg"), need("egg", "2", "egg"))
    assert compute_missing(r, [amt("egg", 4, "pcs", "egg")], ALL_SCANNED).not_enough[0].need == "5"
    assert compute_missing(r, [amt("egg", 5, "pcs", "egg")], ALL_SCANNED).not_enough == []


def test_short_optional_is_only_optional():
    rep = compute_missing(recipe(need("parsley", "3", essential=False)), [amt("parsley", 1, "pcs")], ALL_SCANNED)
    assert rep.missing_optional == ["parsley"] and rep.missing_essential == [] and rep.not_enough == []


def test_short_pantry_item_follows_the_unscanned_pantry_rule():
    inv = [amt("rice", 100, "g", "grain", location="pantry")]
    rep = compute_missing(recipe(need("rice", "300 g", "grain")), inv, FRIDGE_ONLY)
    assert rep.check_first == ["rice"] and rep.missing_essential == [] and rep.not_enough[0].name == "rice"


def test_validate_suggestion_fails_with_not_enough_reason():
    res = validate_suggestion(recipe(need("egg", "5", "egg"), ing("cheddar")), [amt("egg", 4, "pcs", "egg")],
                              [], ALL_SCANNED)
    assert not res.ok
    assert res.reason == "missing: cheddar; not enough egg (have 4, need 5)"
    assert validate_suggestion(recipe(need("egg", "5", "egg")), [amt("egg", 6, "pcs", "egg")], [], ALL_SCANNED).ok


def test_check_candidates_home_fails_a_short_meal():
    res = check_candidates([recipe(need("egg", "5", "egg"), name="Frittata")], [amt("egg", 4, "pcs", "egg")], [],
                           ALL_SCANNED)
    assert res.passed == [] and res.failed[0].reason == "not enough egg (have 4, need 5)"


def test_check_candidates_shop_lists_the_short_item():
    res = check_candidates([recipe(need("egg", "5", "egg"), name="Frittata")], [amt("egg", 4, "pcs", "egg")], [],
                           ALL_SCANNED, cook_mode="shop")
    assert res.passed[0].to_buy == ["egg"] and res.passed[0].not_enough == ["not enough egg (have 4, need 5)"]


def test_check_reply_mode_b_lists_the_shortfall():
    r = recipe(need("egg", "5", "egg"), need("spinach", "200 g", "vegetable"), name="Frittata", requested=True)
    res = check_reply(AgentReply(message="Here is the recipe.", meal_ids=[r.id]), {r.id: r},
                      [amt("egg", 4, "pcs", "egg"), item("spinach", category="vegetable")], [], ALL_SCANNED)
    assert res.ok, res.problems
    assert res.reply.shopping_list == ["egg"]
    assert [(s.name, s.have, s.need) for s in res.reply.not_enough] == [("egg", "4", "5")]
    res = check_reply(AgentReply(message="Here is the recipe.", meal_ids=[r.id]), {r.id: r},
                      [amt("egg", 12, "pcs", "egg"), item("spinach", category="vegetable")], [], ALL_SCANNED)
    assert res.reply.shopping_list == [] and res.reply.not_enough == []


def test_check_reply_home_mode_rejects_a_short_suggested_meal():
    r = recipe(need("egg", "5", "egg"), name="Frittata")
    res = check_reply(AgentReply(message="Try this.", meal_ids=[r.id]), {r.id: r}, [amt("egg", 4, "pcs", "egg")], [],
                      ALL_SCANNED)
    assert not res.ok and "not enough egg (have 4, need 5)" in res.problems[0]


def test_substitute_with_too_little_is_sent_back():
    r = recipe(need("ricotta", "400 g", "dairy"), ing("pasta", "pasta"), name="Lasagna", requested=True)
    reply = AgentReply(message="Use your cottage cheese instead of ricotta.", meal_ids=[r.id],
                       substitutions=[Substitution(missing="ricotta", use_instead="cottage cheese")])
    inv = [amt("cottage cheese", 200, "g", "dairy"), item("pasta", category="pasta")]
    res = check_reply(reply, {r.id: r}, inv, [], ALL_SCANNED)
    assert not res.ok
    assert "not enough cottage cheese (have 200 g, need 400 g)" in res.problems[0]
    assert res.reply.shopping_list == ["ricotta"]  # not substituted: the missing item stays on the list


def test_substitute_with_enough_or_no_amount_is_fine():
    r = recipe(need("ricotta", "400 g", "dairy"), name="Lasagna", requested=True)
    reply = AgentReply(message="Use your cottage cheese instead of ricotta.", meal_ids=[r.id],
                       substitutions=[Substitution(missing="ricotta", use_instead="cottage cheese")])
    for sub_item in (amt("cottage cheese", 500, "g", "dairy"), item("cottage cheese", category="dairy")):
        res = check_reply(reply, {r.id: r}, [sub_item], [], ALL_SCANNED)
        assert res.ok, res.problems
        assert res.reply.shopping_list == []
