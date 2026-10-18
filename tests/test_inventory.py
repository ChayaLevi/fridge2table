from datetime import datetime

import pytest

from app.models import InventoryChange, InventoryItem, ScanState
from app.store import Store
from app.tools.inventory import (
    get_inventory,
    inventory_summary,
    merge_recognized,
    staple_names,
    update_inventory,
)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "inv.db")
    yield s
    s.close()


def item(name, **kw):
    base = dict(
        id=f"id-{name}", name=name, display_name=name.title(), category="vegetable",
        qty_level="some", location="fridge", confidence=0.9, uncertain=False,
        source="photo", updated_at=datetime(2026, 10, 12, 12, 0),
    )
    base.update(kw)
    return InventoryItem(**base)


def add(name, **kw):
    return InventoryChange(op="add", name=name, **kw)


def by_name(items):
    return {i.name: i for i in items}


def stored_names(store):
    return [i.name for i in store.load_inventory()]


# get_inventory

def test_empty_store_has_all_staples(store):
    inv = get_inventory(store)
    assert [i.name for i in inv] == list(staple_names())
    assert len(inv) == 15
    for i in inv:
        assert i.is_staple and i.source == "staple" and i.qty_level == "plenty" and i.confidence == 1.0


def test_staple_names_are_canonical():
    assert "chili flakes" in staple_names()
    assert "all-purpose flour" in staple_names()


def test_stored_items_come_first(store):
    store.save_inventory([item("spinach"), item("milk")])
    inv = get_inventory(store)
    assert [i.name for i in inv[:2]] == ["spinach", "milk"]
    assert len(inv) == 17


def test_removed_staple_is_hidden(store):
    store.set_staple_removed("soy sauce")
    assert "soy sauce" not in by_name(get_inventory(store))


# update_inventory: add

def test_add_normalizes_name(store):
    inv = update_inventory(store, [add("Fresh Scallions", location="fridge", qty_level="low")])
    gi = by_name(inv)["green onion"]
    assert gi.display_name == "Fresh Scallions"
    assert gi.qty_level == "low" and gi.source == "chat" and gi.confidence == 1.0


def test_add_defaults(store):
    update_inventory(store, [add("ricotta")])
    r = store.load_inventory()[0]
    assert (r.qty_level, r.location, r.category, r.use_soon, r.uncertain) == ("some", "fridge", "other", False, False)


def test_add_existing_updates_instead_of_duplicating(store):
    store.save_inventory([item("tomato", qty_level="low", confidence=0.5, uncertain=True)])
    update_inventory(store, [add("tomatoes", qty_level="plenty", use_soon=True)])
    stored = store.load_inventory()
    assert len(stored) == 1
    t = stored[0]
    assert t.qty_level == "plenty" and t.use_soon and not t.uncertain and t.confidence == 1.0
    assert t.display_name == "Tomato"  # not given in the change, so kept


def test_add_twice_in_one_call_gives_one_item(store):
    update_inventory(store, [add("egg"), add("2 large eggs", qty_level="plenty")])
    assert stored_names(store) == ["egg"]
    assert store.load_inventory()[0].qty_level == "plenty"


def test_manual_source(store):
    update_inventory(store, [add("milk")], source="manual")
    assert store.load_inventory()[0].source == "manual"


def test_add_removed_staple_restores_it(store):
    store.set_staple_removed("salt")
    inv = update_inventory(store, [add("salt")])
    assert "salt" in by_name(inv)
    assert "salt" not in store.load_removed_staples()


# update_inventory: remove / set_qty / set_use_soon / rename

def test_remove(store):
    store.save_inventory([item("spinach"), item("milk")])
    inv = update_inventory(store, [InventoryChange(op="remove", name="Spinach")])
    assert stored_names(store) == ["milk"]
    assert "spinach" not in by_name(inv)


def test_remove_unknown_is_ignored(store):
    store.save_inventory([item("milk")])
    update_inventory(store, [InventoryChange(op="remove", name="caviar")])
    assert stored_names(store) == ["milk"]


def test_remove_staple_records_it(store):
    inv = update_inventory(store, [InventoryChange(op="remove", name="olive oil")])
    assert "olive oil" not in by_name(inv)
    assert store.load_removed_staples() == {"olive oil"}
    assert store.load_inventory() == []
    assert "olive oil" not in by_name(get_inventory(store))  # still gone on the next read


def test_remove_staple_by_variant(store):
    update_inventory(store, [InventoryChange(op="remove", name="chilli flakes")])
    assert store.load_removed_staples() == {"chili flakes"}


def test_set_qty(store):
    store.save_inventory([item("milk", qty_level="plenty")])
    update_inventory(store, [InventoryChange(op="set_qty", name="milk", qty_level="low")])
    assert store.load_inventory()[0].qty_level == "low"


def test_set_qty_below_low_removes(store):
    store.save_inventory([item("milk", qty_level="low")])
    update_inventory(store, [InventoryChange(op="set_qty", name="milk", qty_level=None)])
    assert store.load_inventory() == []


def test_set_qty_on_staple_materializes_it(store):
    inv = update_inventory(store, [InventoryChange(op="set_qty", name="sugar", qty_level="low")])
    assert by_name(inv)["sugar"].qty_level == "low"
    assert [i.name for i in inv].count("sugar") == 1
    s = store.load_inventory()[0]
    assert s.name == "sugar" and s.is_staple and s.source == "chat"


def test_set_use_soon(store):
    store.save_inventory([item("spinach")])
    update_inventory(store, [InventoryChange(op="set_use_soon", name="spinach", use_soon=True)])
    assert store.load_inventory()[0].use_soon
    update_inventory(store, [InventoryChange(op="set_use_soon", name="spinach", use_soon=False)])
    assert not store.load_inventory()[0].use_soon


def test_rename_resolves_uncertain_item(store):
    store.save_inventory([item("white container", confidence=0.3, uncertain=True)])
    update_inventory(store, [InventoryChange(op="rename", name="white container", new_name="Leftover Rice")])
    r = store.load_inventory()[0]
    assert r.name == "leftover rice" and r.display_name == "Leftover Rice"
    assert not r.uncertain and r.confidence == 1.0


def test_rename_onto_existing_merges(store):
    store.save_inventory([item("white container", use_soon=True), item("rice")])
    update_inventory(store, [InventoryChange(op="rename", name="white container", new_name="rice")])
    stored = store.load_inventory()
    assert [i.name for i in stored] == ["rice"]
    assert stored[0].use_soon


# merge_recognized

def staple(name):
    return InventoryChange(op="add_staple", name=name)


def test_add_staple_shows_it_as_a_staple_and_survives_reopen(tmp_path):
    s = Store(tmp_path / "inv.db")
    update_inventory(s, [staple("White Rice"), staple("garlic powder")])
    s.close()
    s = Store(tmp_path / "inv.db")
    items = by_name(get_inventory(s))
    assert items["white rice"].source == "staple" and items["white rice"].is_staple
    assert items["garlic powder"].qty_level == "plenty"
    assert [i.name for i in get_inventory(s) if i.source == "staple"][-2:] == ["white rice", "garlic powder"]
    assert "white rice" in inventory_summary(get_inventory(s), ScanState(scanned={})).splitlines()[-1]
    s.close()


def test_add_staple_twice_or_a_default_one_adds_nothing_new(store):
    update_inventory(store, [staple("rice"), staple("rice"), staple("salt")])
    assert store.load_custom_staples() == ["rice"]
    assert len(get_inventory(store)) == len(staple_names()) + 1


def test_add_staple_restores_a_removed_default_staple(store):
    update_inventory(store, [InventoryChange(op="remove", name="salt")])
    update_inventory(store, [staple("salt")])
    assert by_name(get_inventory(store))["salt"].source == "staple"
    assert store.load_custom_staples() == []


def test_add_staple_replaces_a_stored_item_with_that_name(store):
    update_inventory(store, [add("rice", category="grain", location="pantry", qty_level="low")])
    update_inventory(store, [staple("rice")])
    rice = [i for i in get_inventory(store) if i.name == "rice"]
    assert len(rice) == 1 and rice[0].source == "staple"


def test_remove_user_staple_deletes_it(store):
    update_inventory(store, [staple("rice")])
    update_inventory(store, [InventoryChange(op="remove", name="rice")])
    assert "rice" not in by_name(get_inventory(store))
    assert store.load_custom_staples() == [] and "rice" not in store.load_removed_staples()


def test_user_staple_counts_as_available_in_checks(store):
    from app.models import Ingredient, Recipe
    from app.tools.checks import compute_missing

    recipe = Recipe(name="Rice bowl", time_minutes=20,
                    ingredients=[Ingredient(name="rice", amount="1 cup", essential=True, category="grain")])
    scanned = ScanState(scanned={"pantry": datetime(2026, 10, 14)})
    assert compute_missing(recipe, get_inventory(store), scanned).missing_essential == ["rice"]
    update_inventory(store, [staple("rice")])
    assert compute_missing(recipe, get_inventory(store), scanned).missing_essential == []


def test_reset_all_clears_user_staples(store):
    update_inventory(store, [staple("rice")])
    store.reset_all()
    assert store.load_custom_staples() == []


def test_merge_adds_new_items(store):
    inv = merge_recognized(store, [item("Tomatoes"), item("Scallion")])
    assert {"tomato", "green onion"} <= set(by_name(inv))
    assert stored_names(store) == ["tomato", "green onion"]


def test_merge_updates_qty_and_confidence(store):
    store.save_inventory([item("milk", id="m1", qty_level="plenty", confidence=0.9)])
    merge_recognized(store, [item("milk", id="new", qty_level="low", confidence=0.5, uncertain=True)])
    stored = store.load_inventory()
    assert len(stored) == 1
    m = stored[0]
    assert m.id == "m1" and m.qty_level == "low" and m.confidence == 0.5 and m.uncertain


def test_merge_never_clears_use_soon(store):
    store.save_inventory([item("spinach", use_soon=True, source="chat")])
    merge_recognized(store, [item("spinach", use_soon=False, qty_level="plenty")])
    s = store.load_inventory()[0]
    assert s.use_soon and s.qty_level == "plenty"


def test_merge_never_overrides_manual(store):
    store.save_inventory([item("cheddar", source="manual", qty_level="plenty", confidence=1.0)])
    merge_recognized(store, [item("cheddar", qty_level="low", confidence=0.4, uncertain=True)])
    c = store.load_inventory()[0]
    assert (c.qty_level, c.confidence, c.uncertain, c.source) == ("plenty", 1.0, False, "manual")


def test_merge_never_removes(store):
    store.save_inventory([item("milk"), item("butter")])
    merge_recognized(store, [item("egg")])
    assert stored_names(store) == ["milk", "butter", "egg"]


def test_merge_duplicates_keep_higher_confidence(store):
    merge_recognized(store, [
        item("egg", id="a", confidence=0.5, use_soon=True),
        item("eggs", id="b", confidence=0.95, qty_level="plenty"),
    ])
    stored = store.load_inventory()
    assert len(stored) == 1
    e = stored[0]
    assert e.id == "b" and e.confidence == 0.95 and e.qty_level == "plenty" and e.use_soon


def test_merge_recognized_staple(store):
    inv = merge_recognized(store, [item("olive oil", category="condiment", location="pantry")])
    assert [i.name for i in inv].count("olive oil") == 1
    assert store.load_inventory()[0].is_staple


# inventory_summary

def test_summary_marks_places_and_flags(store):
    store.save_inventory([
        item("milk"),
        item("spinach", use_soon=True, qty_level="low"),
        item("white container", uncertain=True, confidence=0.3),
        item("peas", location="freezer"),
    ])
    scan = ScanState(scanned={"fridge": datetime(2026, 10, 12, 9, 0)})
    text = inventory_summary(get_inventory(store), scan)
    lines = text.splitlines()
    assert lines[0].startswith("fridge (scanned 2026-10-12): white container (some, UNCERTAIN)")
    assert "spinach (low, USE SOON)" in lines[0]
    assert "milk (some)" in lines[0]
    assert lines[1] == "freezer (NOT SCANNED): peas (some)"
    assert lines[2] == "pantry (NOT SCANNED): nothing"
    assert lines[3].startswith("staples (assumed present): salt, black pepper")


def test_summary_freezer_declined_and_removed_staple(store):
    store.set_staple_removed("salt")
    text = inventory_summary(get_inventory(store), ScanState(scanned={}, freezer_declined=True))
    assert "freezer (NOT SCANNED, user declined)" in text
    assert "salt" not in text.splitlines()[-1].split(": ")[1].split(", ")


def test_summary_length_for_60_items(store):
    names = [
        "milk", "egg", "butter", "cheddar", "greek yogurt", "cream cheese", "parmesan", "mozzarella",
        "spinach", "carrot", "broccoli", "cucumber", "tomato", "bell pepper", "zucchini", "eggplant",
        "lettuce", "green onion", "lemon", "lime", "apple", "orange juice", "chicken", "ground beef",
        "bacon", "ham", "salmon", "tofu", "hummus", "ketchup", "mayonnaise", "mustard", "jam",
        "peas", "corn", "ice cream", "frozen berries", "fish sticks", "pizza", "dumpling",
        "pasta", "rice", "oats", "lentil", "chickpea", "canned tomato", "tuna", "coconut milk",
        "peanut butter", "honey", "bread", "tortilla", "crackers", "cereal", "almond", "walnut",
        "raisin", "breadcrumbs", "cornstarch", "white container",
    ]
    locs = ["fridge"] * 33 + ["freezer"] * 7 + ["pantry"] * 20
    store.save_inventory([
        item(n, id=str(k), location=loc, use_soon=k % 9 == 0, uncertain=k % 13 == 0)
        for k, (n, loc) in enumerate(zip(names, locs))
    ])
    scan = ScanState(scanned={loc: datetime(2026, 10, 12) for loc in ("fridge", "freezer", "pantry")})
    text = inventory_summary(get_inventory(store), scan)
    assert len(names) == 60
    assert all(n in text for n in names)
    assert len(text) < 1500, len(text)


# --- not seen in a new photo of the same place ------------------------------------------------------

def test_rescan_marks_items_of_that_place_not_seen_without_removing_them(store):
    store.save_inventory([item("milk"), item("butter"), item("rice", location="pantry")])
    merge_recognized(store, [item("milk", confidence=0.95)], places=["fridge"])
    inv = by_name(get_inventory(store))
    assert inv["butter"].not_seen and not inv["milk"].not_seen
    assert not inv["rice"].not_seen  # the pantry was not photographed
    assert not inv["salt"].not_seen  # staples are never flagged
    assert stored_names(store) == ["milk", "butter", "rice"]


def test_without_places_nothing_is_marked_not_seen(store):
    store.save_inventory([item("milk"), item("butter")])
    merge_recognized(store, [item("milk")])
    assert not any(i.not_seen for i in get_inventory(store))


def test_seen_again_clears_not_seen_even_for_manual_items(store):
    store.save_inventory([item("butter", source="manual", not_seen=True)])
    merge_recognized(store, [item("butter", qty_level="low")], places=["fridge"])
    butter = by_name(get_inventory(store))["butter"]
    assert not butter.not_seen and butter.qty_level == "some"  # manual: quantity not overridden


def test_confirm_clears_not_seen_and_uncertain(store):
    store.save_inventory([item("butter", not_seen=True), item("white container", uncertain=True, confidence=0.3)])
    update_inventory(store, [InventoryChange(op="confirm", name="butter"),
                             InventoryChange(op="confirm", name="white container"),
                             InventoryChange(op="confirm", name="salt")], source="manual")
    inv = by_name(get_inventory(store))
    assert not inv["butter"].not_seen and inv["butter"].source == "manual"
    assert not inv["white container"].uncertain and inv["white container"].confidence == 1.0
    assert inv["salt"].source == "staple"  # a virtual staple is left alone


def test_any_edit_clears_not_seen(store):
    store.save_inventory([item("butter", not_seen=True)])
    update_inventory(store, [InventoryChange(op="set_qty", name="butter", qty_level="low")], source="manual")
    assert not by_name(get_inventory(store))["butter"].not_seen


def test_summary_marks_not_seen_items_first(store):
    store.save_inventory([item("milk"), item("butter", not_seen=True)])
    line = inventory_summary(get_inventory(store), ScanState(scanned={})).splitlines()[0]
    assert line.index("butter (some, NOT SEEN IN LAST PHOTO)") < line.index("milk")


# --- exact amounts (T6.3) ---------------------------------------------------------------------------

def test_set_amount_keeps_qty_level_and_is_stored_as_entered(store):
    update_inventory(store, [add("milk", category="dairy", qty_level="low")])
    inv = by_name(update_inventory(store, [InventoryChange(op="set_amount", name="milk", amount=1.5, unit="l")]))
    assert (inv["milk"].amount, inv["milk"].unit, inv["milk"].qty_level) == (1.5, "l", "low")
    assert inv["milk"].amount_text == "1.5 l"
    assert by_name(Store(store.path).load_inventory())["milk"].unit == "l"  # persisted


def test_set_amount_default_unit_by_category(store):
    update_inventory(store, [add("egg", category="egg"), add("chicken", category="meat"), add("milk", category="dairy")])
    inv = by_name(update_inventory(store, [
        InventoryChange(op="set_amount", name="eggs", amount=6),
        InventoryChange(op="set_amount", name="chicken", amount=500),
        InventoryChange(op="set_amount", name="milk", amount=2),
    ]))
    assert (inv["egg"].amount, inv["egg"].unit) == (6, "pcs")
    assert (inv["chicken"].amount, inv["chicken"].unit) == (500, "g")
    assert (inv["milk"].amount, inv["milk"].unit) == (2, "l")


@pytest.mark.parametrize("amount", [None, 0])
def test_set_amount_none_or_zero_clears_it(store, amount):
    update_inventory(store, [add("milk", amount=2, unit="l")])
    inv = by_name(update_inventory(store, [InventoryChange(op="set_amount", name="milk", amount=amount)]))
    assert "milk" in inv and inv["milk"].amount is None and inv["milk"].unit is None
    assert inv["milk"].amount_text == ""


def test_set_amount_on_a_missing_item_is_ignored(store):
    assert "milk" not in by_name(update_inventory(store, [InventoryChange(op="set_amount", name="milk", amount=2)]))


def test_set_amount_rejects_negative():
    with pytest.raises(ValueError):
        InventoryChange(op="set_amount", name="milk", amount=-1)


def test_add_reads_the_amount_from_the_name(store):
    inv = by_name(update_inventory(store, [add("milk 2 l", location="fridge"), add("6 eggs", category="egg")],
                                   source="manual"))
    assert (inv["milk"].amount, inv["milk"].unit, inv["milk"].display_name) == (2, "l", "milk")
    assert (inv["egg"].amount, inv["egg"].unit, inv["egg"].display_name) == (6, "pcs", "eggs")


def test_add_without_amount_keeps_the_stored_amount(store):
    update_inventory(store, [add("milk", amount=2, unit="l")])
    inv = by_name(update_inventory(store, [add("milk", qty_level="plenty")]))
    assert (inv["milk"].amount, inv["milk"].unit, inv["milk"].qty_level) == (2, "l", "plenty")


def test_rename_confirm_and_qty_keep_the_amount(store):
    store.save_inventory([item("white bottle", uncertain=True, confidence=0.3, category="dairy")])
    update_inventory(store, [InventoryChange(op="set_amount", name="white bottle", amount=1, unit="l")])
    update_inventory(store, [InventoryChange(op="confirm", name="white bottle")])
    update_inventory(store, [InventoryChange(op="set_qty", name="white bottle", qty_level="low")])
    inv = by_name(update_inventory(store, [InventoryChange(op="rename", name="white bottle", new_name="milk")]))
    assert (inv["milk"].amount, inv["milk"].unit) == (1, "l")


def test_rename_onto_an_existing_item_keeps_an_amount(store):
    update_inventory(store, [add("milk"), add("white bottle", amount=1, unit="l")])
    inv = by_name(update_inventory(store, [InventoryChange(op="rename", name="white bottle", new_name="milk")]))
    assert (inv["milk"].amount, inv["milk"].unit) == (1, "l")


def test_recognition_keeps_the_users_amount(store):
    update_inventory(store, [add("milk", amount=2, unit="l")], source="chat")
    inv = by_name(merge_recognized(store, [item("milk", qty_level="low")], places=["fridge"]))
    assert (inv["milk"].amount, inv["milk"].qty_level) == (2, "low")


def test_summary_shows_the_amount(store):
    update_inventory(store, [add("milk", amount=2, unit="l"), add("chicken", category="meat", amount=1500, unit="g"),
                             add("egg")])
    text = inventory_summary(get_inventory(store), ScanState(scanned={}))
    assert "milk (2 l, some)" in text
    assert "chicken (1.5 kg, some)" in text
    assert "egg (some)" in text


def test_add_with_an_amount_keeps_the_display_name_of_an_existing_item(store):
    update_inventory(store, [add("egg", display_name="Free-range eggs")])
    inv = by_name(update_inventory(store, [add("6 eggs")], source="manual"))
    assert (inv["egg"].display_name, inv["egg"].amount) == ("Free-range eggs", 6)


# --- "Bought it" (T6.4) ----------------------------------------------------------------------------------

from app.models import BoughtItem  # noqa: E402
from app.tools.inventory import location_for, mark_bought, package_sizes  # noqa: E402


def bought(name, **kw):
    return BoughtItem(name=name, **kw)


def test_bought_new_item_is_plenty_in_its_place_without_amount(store):
    mark_bought(store, [bought("ground beef", category="meat"), bought("lasagna noodle", category="pasta"),
                        bought("peas", category="frozen")])
    inv = by_name(get_inventory(store))
    beef = inv["ground beef"]
    assert (beef.qty_level, beef.location, beef.category, beef.amount, beef.source) == ("plenty", "fridge", "meat", None, "manual")
    assert inv["lasagna noodle"].location == "pantry"
    assert inv["pea"].location == "freezer"


def test_bought_new_item_without_category_goes_to_the_fridge(store):
    mark_bought(store, [bought("mystery")])
    item_ = by_name(get_inventory(store))["mystery"]
    assert (item_.location, item_.category, item_.qty_level) == ("fridge", "other", "plenty")


def test_bought_existing_item_becomes_plenty_and_keeps_its_place(store):
    update_inventory(store, [add("milk", category="dairy", location="freezer", qty_level="low")])
    mark_bought(store, [bought("milk", category="dairy")])
    milk = by_name(get_inventory(store))["milk"]
    assert (milk.qty_level, milk.location) == ("plenty", "freezer")


def test_bought_without_amount_clears_a_stale_amount_and_returns_it(store):
    update_inventory(store, [add("egg", category="egg", amount=4, unit="pcs")])
    previous = mark_bought(store, [bought("eggs", category="egg")])
    egg = by_name(get_inventory(store))["egg"]
    assert (egg.qty_level, egg.amount, egg.unit) == ("plenty", None, None)
    assert previous == {"egg": (4, "pcs")}


def test_chip_after_bought_adds_to_what_the_item_had(store):
    update_inventory(store, [add("egg", category="egg", amount=4, unit="pcs")])
    mark_bought(store, [bought("egg")])
    mark_bought(store, [bought("egg", amount=12, unit="pcs", had_amount=4, had_unit="pcs")])
    egg = by_name(get_inventory(store))["egg"]
    assert (egg.amount, egg.unit, egg.amount_text) == (16, "pcs", "16 pcs")


def test_amount_adds_to_the_current_amount_in_its_unit(store):
    update_inventory(store, [add("rice", category="grain", amount=1, unit="kg")])
    mark_bought(store, [bought("rice", amount=500, unit="g")])
    flour = by_name(get_inventory(store))["rice"]
    assert (flour.amount, flour.unit, flour.amount_text) == (1.5, "kg", "1.5 kg")


def test_amount_of_another_kind_replaces(store):
    update_inventory(store, [add("butter", category="dairy", amount=1, unit="pack")])
    mark_bought(store, [bought("butter", amount=250, unit="g")])
    butter = by_name(get_inventory(store))["butter"]
    assert (butter.amount, butter.unit) == (250, "g")


def test_chip_on_a_new_item_sets_the_amount(store):
    mark_bought(store, [bought("ground beef", category="meat")])
    mark_bought(store, [bought("ground beef", category="meat", amount=500, unit="g")])
    beef = by_name(get_inventory(store))["ground beef"]
    assert (beef.amount_text, beef.qty_level) == ("500 g", "plenty")


def test_new_item_with_an_amount_and_no_unit_uses_the_category_default(store):
    mark_bought(store, [bought("milk", category="dairy", amount=2)])
    assert by_name(get_inventory(store))["milk"].amount_text == "2 l"


def test_staple_names_are_ignored(store):
    before = by_name(get_inventory(store))
    mark_bought(store, [bought("salt", category="spice"), bought("olive oil", category="condiment")])
    after = by_name(get_inventory(store))
    assert after["salt"].is_staple and after["salt"].source == "staple"
    assert store.load_inventory() == [] and before.keys() == after.keys()


def test_a_removed_staple_comes_back(store):
    update_inventory(store, [InventoryChange(op="remove", name="salt")])
    assert "salt" not in by_name(get_inventory(store))
    mark_bought(store, [bought("salt", category="spice")])
    assert by_name(get_inventory(store))["salt"].source == "staple"


def test_bought_names_are_normalized_and_deduplicated(store):
    mark_bought(store, [bought("Eggs", category="egg"), bought("egg", category="egg", amount=6, unit="pcs")])
    inv = [i for i in get_inventory(store) if i.name == "egg"]
    assert len(inv) == 1 and inv[0].amount is None  # the second entry for the same name is ignored


def test_package_sizes():
    assert [s.text for s in package_sizes("eggs", "egg")] == ["6 pcs", "12 pcs", "18 pcs"]
    assert [s.text for s in package_sizes("sugar", "baking")] == ["500 g", "1 kg"]
    assert [s.text for s in package_sizes("milk", "dairy")] == ["1 l", "2 l"]
    assert [s.text for s in package_sizes("cheddar", "dairy")] == ["200 g", "500 g"]
    assert [s.text for s in package_sizes("ground beef", "meat")] == ["500 g", "1 kg"]
    assert [s.text for s in package_sizes("salmon", "fish")] == ["500 g", "1 kg"]
    assert [s.text for s in package_sizes("thing", "other")] == ["1 pack", "2 packs"]
    assert [s.text for s in package_sizes("thing", None)] == ["1 pack", "2 packs"]


def test_location_for():
    assert location_for("pasta") == "pantry" and location_for("spice") == "pantry"
    assert location_for("frozen") == "freezer"
    assert location_for("meat") == "fridge" and location_for(None) == "fridge"


# --- "I made it" (T6.1) ----------------------------------------------------------------------------------

from app.models import Ingredient, Recipe, Substitution  # noqa: E402
from app.tools.inventory import mark_made, undo_made  # noqa: E402


def dish_of(*ings):
    """ings: (name, amount[, essential])."""
    return Recipe(name="Dish", time_minutes=20, ingredients=[
        Ingredient(name=i[0], amount=i[1], essential=i[2] if len(i) > 2 else True, category="other") for i in ings])


def test_made_subtracts_an_exact_amount(store):
    update_inventory(store, [add("egg", category="egg", qty_level="plenty", amount=12, unit="pcs"),
                             add("milk", category="dairy", amount=1, unit="l")])
    res = mark_made(store, dish_of(("egg", "5"), ("milk", "250 ml")))
    inv = by_name(get_inventory(store))
    assert (inv["egg"].amount, inv["egg"].unit, inv["egg"].qty_level) == (7, "pcs", "plenty")
    assert (inv["milk"].amount, inv["milk"].unit, inv["milk"].amount_text) == (0.75, "l", "750 ml")
    assert res.summary() == "egg 12 → 7 pcs, milk 1 l → 750 ml"


def test_made_sums_an_ingredient_listed_twice(store):
    update_inventory(store, [add("egg", category="egg", amount=6, unit="pcs")])
    mark_made(store, dish_of(("egg", "3"), ("egg", "1, to glaze")))
    assert by_name(get_inventory(store))["egg"].amount == 2


@pytest.mark.parametrize("have, need", [(5, "5"), (4, "5")])
def test_made_subtract_to_zero_or_below_removes(store, have, need):
    update_inventory(store, [add("egg", category="egg", amount=have, unit="pcs")])
    res = mark_made(store, dish_of(("egg", need)))
    assert "egg" not in by_name(get_inventory(store))
    assert res.summary() == "egg removed"


def test_made_without_amount_steps_the_level_down(store):
    update_inventory(store, [add("spinach", qty_level="plenty"), add("onion", qty_level="some"),
                             add("cheddar", qty_level="low")])
    res = mark_made(store, dish_of(("spinach", "200 g"), ("onion", "1"), ("cheddar", "50 g")))
    inv = by_name(get_inventory(store))
    assert inv["spinach"].qty_level == "some" and inv["onion"].qty_level == "low" and "cheddar" not in inv
    assert res.summary() == "spinach plenty → some, onion some → low, cheddar removed"


@pytest.mark.parametrize("recipe_amount", ["2 cups", "a splash", "500 g"])
def test_made_incompatible_units_step_down_and_keep_the_amount(store, recipe_amount):
    update_inventory(store, [add("milk", category="dairy", qty_level="plenty", amount=1, unit="l")])
    mark_made(store, dish_of(("milk", recipe_amount)))
    milk = by_name(get_inventory(store))["milk"]
    assert (milk.qty_level, milk.amount, milk.unit) == ("some", 1, "l")


def test_made_deducts_the_substitute(store):
    update_inventory(store, [add("cottage cheese", category="dairy", amount=500, unit="g")])
    res = mark_made(store, dish_of(("ricotta", "400 g"), ("pasta", "250 g")),
                    [Substitution(missing="ricotta", use_instead="cottage cheese")])
    inv = by_name(get_inventory(store))
    assert inv["cottage cheese"].amount == 100 and "ricotta" not in inv
    assert res.summary() == "cottage cheese 500 → 100 g"  # pasta is not in the inventory: skipped


def test_made_never_touches_staples(store):
    update_inventory(store, [add("egg", qty_level="plenty")])
    res = mark_made(store, dish_of(("salt", "1 tsp"), ("olive oil", "2 tbsp"), ("egg", "2")))
    inv = by_name(get_inventory(store))
    assert inv["salt"].source == "staple" and inv["olive oil"].source == "staple"
    assert [c.name for c in res.changes] == ["egg"]


def test_made_never_touches_an_edited_staple(store):
    update_inventory(store, [InventoryChange(op="set_qty", name="salt", qty_level="low")])  # now a stored staple
    mark_made(store, dish_of(("salt", "1 tsp")))
    assert by_name(get_inventory(store))["salt"].qty_level == "low"


def test_made_deducts_an_optional_ingredient_only_if_present(store):
    update_inventory(store, [add("parsley", qty_level="some")])
    res = mark_made(store, dish_of(("parsley", "a handful", False), ("chive", "1 tbsp", False)))
    assert by_name(get_inventory(store))["parsley"].qty_level == "low"
    assert [c.name for c in res.changes] == ["parsley"]


def test_undo_restores_the_exact_previous_state(store):
    update_inventory(store, [add("egg", category="egg", qty_level="plenty", amount=12, unit="pcs", use_soon=True),
                             add("cheddar", qty_level="low"), add("spinach", qty_level="plenty")])
    before = {i.name: i.model_dump() for i in store.load_inventory()}
    res = mark_made(store, dish_of(("egg", "5"), ("cheddar", "50 g"), ("spinach", "100 g")))
    assert "cheddar" not in by_name(get_inventory(store))
    assert undo_made(store, res.token) is True
    after = {i.name: i.model_dump() for i in store.load_inventory()}
    assert after == before  # amounts, levels, flags, ids, sources, times
    assert undo_made(store, res.token) is False  # works once


def test_undo_with_an_unknown_token(store):
    assert undo_made(store, "nope") is False
