"""Endpoint tests with FastAPI's TestClient: the real agent loop on scripted models, no network."""

import json
from functools import partial

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app import api, config
from app.agent import run_turn
from app.models import InventoryChange, Preference
from app.store import Store
from app.tools.inventory import staple_names, update_inventory
from tests.test_agent import FIXTURE_IMAGE, RECIPE_MODEL, ids_by_name, structured


@pytest.fixture
def store():
    s = Store(":memory:")
    s.mark_scanned("fridge")
    update_inventory(s, [
        InventoryChange(op="add", name="spinach", category="vegetable", use_soon=True),
        InventoryChange(op="add", name="eggs", category="egg", qty_level="plenty"),
    ])
    yield s
    s.close()


@pytest.fixture
def client(store, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path / "uploads")
    api.app.dependency_overrides[api.get_store] = lambda: store
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()


def use_runner(runner):
    api.app.dependency_overrides[api.get_turn_runner] = lambda: runner


def mode_a_model() -> FunctionModel:
    """Call suggest_meals, then reply with the id of the omelette it returned."""

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart("suggest_meals", {"request": "dinner"})])
        ids = ids_by_name(messages[-1].parts)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "message": "An omelette uses your spinach.", "meal_ids": [ids["Spinach omelette"]]})])

    return FunctionModel(fn)


class FakeRunner:
    """Records the arguments of each turn; raises `error` if given."""

    def __init__(self, error: Exception | None = None):
        self.calls: list[tuple] = []
        self.error = error

    async def __call__(self, store, session_id, message, images):
        self.calls.append((session_id, message, images))
        if self.error:
            raise self.error
        return await run_turn(store, session_id, message, images, model=FunctionModel(
            lambda m, info: ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"message": "ok"})])))


def photo(name="fridge.jpg"):
    return ("images", (name, FIXTURE_IMAGE.read_bytes(), "image/jpeg"))


# --- /chat ----------------------------------------------------------------------------------------

def test_chat_mode_a_returns_reply_with_meals_trace_inventory_and_scan_state(client, store):
    use_runner(partial(run_turn, model=mode_a_model(), recipe_model=RECIPE_MODEL))
    r = client.post("/chat", data={"session_id": "s1", "message": "What can I cook tonight?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reply"]["message"] == "An omelette uses your spinach."
    [meal] = body["reply"]["meals"]
    assert meal["name"] == "Spinach omelette" and body["reply"]["meal_ids"] == [meal["id"]]
    assert {i["name"] for i in meal["ingredients"]} >= {"egg", "spinach"}
    assert [t["tool"] for t in body["trace"]] == ["suggest_meals", "output check"]
    assert "1 failed" in body["trace"][0]["result_summary"]  # carbonara: no cream
    assert {"spinach", "egg", "salt"} <= {i["name"] for i in body["inventory"]}
    assert "fridge" in body["scan_state"]["scanned"]
    assert body["usage"]["tool_calls"] >= 1
    assert store.load_session_messages("s1")  # history persisted


def test_chat_saves_photos_and_passes_them_with_their_tags(client):
    runner = FakeRunner()
    use_runner(runner)
    r = client.post("/chat", data={"session_id": "s1", "locations": ["fridge", "pantry"]},
                    files=[photo("a.jpg"), photo("b.jpg")])
    assert r.status_code == 200, r.text
    [(session_id, message, images)] = runner.calls
    assert session_id == "s1" and message == ""
    assert [loc for _, loc in images] == ["fridge", "pantry"]
    for path, _ in images:
        assert path.parent == config.UPLOAD_DIR and path.read_bytes() == FIXTURE_IMAGE.read_bytes()


def test_chat_accepts_comma_separated_locations(client):
    runner = FakeRunner()
    use_runner(runner)
    r = client.post("/chat", data={"session_id": "s1", "message": "hi", "locations": "Fridge, freezer"},
                    files=[photo(), photo()])
    assert r.status_code == 200, r.text
    assert [loc for _, loc in runner.calls[0][2]] == ["fridge", "freezer"]


@pytest.mark.parametrize("data, n_files, error", [
    ({"message": "hi", "locations": ["fridge"]}, 2, "one location per image"),
    ({"message": "hi"}, 1, "one location per image"),
    ({"message": "hi", "locations": ["garage"]}, 1, "Unknown location"),
    ({"message": "hi", "locations": ["fridge"] * 5}, 5, "At most 4 photos"),
    ({"message": "   "}, 0, "message or at least one photo"),
])
def test_chat_rejects_bad_input_before_running_the_agent(client, data, n_files, error):
    runner = FakeRunner()
    use_runner(runner)
    r = client.post("/chat", data={"session_id": "s1", **data}, files=[photo() for _ in range(n_files)] or None)
    assert r.status_code == 400 and error in r.json()["detail"]
    assert runner.calls == []


@pytest.mark.parametrize("error, status, detail", [
    (ModelAPIError("deepseek-v4-pro", "Connection error"), 503, api.MODEL_DOWN),
    (UnexpectedModelBehavior("Exceeded maximum retries (2) for output validation"), 502, api.AGENT_FAILED),
])
def test_chat_model_failures_are_clear_json_errors(client, error, status, detail):
    use_runner(FakeRunner(error))
    r = client.post("/chat", data={"session_id": "s1", "message": "dinner?"})
    assert r.status_code == status and r.json() == {"detail": detail}


# --- /inventory -----------------------------------------------------------------------------------

def test_get_inventory_lists_items_staples_and_scan_state(client):
    body = client.get("/inventory").json()
    names = [i["name"] for i in body["inventory"]]
    assert names[:2] == ["spinach", "egg"] and set(staple_names()) <= set(names)
    assert list(body["scan_state"]["scanned"]) == ["fridge"]


def test_patch_inventory_applies_panel_edits_as_manual(client, store):
    r = client.patch("/inventory", json=[
        {"op": "add", "name": "Tomatoes", "category": "vegetable", "qty_level": "low"},
        {"op": "set_use_soon", "name": "spinach", "use_soon": False},
        {"op": "remove", "name": "salt"},
    ])
    assert r.status_code == 200, r.text
    items = {i["name"]: i for i in r.json()["inventory"]}
    assert items["tomato"]["source"] == "manual" and items["tomato"]["qty_level"] == "low"
    assert items["spinach"]["use_soon"] is False
    assert "salt" not in items and "salt" in store.load_removed_staples()


def test_patch_inventory_adds_a_staple_and_renames_an_uncertain_item(client, store):
    from app.tools.inventory import merge_recognized
    from tests.test_inventory import item

    merge_recognized(store, [item("white container", confidence=0.3, uncertain=True)])
    r = client.patch("/inventory", json=[
        {"op": "add_staple", "name": "Rice"},
        {"op": "rename", "name": "white container", "new_name": "leftover rice"},
    ])
    assert r.status_code == 200, r.text
    items = {i["name"]: i for i in r.json()["inventory"]}
    assert items["rice"]["source"] == "staple"
    assert items["leftover rice"]["uncertain"] is False and "white container" not in items


def test_patch_inventory_rejects_an_unknown_op(client):
    assert client.patch("/inventory", json=[{"op": "buy", "name": "milk"}]).status_code == 422


# --- /recipe/{id}/steps ---------------------------------------------------------------------------

def test_steps_are_generated_once_then_read_from_the_store(client, store):
    from app.models import Ingredient, Recipe

    calls = []

    def fn(messages, info):
        calls.append(1)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"steps": ["Beat the eggs.", "Cook."]})])

    api.app.dependency_overrides[api.get_recipe_model] = lambda: FunctionModel(fn)
    store.save_recipe(Recipe(id="abc123", name="Omelette", time_minutes=10,
                             ingredients=[Ingredient(name="egg", amount="2", essential=True, category="egg")]))
    for _ in range(2):
        r = client.get("/recipe/abc123/steps")
        assert r.status_code == 200 and r.json()["steps"] == ["Beat the eggs.", "Cook."]
    assert len(calls) == 1


def test_steps_for_an_unknown_recipe_is_404(client):
    api.app.dependency_overrides[api.get_recipe_model] = lambda: structured({"steps": ["x"]})
    r = client.get("/recipe/nope/steps")
    assert r.status_code == 404 and "nope" in r.json()["detail"]


# --- /opening, /, admin ---------------------------------------------------------------------------

def test_opening_is_a_static_greeting_with_the_panel_state(client):
    body = client.get("/opening", params={"session_id": "s1"}).json()
    assert body["reply"]["message"] == api.OPENING_MESSAGE and body["trace"] == [] and body["usage"] is None
    assert any(i["name"] == "spinach" for i in body["inventory"])


def test_index_page_is_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]


def test_admin_reset_then_seed(client, store):
    store.add_preference(Preference(id="p", text="no pork", avoid=["pork"], created_at="2026-10-13T00:00:00"))
    store.save_session_messages("s1", [])
    body = client.post("/admin/reset").json()
    assert {i["name"] for i in body["inventory"]} == set(staple_names())
    assert body["scan_state"]["scanned"] == {} and store.load_preferences() == []

    body = client.post("/admin/seed").json()
    items = {i["name"]: i for i in body["inventory"] if not i["is_staple"]}
    assert len(items) >= 20 and items["spinach"]["use_soon"] is True
    assert {"eggplant", "cottage cheese", "pasta"} <= set(items) and not {"ricotta", "cream"} & set(items)
    assert list(body["scan_state"]["scanned"]) == ["fridge"]  # pantry left unscanned for the demo


def test_demo_seed_file_is_valid():
    seed = json.loads(config.DEMO_SEED_PATH.read_text(encoding="utf-8"))
    for item in seed["inventory"]:
        InventoryChange(op="add", **item)
    for pref in seed.get("preferences", []):
        Preference.model_validate(pref)
