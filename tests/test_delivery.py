"""Grocery deliveries (docs/MAIL_DEMO_PLAN.md): the final list, the cooking filter, apply + undo, notices,
and the endpoints. No network: the agent runs on scripted models."""

import json
from functools import partial

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.exceptions import ModelAPIError
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app import api, config
from app.agent import delivery_details, run_delivery
from app.models import GroceryOrder, InventoryChange, OrderLine
from app.store import Store
from app.tools import inventory
from app.tools.delivery import apply_delivery, classify_line, final_lines, line_amount
from tests.test_agent import RECIPE_MODEL, ids_by_name

HID = "0123456789abcdef0123456789abcdef"


def line(name, status="delivered", section="Dairy & Eggs", **kw):
    return OrderLine(raw_name=name, line_status=status, retailer_category=section, **kw)


def order(*lines):
    return GroceryOrder(retailer="Leafline Market", order_id="LL-1", lines=list(lines))


@pytest.fixture
def store():
    s = Store(":memory:")
    s.mark_scanned("fridge")
    inventory.update_inventory(s, [
        InventoryChange(op="add", name="spinach", category="vegetable", use_soon=True),
        InventoryChange(op="add", name="eggs", category="egg", qty_level="plenty"),
        InventoryChange(op="add", name="chicken", category="meat", qty_level="low"),
    ])
    yield s
    s.close()


def names(store):
    return {i.name: i for i in store.load_inventory()}


# --- final list -----------------------------------------------------------------------------------

def test_final_lines_drop_missing_and_refunded_and_replace_substituted():
    lines = [line("Ricotta"), line("Heavy Cream", "missing"), line("Butter", "refunded"),
             line("Parmesan", "ordered"), line("Grana Padano", "substituted", substitute_for="Parmesan"),
             line("Chicken Breast", "weight_adjusted", pack_size=0.86, pack_unit="kg")]
    assert [ln.raw_name for ln in final_lines(lines)] == ["Ricotta", "Grana Padano", "Chicken Breast"]


# --- cooking filter -------------------------------------------------------------------------------

@pytest.mark.parametrize("ln, expected", [
    (line("Ricotta"), ("cooking_ingredient", "dairy")),
    (line("Tomatoes", section="Fruit & Veg"), ("cooking_ingredient", "vegetable")),
    (line("Lasagna Sheets", section="Pantry"), ("cooking_ingredient", "grain")),
    (line("Toilet Paper", section="Household"), ("non_food", None)),
    (line("Cat Food", section="Pet"), ("non_food", None)),
    (line("Dish Soap", section=None), ("non_food", None)),  # by its words, without a section
    (line("Nonna's Secret Sauce", section="Local Makers"), ("uncertain", None)),
    (line("Rice Paper", section="Pantry"), ("cooking_ingredient", "grain")),  # "paper" alone is not non-food
])
def test_classify_line(ln, expected):
    assert classify_line(ln) == expected


def test_line_amount_only_for_supported_units():
    assert line_amount(line("Ricotta", qty=2, pack_size=250, pack_unit="g")) == (500, "g")
    assert line_amount(line("Basil", pack_size=1, pack_unit="bunch")) is None
    assert line_amount(line("Basil")) is None


# --- apply ----------------------------------------------------------------------------------------

def test_apply_delivery_adds_ingredients_and_skips_the_rest(store):
    notice = apply_delivery(store, order(
        line("Ricotta", pack_size=500, pack_unit="g"),
        line("Heavy Cream", "missing", pack_size=500, pack_unit="ml"),
        line("Parmesan", "ordered", pack_size=200, pack_unit="g"),
        line("Grana Padano", "substituted", substitute_for="Parmesan", pack_size=200, pack_unit="g"),
        line("Chicken Breast", "weight_adjusted", section="Meat & Fish", pack_size=0.86, pack_unit="kg"),
        line("Lasagna Sheets", section="Pantry", pack_size=500, pack_unit="g"),
        line("Toilet Paper", section="Household", pack_size=12, pack_unit="pcs"),
        line("Nonna's Secret Sauce", section="Local Makers", pack_size=680, pack_unit="g"),
    ))
    inv = names(store)
    assert inv["ricotta"].amount == 500 and inv["ricotta"].qty_level == "plenty" and inv["ricotta"].location == "fridge"
    assert inv["parmesan"].display_name == "Grana Padano"  # the substitute, under its own name
    assert "cream" not in inv and "toilet paper" not in inv
    assert (inv["chicken"].amount, inv["chicken"].unit, inv["chicken"].qty_level) == (0.86, "kg", "plenty")
    assert inv["lasagna noodle"].location == "pantry"
    assert inv["nonnas secret sauce"].uncertain and not inv["ricotta"].uncertain
    assert notice.skipped == ["Toilet Paper"] and notice.unavailable == ["Heavy Cream"]
    assert notice.substituted == [("Parmesan", "Grana Padano")] and notice.uncertain == ["Nonna's Secret Sauce"]
    assert [i.display_name for i in notice.added] == ["Ricotta", "Grana Padano", "Chicken Breast", "Lasagna Sheets",
                                                     "Nonna's Secret Sauce"]
    assert store.load_notices() == [notice]


def test_apply_delivery_leaves_staples_alone(store):
    notice = apply_delivery(store, order(line("Olive Oil", section="Pantry", pack_size=1, pack_unit="l")))
    assert notice.added == [] and notice.undo is None
    assert names(store).get("olive oil") is None  # still the virtual staple


def test_undo_takes_the_whole_delivery_back_out(store):
    before = {n: i.model_dump() for n, i in names(store).items()}
    notice = apply_delivery(store, order(line("Ricotta", pack_size=500, pack_unit="g"),
                                         line("Chicken", section="Meat", pack_size=1, pack_unit="kg")))
    assert inventory.undo_made(store, notice.undo)
    assert {n: i.model_dump() for n, i in names(store).items()} == before


def test_notice_is_shown_once(store):
    notice = apply_delivery(store, order(line("Ricotta")))
    assert store.mark_notice_seen(notice.id) and not store.mark_notice_seen(notice.id)
    assert store.load_notices() == [] and store.load_notice(notice.id) == notice


def test_demo_delivery_file_matches_the_story():
    o = GroceryOrder.model_validate_json(config.DEMO_DELIVERY_PATH.read_text(encoding="utf-8"))
    targets = {ln.raw_name for ln in o.lines}
    assert all(ln.substitute_for in targets for ln in o.lines if ln.substitute_for)
    kinds = {ln.raw_name: classify_line(ln)[0] for ln in final_lines(o.lines)}
    assert kinds["Ricotta"] == kinds["Lasagna Sheets"] == "cooking_ingredient"
    assert kinds["Nonna's Secret Sauce"] == "uncertain"
    assert {n for n, k in kinds.items() if k == "non_food"} == {"Toilet Paper", "Dish Soap", "Cat Food"}
    assert "Heavy Cream" not in kinds and "Parmesan" not in kinds


def test_delivery_details_lists_what_happened(store):
    notice = apply_delivery(store, order(line("Ricotta", pack_size=500, pack_unit="g"), line("Cream", "missing"),
                                         line("Cat Food", section="Pet")))
    text = delivery_details(notice)
    assert "Added: Ricotta (500 g)." in text and "out of stock): Cream" in text and "Not food" in text


# --- endpoints ------------------------------------------------------------------------------------

@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.setattr(api, "_stores", {HID: store})
    monkeypatch.setattr(api, "_last_seen", {HID: 1.0})
    api.app.dependency_overrides[api.get_store] = lambda: store
    c = TestClient(api.app)
    c.cookies.set(api.HOUSEHOLD_COOKIE, HID)
    yield c
    api.app.dependency_overrides.clear()


def delivery_model() -> FunctionModel:
    """Call suggest_meals, then offer the omelette it returned."""

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart("suggest_meals", {"request": "uses the delivery"})])
        ids = ids_by_name(messages[-1].parts)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "message": "Your Leafline order is in. How about a spinach omelette?",
            "meal_ids": [ids["Spinach omelette"]]})])

    return FunctionModel(fn)


def test_admin_delivery_applies_the_demo_order_and_the_page_finds_the_notice(client, store):
    body = client.post("/admin/delivery").json()
    inv = {i["name"]: i for i in body["inventory"]}
    assert inv["ricotta"]["amount"] == 500 and inv["chicken"]["amount"] == 0.86
    assert not {"cream", "toilet paper", "cat food"} & set(inv)
    notices = client.get("/notices").json()
    assert [n["id"] for n in notices["notices"]] == [body["notice"]["id"]]
    assert notices["poll_seconds"] == config.NOTICE_POLL_SECONDS


def test_admin_delivery_to_the_latest_household_without_a_cookie(client, store):
    client.cookies.clear()
    assert client.post("/admin/delivery").status_code == 400
    r = client.post("/admin/delivery", params={"household": "latest"},
                    json={"retailer": "X", "lines": [{"raw_name": "Ricotta", "retailer_category": "Dairy"}]})
    assert r.status_code == 200 and "ricotta" in names(store)


def test_open_notice_returns_the_agents_meal_with_the_delivery_trace(client, store):
    api.app.dependency_overrides[api.get_delivery_runner] = lambda: partial(
        run_delivery, model=delivery_model(), recipe_model=RECIPE_MODEL)
    notice_id = client.post("/admin/delivery").json()["notice"]["id"]
    body = client.post(f"/notices/{notice_id}/open", params={"session_id": "s1"}).json()
    assert body["reply"]["message"].startswith("Your Leafline order is in")
    assert [m["name"] for m in body["reply"]["meals"]] == ["Spinach omelette"]
    assert body["trace"][0]["label"] == "source: Leafline Market order #LL-4821 (email)"
    assert [t["tool"] for t in body["trace"][1:]] == ["suggest_meals", "output check"]
    assert client.get("/notices").json()["notices"] == []
    assert client.post(f"/notices/{notice_id}/open", params={"session_id": "s1"}).status_code == 404
    history = json.dumps(str(store.load_session_messages("s1")))
    assert "Leafline Market order LL-4821" in history  # the agent can recall the delivery later


def test_open_notice_falls_back_to_static_text_when_the_model_fails(client):
    async def failing(*a, **kw):
        raise ModelAPIError("deepseek-v4-pro", "Connection error")

    api.app.dependency_overrides[api.get_delivery_runner] = lambda: failing
    notice_id = client.post("/admin/delivery").json()["notice"]["id"]
    body = client.post(f"/notices/{notice_id}/open", params={"session_id": "s1"}).json()
    assert body["reply"]["message"].startswith("Your Leafline Market order arrived")
    assert body["trace"][0]["tool"] == "delivery"
