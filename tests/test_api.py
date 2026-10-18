"""Endpoint tests with FastAPI's TestClient: the real agent loop on scripted models, no network."""

import json
from functools import partial

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app import api, config
from app.agent import WELCOME_MESSAGE, run_opening, run_turn
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

    async def __call__(self, store, session_id, message="hi", images=(), cook_mode="home"):
        self.calls.append((session_id, message, images))
        self.cook_mode = cook_mode
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


def test_chat_passes_the_cooking_mode_home_by_default(client):
    runner = FakeRunner()
    use_runner(runner)
    assert client.post("/chat", data={"session_id": "s1", "message": "hi"}).status_code == 200
    assert runner.cook_mode == "home"
    r = client.post("/chat", data={"session_id": "s1", "message": "hi", "cook_mode": "shop"})
    assert r.status_code == 200 and runner.cook_mode == "shop"
    assert r.json()["reply"]["offer_shop"] is False
    assert client.post("/chat", data={"session_id": "s1", "message": "hi", "cook_mode": "buy"}).status_code == 422


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


def test_inventory_reset_clears_items_and_scans_but_keeps_preferences_staples_and_chats(client, store):
    store.add_preference(Preference(id="p", text="no pork", avoid=["pork"], created_at="2026-10-14T00:00:00"))
    client.patch("/inventory", json=[{"op": "add_staple", "name": "rice"}, {"op": "remove", "name": "salt"}])
    store.save_session_messages("s1", [])
    body = client.post("/inventory/reset").json()
    names = {i["name"] for i in body["inventory"]}
    assert not any(i["source"] != "staple" for i in body["inventory"])  # spinach and egg are gone
    assert "rice" in names and "salt" not in names  # staple choices kept
    assert body["scan_state"]["scanned"] == {}
    assert [p.text for p in store.load_preferences()] == ["no pork"]
    assert store.load_session_messages("s1") == []  # the session row is still there (empty history)


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


def test_steps_with_substitutes_from_the_query(client, store):
    from app.models import Ingredient, Recipe

    prompts = []

    def fn(messages, info):
        prompts.append(next(p.content for m in messages for p in m.parts if p.part_kind == "user-prompt"))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"steps": ["Mix the cottage cheese."]})])

    api.app.dependency_overrides[api.get_recipe_model] = lambda: FunctionModel(fn)
    store.save_recipe(Recipe(id="las001", name="Lasagna", time_minutes=60, ingredients=[
        Ingredient(name="ricotta", amount="450 g", essential=True, category="dairy")]))
    r = client.get("/recipe/las001/steps", params={"sub": ["ricotta:cottage cheese", "bad-format"]})
    assert r.status_code == 200 and r.json()["steps"] == ["Mix the cottage cheese."]
    assert "- cottage cheese: 450 g" in prompts[0] and r.json()["ingredients"][0]["name"] == "ricotta"


def test_steps_for_an_unknown_recipe_is_404(client):
    api.app.dependency_overrides[api.get_recipe_model] = lambda: structured({"steps": ["x"]})
    r = client.get("/recipe/nope/steps")
    assert r.status_code == 404 and "nope" in r.json()["detail"]


# --- /opening, /, admin ---------------------------------------------------------------------------

def opening_model() -> FunctionModel:
    """Call suggest_meals, then offer the omelette."""

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart("suggest_meals", {"request": "use soon", "n": 3})])
        ids = ids_by_name(messages[-1].parts)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "message": "Hi! Your spinach needs using: how about an omelette?", "meal_ids": [ids["Spinach omelette"]]})])

    return FunctionModel(fn)


def use_opening(runner):
    api.app.dependency_overrides[api.get_opening_runner] = lambda: runner


def test_opening_runs_the_agent_and_offers_a_meal(client, store):
    use_opening(partial(run_opening, model=opening_model(), recipe_model=RECIPE_MODEL))
    body = client.get("/opening", params={"session_id": "s1"}).json()
    assert "spinach" in body["reply"]["message"]
    assert [m["name"] for m in body["reply"]["meals"]] == ["Spinach omelette"]
    assert [t["tool"] for t in body["trace"]] == ["suggest_meals", "output check"]
    assert body["usage"]["requests"] == 2 and any(i["name"] == "spinach" for i in body["inventory"])


def test_opening_with_an_empty_inventory_is_the_welcome_without_a_model(client, store):
    store.reset_all()
    use_opening(partial(run_opening, model=FunctionModel(lambda m, i: pytest.fail("model called"))))
    body = client.get("/opening", params={"session_id": "s1"}).json()
    assert body["reply"]["message"] == WELCOME_MESSAGE and body["trace"] == [] and body["usage"] is None


def test_opening_falls_back_to_a_static_greeting_when_the_model_fails(client):
    use_opening(FakeRunner(ModelAPIError("deepseek-v4-pro", "Connection error")))
    r = client.get("/opening", params={"session_id": "s1"})
    assert r.status_code == 200 and r.json()["reply"]["message"] == api.OPENING_MESSAGE


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


# --- /recipe/{id}/photo ---------------------------------------------------------------------------

def test_photo_is_served_or_404(client, store, tmp_path, monkeypatch):
    from app.models import Recipe
    from app.tools import photos

    found = tmp_path / "abc123.jpg"
    found.write_bytes(b"\xff\xd8jpeg")
    monkeypatch.setattr(photos, "recipe_photo", lambda r: _done(found if r.id == "abc123" else None))
    for rid in ("abc123", "def456"):
        store.save_recipe(Recipe(id=rid, name="Omelette", time_minutes=10, ingredients=[]))
    r = client.get("/recipe/abc123/photo")
    assert r.status_code == 200 and r.content == b"\xff\xd8jpeg" and r.headers["content-type"] == "image/jpeg"
    assert client.get("/recipe/def456/photo").status_code == 404
    assert client.get("/recipe/nope/photo").status_code == 404


def test_photo_service_down_is_503(client, store, monkeypatch):
    import httpx

    from app.models import Recipe
    from app.tools import photos

    async def down(_):
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(photos, "recipe_photo", down)
    store.save_recipe(Recipe(id="abc123", name="Omelette", time_minutes=10, ingredients=[]))
    r = client.get("/recipe/abc123/photo")
    assert r.status_code == 503 and r.json()["detail"] == "The photo service did not answer."


async def _done(value):
    return value


def test_patch_inventory_sets_and_clears_an_amount(client, store):
    r = client.patch("/inventory", json=[{"op": "add", "name": "chicken", "category": "meat"},
                                         {"op": "set_amount", "name": "chicken", "amount": 500, "unit": "g"}])
    assert r.status_code == 200, r.text
    chicken = {i["name"]: i for i in r.json()["inventory"]}["chicken"]
    assert (chicken["amount"], chicken["unit"], chicken["amount_text"], chicken["qty_level"]) == (500, "g", "500 g", "some")
    r = client.patch("/inventory", json=[{"op": "set_amount", "name": "chicken", "amount": None}])
    chicken = {i["name"]: i for i in r.json()["inventory"]}["chicken"]
    assert chicken["amount"] is None and chicken["amount_text"] == ""


def test_patch_inventory_add_field_with_an_amount(client):
    r = client.patch("/inventory", json=[{"op": "add", "name": "milk 2 l", "location": "fridge", "qty_level": "some"}])
    milk = {i["name"]: i for i in r.json()["inventory"]}["milk"]
    assert (milk["display_name"], milk["amount_text"]) == ("milk", "2 l")


def test_patch_inventory_rejects_a_bad_unit(client):
    assert client.patch("/inventory", json=[{"op": "set_amount", "name": "milk", "amount": 2, "unit": "cup"}]).status_code == 422
