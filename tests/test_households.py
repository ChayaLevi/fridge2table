"""One household per browser: the cookie picks the SQLite file, so two browsers never share an inventory."""

import pytest
from fastapi.testclient import TestClient

from app import api, config

ADD_MILK = [{"op": "add", "name": "milk", "category": "dairy"}]


@pytest.fixture
def browsers(tmp_path, monkeypatch):
    """A factory of fresh browsers (TestClients with their own cookie jar) on real per-household stores."""
    monkeypatch.setattr(config, "HOUSEHOLD_DIR", tmp_path / "households")
    monkeypatch.setattr(api, "_stores", {})
    clients = []

    def new() -> TestClient:
        clients.append(TestClient(api.app))
        return clients[-1]

    yield new
    for store in api._stores.values():
        store.close()


def names(r) -> set[str]:
    return {item["name"] for item in r.json()["inventory"]}


def test_page_sets_the_household_cookie(browsers):
    browser = browsers()
    r = browser.get("/")
    assert r.status_code == 200
    assert len(browser.cookies[api.HOUSEHOLD_COOKIE]) == 32


def test_two_browsers_have_separate_inventories(browsers):
    alice, bob = browsers(), browsers()
    alice.get("/"), bob.get("/")
    assert alice.cookies[api.HOUSEHOLD_COOKIE] != bob.cookies[api.HOUSEHOLD_COOKIE]
    assert "milk" in names(alice.patch("/inventory", json=ADD_MILK))
    assert "milk" not in names(bob.get("/inventory"))
    assert "milk" in names(alice.get("/inventory"))  # the same browser keeps its own
    assert len(list(config.HOUSEHOLD_DIR.glob("*.db"))) == 2


def test_api_call_without_the_page_still_gets_a_household(browsers):
    browser = browsers()  # e.g. /docs on a fresh browser
    browser.patch("/inventory", json=ADD_MILK)
    assert "milk" in names(browser.get("/inventory"))


def test_a_bad_cookie_gets_a_new_household(browsers):
    r = browsers().get("/inventory", headers={"Cookie": f"{api.HOUSEHOLD_COOKIE}=../../app"})
    assert r.status_code == 200
    assert r.cookies[api.HOUSEHOLD_COOKIE] != "../../app"
    assert all(p.parent == config.HOUSEHOLD_DIR for p in config.HOUSEHOLD_DIR.glob("**/*.db"))
