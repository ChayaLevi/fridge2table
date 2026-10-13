"""T2.4: scripts/chat.py — the /photo parser and one REPL session with a scripted agent model (no network)."""

import importlib.util
from pathlib import Path

import pytest

from app import agent as agent_module
from tests.test_agent import FIXTURE_IMAGE, VISION_MODEL, reply, scripted, store  # noqa: F401 (fixture)

_spec = importlib.util.spec_from_file_location("chat", Path(__file__).parent.parent / "scripts" / "chat.py")
chat = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chat)


def test_parse_photo_command():
    assert chat.parse_photo_command(str(FIXTURE_IMAGE)) == [(FIXTURE_IMAGE, "fridge")]
    assert chat.parse_photo_command(f'"{FIXTURE_IMAGE}" {FIXTURE_IMAGE} Pantry') == [
        (FIXTURE_IMAGE, "pantry"), (FIXTURE_IMAGE, "pantry")]
    with pytest.raises(ValueError, match="no such file"):
        chat.parse_photo_command("nope.jpg freezer")
    with pytest.raises(ValueError, match="usage"):
        chat.parse_photo_command("pantry")


async def test_repl_sends_photos_with_the_next_message_and_keeps_history(store, monkeypatch, capsys):
    model, seen = scripted(("recognize_inventory", {}), reply(message="Found 2 items."), reply(message="Sure."))
    real_run_turn = agent_module.run_turn

    async def fake_run_turn(store, session, message, images):
        return await real_run_turn(store, session, message, images, model=model, vision_model=VISION_MODEL)

    monkeypatch.setattr(chat, "run_turn", fake_run_turn)
    lines = iter([f"/photo {FIXTURE_IMAGE} pantry", "here is my pantry", "/inventory", "thanks", "/quit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(lines))

    await chat.repl(store, "t1", debug=False)

    out = capsys.readouterr().out
    assert "attached 1 (pantry)" in out
    assert "agent: Found 2 items." in out and "recognize_inventory() -> Recognized 2 items" in out
    assert "pantry (scanned" in out  # /inventory after the scan
    assert "agent: Sure." in out
    # the photos went with the first message only; both turns are in the stored history
    assert "[user attached 1 photo (pantry)]" in str(seen[0][1])
    assert "attached" not in str(seen[2][1][-1])
    assert len(store.load_session_messages("t1")) > 4
