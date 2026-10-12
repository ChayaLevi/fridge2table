from datetime import datetime

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from app.models import InventoryItem, Preference
from app.store import Store


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "sub" / "test.db"


def item(name, **kw):
    base = dict(
        id=f"id-{name}", name=name, display_name=name.title(), category="vegetable",
        qty_level="some", location="fridge", confidence=0.9, uncertain=False,
        source="photo", updated_at=datetime(2026, 10, 12, 12, 0),
    )
    base.update(kw)
    return InventoryItem(**base)


def reopen(store, path):
    store.close()
    return Store(path)


def test_creates_parent_dir_and_starts_empty(db_path):
    s = Store(db_path)
    assert s.load_inventory() == []
    assert s.load_preferences() == []
    assert s.load_removed_staples() == set()
    assert s.load_scan_state().scanned == {}
    assert s.load_session_messages("nope") == []


def test_inventory_survives_reopen_and_keeps_order(db_path):
    s = Store(db_path)
    items = [item("milk"), item("spinach", use_soon=True), item("egg")]
    s.save_inventory(items)
    s = reopen(s, db_path)
    assert s.load_inventory() == items


def test_save_inventory_replaces(db_path):
    s = Store(db_path)
    s.save_inventory([item("milk"), item("egg")])
    s.save_inventory([item("egg", qty_level="low")])
    loaded = s.load_inventory()
    assert [i.name for i in loaded] == ["egg"]
    assert loaded[0].qty_level == "low"


def test_preferences_survive_reopen(db_path):
    s = Store(db_path)
    p = Preference(id="p1", text="kids dislike eggplant", avoid=["eggplant"], created_at=datetime(2026, 10, 12))
    s.add_preference(p)
    s.add_preference(p)  # same id: no duplicate row
    s = reopen(s, db_path)
    assert s.load_preferences() == [p]


def test_removed_staples(db_path):
    s = Store(db_path)
    s.set_staple_removed("sugar")
    s.set_staple_removed("sugar")
    s.set_staple_removed("salt")
    s = reopen(s, db_path)
    assert s.load_removed_staples() == {"sugar", "salt"}
    s.set_staple_removed("sugar", removed=False)
    assert s.load_removed_staples() == {"salt"}


def test_scan_state_survives_reopen(db_path):
    s = Store(db_path)
    t = datetime(2026, 10, 12, 18, 30)
    s.mark_scanned("fridge", t)
    s.set_freezer_declined()
    s = reopen(s, db_path)
    state = s.load_scan_state()
    assert state.scanned == {"fridge": t}
    assert state.freezer_declined is True
    s.mark_scanned("pantry")
    state = s.load_scan_state()
    assert set(state.scanned) == {"fridge", "pantry"}
    assert state.scanned["fridge"] == t
    assert state.freezer_declined is True


def test_session_messages_round_trip(db_path):
    s = Store(db_path)
    msgs = [
        ModelRequest(parts=[UserPromptPart(content="What can I cook?")]),
        ModelResponse(parts=[TextPart(content="Let me look.")]),
    ]
    s.save_session_messages("a", msgs)
    s.save_session_messages("b", msgs[:1])
    s = reopen(s, db_path)
    loaded = s.load_session_messages("a")
    assert len(loaded) == 2
    assert loaded[0].parts[0].content == "What can I cook?"
    assert loaded[1].parts[0].content == "Let me look."
    assert len(s.load_session_messages("b")) == 1
    s.save_session_messages("a", msgs[:1])
    assert len(s.load_session_messages("a")) == 1


def test_reset_all(db_path):
    s = Store(db_path)
    s.save_inventory([item("milk")])
    s.add_preference(Preference(id="p1", text="x", avoid=["x"], created_at=datetime(2026, 10, 12)))
    s.set_staple_removed("salt")
    s.mark_scanned("fridge")
    s.save_session_messages("a", [ModelRequest(parts=[UserPromptPart(content="hi")])])
    s.reset_all()
    s = reopen(s, db_path)
    assert s.load_inventory() == []
    assert s.load_preferences() == []
    assert s.load_removed_staples() == set()
    assert s.load_scan_state().scanned == {}
    assert s.load_session_messages("a") == []
