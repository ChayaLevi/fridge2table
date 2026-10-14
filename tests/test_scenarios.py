import importlib.util
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models import AgentReply, Ingredient, Recipe, Substitution, ToolTraceItem, TurnUsage
from app.store import Store
from app.tools.inventory import get_inventory

_spec = importlib.util.spec_from_file_location(
    "run_scenarios", Path(__file__).resolve().parent.parent / "eval" / "run_scenarios.py")
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)


def _trace(*tools: str, failed: str | None = None) -> list[ToolTraceItem]:
    return [ToolTraceItem(tool=t, args_summary="", result_summary="", failed=(t == failed)) for t in tools]


def _recipe(name: str, *ings: str, minutes: int = 20) -> Recipe:
    return Recipe(name=name, time_minutes=minutes,
                  ingredients=[Ingredient(name=i, amount="1", essential=True, category="vegetable") for i in ings])


def _store(*items: str, scanned=("fridge",)) -> Store:
    store = Store(":memory:")
    sc.seed_store(store, {"inventory": list(items), "scanned": list(scanned)}, {})
    return store


def test_suite_file_loads_with_eleven_scenarios():
    inventories, scenarios = sc.load_suite()
    assert [s["id"] for s in scenarios] == list(range(1, 12))
    for s in scenarios:  # every seed is valid
        sc.seed_store(Store(":memory:"), s.get("seed") or {}, inventories)
    for s in scenarios:
        for t in s["turns"]:
            for p, loc in t.get("photos") or []:
                assert (sc.ROOT / p).exists() and loc in sc.LOCATIONS


def test_load_suite_rejects_unknown_expect_key(tmp_path):
    f = tmp_path / "s.yaml"
    f.write_text("scenarios:\n  - {id: 1, name: x, turns: [{message: hi, expect: {max_meal: 3}}]}\n")
    with pytest.raises(ValueError, match="max_meal"):
        sc.load_suite(f)


def test_parse_item_and_seed():
    c = sc.parse_item("pasta, pasta, plenty, pantry, soon")
    assert (c.name, c.category, c.qty_level, c.location, c.use_soon) == ("pasta", "pasta", "plenty", "pantry", True)
    assert sc.parse_item("egg, egg, some").location == "fridge"
    with pytest.raises(ValueError):
        sc.parse_item("egg, egg, some, garage")
    store = Store(":memory:")
    sc.seed_store(store, {"inventory": "base", "add": ["milk, dairy, low"], "remove": ["egg"], "scanned": ["fridge"],
                          "preferences": [{"text": "no pork", "avoid": ["pork"]}]},
                  {"base": ["egg, egg, plenty", "tomatoes, vegetable, some"]})
    names = {i.name for i in get_inventory(store) if not i.is_staple}
    assert names == {"tomato", "milk"}
    assert "fridge" in store.load_scan_state().scanned
    assert store.load_preferences()[0].avoid == ["pork"]


def test_has_matches_synonyms_and_longer_names():
    assert sc._has(["Ricotta cheese"], "ricotta")
    assert sc._has(["spaghetti"], "pasta")
    assert sc._has(["lasagna pasta sheet"], "pasta")
    assert not sc._has(["eggplant"], "egg")


def test_check_turn_mode_a_pass():
    store = _store("spinach, vegetable, some", "egg, egg, plenty")
    reply = AgentReply(message="Here you go.", meals=[_recipe("Spinach omelette", "spinach", "egg")])
    expect = {"tools_called": ["suggest_meals", "output check"], "min_meals": 1, "max_meals": 3, "meals_valid": True,
              "max_minutes": 30, "meals_must_not_contain": ["eggplant"], "max_questions": 3}
    assert sc.check_turn(expect, reply, _trace("update_inventory", "suggest_meals", "output check"), store) == []


def test_check_turn_mode_a_failures():
    store = _store("spinach, vegetable, some")
    reply = AgentReply(message="x", meals=[_recipe("Spinach omelette", "spinach", "egg", minutes=40)])
    fails = sc.check_turn({"tools_called": ["update_inventory", "suggest_meals"], "meals_valid": True,
                           "max_minutes": 30, "meals_must_not_contain": ["egg"], "failed_check": True,
                           "first_tool": "update_inventory", "inventory_lacks": ["spinach"]},
                          reply, _trace("suggest_meals", "output check"), store)
    text = "\n".join(fails)
    for part in ("tools_called", "first tool", "40 min > 30", "contains egg", "invalid", "no failed check",
                 "spinach still in the inventory"):
        assert part in text


def test_check_turn_mode_b():
    store = _store("cottage cheese, dairy, some")
    reply = AgentReply(message="You need a few things.", meals=[_recipe("Lasagna", "ricotta", "pasta")],
                       substitutions=[Substitution(missing="ricotta", use_instead="cottage cheese")],
                       shopping_list=["ground beef"], check_first=["lasagna noodle"])
    expect = {"substitution_for": ["ricotta"], "shopping_list_must_not_contain": ["ricotta"],
              "shopping_list_contains": ["ground beef"], "check_first_contains": ["lasagna noodle"]}
    assert sc.check_turn(expect, reply, _trace("get_recipe", "compute_missing", "output check"), store) == []
    fails = sc.check_turn({"shopping_list_empty": True, "check_first_must_not_contain": ["pasta"],
                           "meals_valid": True, "substitution_for": ["mozzarella"]}, reply, [], store)
    # list not empty, Mode B where Mode A was expected, the lasagna is invalid, no mozzarella substitution;
    # "lasagna noodle" is not pasta, so check_first passes
    assert len(fails) == 4


def test_check_turn_preference_and_messages():
    store = _store()
    from app.tools.preferences import save_preference
    save_preference(store, "kids hated the eggplant", ["aubergine"])
    reply = AgentReply(message="Got it, no eggplant. A pantry photo would help.",
                       questions=["Is the white container rice?", "Can you snap the pantry?"])
    expect = {"preference_saved": ["eggplant"], "asks_for_photo": "pantry", "message_matches": "no eggplant"}
    assert sc.check_turn(expect, reply, _trace("save_preference"), store) == []
    reply.questions.append("Pantry again?")
    fails = sc.check_turn({"asks_for_photo": "pantry", "max_questions": 2, "preference_saved": ["pork"]},
                          reply, [], store)
    assert len(fails) == 3


def test_select_adds_dependencies():
    scenarios = [{"id": 1}, {"id": 6}, {"id": 7, "after": 6}]
    assert [s["id"] for s in sc.select(scenarios, [7])] == [6, 7]
    assert sc.select(scenarios, None) == scenarios


async def test_run_suite_with_a_fake_agent(monkeypatch):
    """The runner without a model: run_turn is replaced; the store of `after` is shared."""
    seen = []

    async def fake_run_turn(store, session_id, message="", images=None):
        seen.append((session_id, message, len(get_inventory(store))))
        meals = [_recipe("Omelette", "egg")] if "cook" in message else []
        return SimpleNamespace(
            reply=AgentReply(message="ok", meals=meals),
            trace=_trace("suggest_meals", "output check"),
            usage=TurnUsage(latency_s=1.5, requests=2, tool_calls=1, input_tokens=10, output_tokens=5),
        )

    monkeypatch.setattr(sc, "run_turn", fake_run_turn)
    scenarios = [
        {"id": 1, "name": "a", "seed": {"inventory": ["egg, egg, plenty"]},
         "turns": [{"message": "what can I cook", "expect": {"min_meals": 1}}]},
        {"id": 2, "name": "b", "after": 1, "seed": {"add": ["milk, dairy, some"]},
         "turns": [{"message": "hi", "expect": {"min_meals": 1}},
                   {"message": "hi again", "new_session": True, "scan": ["pantry"]}]},
    ]
    results = await sc.run_suite(scenarios, {}, jobs=2, run_tag="t", report_ids={1, 2})
    assert [r["passed"] for r in results] == [True, False]
    assert results[1]["turns"][0]["failures"] == ["0 meals < 1"]
    assert seen[1][2] == seen[0][2] + 1  # scenario 2 reused scenario 1's store and added milk
    assert seen[1][0] != seen[2][0]  # new_session
    table = sc.summary_table([results])
    assert "| 1 | a | 1/1 | 1.5 s |" in table and "**1/2**" in table
