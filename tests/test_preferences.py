import pytest

from app.store import Store
from app.tools.preferences import (
    format_preferences,
    get_preferences,
    preferences_summary,
    save_preference,
)


@pytest.fixture
def store():
    s = Store(":memory:")
    yield s
    s.close()


def test_save_normalizes_avoid(store):
    p = save_preference(store, "kids hate aubergines", ["Aubergines", "fresh Scallions"])
    assert p.avoid == ["eggplant", "green onion"]
    assert p.text == "kids hate aubergines"
    assert get_preferences(store) == [p]


def test_save_dedupes_avoid_within_one_call(store):
    p = save_preference(store, "no eggplant", ["eggplant", "aubergine", "eggplants", ""])
    assert p.avoid == ["eggplant"]


def test_save_persists_across_reopen(tmp_path):
    s = Store(tmp_path / "x.db")
    p = save_preference(s, "no mushrooms", ["mushroom"])
    s.close()
    s = Store(tmp_path / "x.db")
    assert get_preferences(s) == [p]
    s.close()


def test_same_text_is_not_duplicated(store):
    a = save_preference(store, "Kids dislike eggplant", ["eggplant"])
    b = save_preference(store, "  kids   dislike EGGPLANT ", ["eggplant"])
    assert b.id == a.id
    assert len(get_preferences(store)) == 1


def test_same_text_extends_avoid(store):
    a = save_preference(store, "kids are picky", ["eggplant"])
    b = save_preference(store, "kids are picky", ["mushrooms"])
    assert b.id == a.id
    assert b.avoid == ["eggplant", "mushroom"]
    assert get_preferences(store)[0].avoid == ["eggplant", "mushroom"]


def test_same_avoid_other_text_is_not_duplicated(store):
    a = save_preference(store, "kids hated the eggplant", ["eggplant"])
    b = save_preference(store, "no aubergine please", ["aubergine"])
    assert b == a
    assert len(get_preferences(store)) == 1


def test_partial_overlap_keeps_only_new_items(store):
    save_preference(store, "kids hated the eggplant", ["eggplant"])
    b = save_preference(store, "no eggplant or zucchini", ["eggplant", "courgette"])
    assert b.avoid == ["zucchini"]
    prefs = get_preferences(store)
    assert len(prefs) == 2
    assert sorted(a for p in prefs for a in p.avoid) == ["eggplant", "zucchini"]


def test_text_only_preference(store):
    p = save_preference(store, "we like spicy food")
    assert p.avoid == []
    assert save_preference(store, "We like spicy food", []).id == p.id
    assert len(get_preferences(store)) == 1


def test_avoid_only_gets_a_text(store):
    p = save_preference(store, "", ["peanuts"])
    assert p.avoid == ["peanut"]
    assert p.text == "avoid peanut"


def test_empty_preference_rejected(store):
    with pytest.raises(ValueError):
        save_preference(store, "  ", [])


def test_summary_empty(store):
    assert preferences_summary(store) == "none"
    assert format_preferences([]) == "none"


def test_summary_lines(store):
    save_preference(store, "kids dislike eggplant", ["eggplant"])
    save_preference(store, "we like spicy food")
    save_preference(store, "allergic to nuts", ["peanuts", "walnuts"])
    assert preferences_summary(store) == (
        "- kids dislike eggplant (avoid: eggplant)\n"
        "- we like spicy food\n"
        "- allergic to nuts (avoid: peanut, walnut)"
    )


def test_saved_preference_fails_validation(store):
    from app.models import Ingredient, Recipe, ScanState
    from app.tools.checks import validate_suggestion
    from app.tools.inventory import get_inventory

    save_preference(store, "kids hated the eggplant", ["eggplants"])
    recipe = Recipe(name="baba ganoush", steps=["roast"], time_minutes=40, ingredients=[
        Ingredient(name="aubergine", amount="2", essential=True, category="vegetable")])
    res = validate_suggestion(recipe, get_inventory(store), get_preferences(store), ScanState(scanned={}))
    assert not res.ok
    assert res.violated_preferences == ["eggplant (kids hated the eggplant)"]
