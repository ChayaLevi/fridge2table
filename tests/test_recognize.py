import io
from pathlib import Path

import pytest
from PIL import Image
from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.store import Store
from app.tools.recognize import (
    PLACE_HINTS, RECOGNITION_PROMPT, TILE_HINT, RecognizedItem, load_image, merge_items, recognize_images,
    recognize_inventory, split_tiles,
)


def _item(name, conf=0.9, qty="some", category="dairy", note="", display=None):
    return {"name": name, "display_name": display or name, "category": category, "qty_level": qty,
            "confidence": conf, "note": note}


def fake_vision(answer):
    """FunctionModel whose reply is `answer(prompt_text, image)`; records (prompt, image size) per call."""
    calls = []

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        part = next(p for m in messages for p in m.parts if isinstance(p, UserPromptPart))
        text = next(c for c in part.content if isinstance(c, str))
        image = next(c for c in part.content if isinstance(c, BinaryContent))
        img = Image.open(io.BytesIO(image.data))
        calls.append((text, img.size))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"items": answer(text, img)})])

    return FunctionModel(fn), calls


def make_photo(tmp_path: Path, name: str, size=(800, 600)) -> Path:
    path = tmp_path / name
    Image.new("RGB", size, (200, 180, 160)).save(path, format="JPEG")
    return path


# --- pure helpers ---------------------------------------------------------------------------------

def test_split_tiles_one_is_identity():
    img = Image.new("RGB", (1000, 800))
    assert split_tiles(img, 1) == [img]


def test_split_tiles_two_is_top_and_bottom_with_overlap():
    top, bottom = split_tiles(Image.new("RGB", (1000, 800)), 2)
    assert top.size == (1000, 440) and bottom.size == (1000, 440)  # 400 + 5% of 800 each side
    # together they cover the image and share 80 px (10%)
    assert 440 + 440 - 800 == 80


def test_split_tiles_four_are_overlapping_quadrants():
    tiles = split_tiles(Image.new("RGB", (1000, 800)), 4)
    assert [t.size for t in tiles] == [(550, 440)] * 4


def test_split_tiles_keeps_pixels_in_place():
    img = Image.new("RGB", (100, 100), (0, 0, 0))
    img.putpixel((99, 99), (255, 0, 0))  # bottom-right corner
    tiles = split_tiles(img, 4)
    assert tiles[3].getpixel((tiles[3].size[0] - 1, tiles[3].size[1] - 1)) == (255, 0, 0)
    assert tiles[0].getpixel((0, 0)) == (0, 0, 0)


def test_split_tiles_rejects_other_counts():
    with pytest.raises(ValueError):
        split_tiles(Image.new("RGB", (10, 10)), 3)


def test_load_image_resizes_long_side(tmp_path):
    img = load_image(make_photo(tmp_path, "big.jpg", (3200, 2400)))
    assert img.size == (1600, 1200)
    assert load_image(make_photo(tmp_path, "small.jpg", (800, 600))).size == (800, 600)


def test_merge_items_normalizes_and_keeps_max_confidence_and_higher_qty():
    items = [RecognizedItem(**_item("Scallions", 0.5, "plenty", note="a")),
             RecognizedItem(**_item("green onion", 0.8, "low", note="b")),
             RecognizedItem(**_item("eggs", 0.9, category="Eggs!"))]
    merged = merge_items(items)
    assert [i.name for i in merged] == ["green onion", "egg"]
    onion = merged[0]
    assert onion.confidence == 0.8 and onion.qty_level == "plenty" and onion.note == "b"
    assert merged[1].category == "other"  # unknown category


def test_merge_items_clamps_confidence():
    assert merge_items([RecognizedItem(**_item("milk", 1.7))])[0].confidence == 1.0


def test_prompt_has_the_rules():
    for rule in ("generic English name", "Read labels", "opaque or closed containers", "0.4",
                 "non-food", '"plenty", "some" or "low"'):
        assert rule in RECOGNITION_PROMPT


# --- recognize_inventory with a mocked model ------------------------------------------------------

async def test_recognize_inventory_one_call_per_image_with_place_hint(tmp_path):
    def answer(text, img):
        if "pantry" in text:
            return [_item("Canned Tomatoes", 0.95, "plenty", "canned"), _item("pasta", 0.9, category="pasta")]
        return [_item("Whole Milk", 0.9), _item("eggs", 0.85, category="egg")]

    model, calls = fake_vision(answer)
    store = Store(":memory:")
    items = await recognize_inventory(
        [(make_photo(tmp_path, "f.jpg"), "fridge"), (make_photo(tmp_path, "p.jpg"), "pantry")],
        store=store, model=model, tiles=1,
    )
    assert len(calls) == 2
    assert sorted(PLACE_HINTS["fridge"] in t for t, _ in calls) == [False, True]
    assert all(TILE_HINT not in t for t, _ in calls)
    by_name = {i.name: i for i in items}
    assert set(by_name) == {"milk", "egg", "canned tomato", "pasta"}
    # the location comes from the tag, not the model
    assert by_name["milk"].location == "fridge" and by_name["pasta"].location == "pantry"
    assert all(i.source == "photo" and not i.uncertain for i in items)
    assert set(store.load_scan_state().scanned) == {"fridge", "pantry"}


async def test_uncertain_items_and_notes(tmp_path):
    model, _ = fake_vision(lambda t, s: [
        _item("white container", 0.3, category="other", note="possibly leftover rice"),
        _item("butter", 0.59), _item("cheddar", 0.6),
    ])
    items = {i.name: i for i in await recognize_inventory([(make_photo(tmp_path, "a.jpg"), "fridge")], model=model)}
    box = items["white container"]
    assert box.uncertain and box.display_name == "white container (possibly leftover rice)"
    assert items["butter"].uncertain  # below UNCERTAIN_THRESHOLD = 0.6
    assert not items["cheddar"].uncertain


async def test_duplicates_across_images_keep_higher_confidence(tmp_path):
    def answer(text, img):
        return [_item("milk", 0.5, "low")] if img.size[0] == 800 else [_item("milk", 0.9, "some", display="Milk 2%")]

    model, _ = fake_vision(answer)
    items = await recognize_inventory(
        [(make_photo(tmp_path, "a.jpg", (800, 600)), "fridge"), (make_photo(tmp_path, "b.jpg", (900, 600)), "fridge")],
        model=model,
    )
    assert len(items) == 1
    assert items[0].confidence == 0.9 and items[0].display_name == "Milk 2%" and not items[0].uncertain


async def test_tiles_send_crops_and_merge(tmp_path):
    def answer(text, img):
        # every crop sees the jam; only the top crop (white) sees the eggs
        top = img.getpixel((img.size[0] // 2, img.size[1] // 2))[0] > 128
        items = [_item("jam", 0.9 if top else 0.6, "low" if top else "plenty", "condiment")]
        return items + ([_item("eggs", 0.8, category="egg")] if top else [])

    model, calls = fake_vision(answer)
    photo = Image.new("RGB", (800, 600), (255, 255, 255))
    photo.paste((0, 0, 0), (0, 300, 800, 600))  # bottom half black
    photo.save(tmp_path / "a.jpg")
    results = await recognize_images([(tmp_path / "a.jpg", "fridge")], model=model, tiles=2)
    assert len(calls) == 2 and all(TILE_HINT in t for t, _ in calls)
    assert sorted(s for _, s in calls) == [(800, 330), (800, 330)]
    jam = next(i for i in results[0].items if i.name == "jam")
    assert jam.confidence == 0.9 and jam.qty_level == "plenty"
    assert {i.name for i in results[0].items} == {"jam", "egg"}


async def test_four_tiles_make_four_calls_per_image(tmp_path):
    model, calls = fake_vision(lambda t, s: [])
    photos = [(make_photo(tmp_path, f"{k}.jpg"), "pantry") for k in range(2)]
    items = await recognize_inventory(photos, model=model, tiles=4)
    assert len(calls) == 8 and items == []


async def test_big_photos_are_resized_before_sending(tmp_path):
    model, calls = fake_vision(lambda t, s: [])
    await recognize_images([(make_photo(tmp_path, "big.jpg", (4000, 3000)), "fridge")], model=model, tiles=1)
    assert calls[0][1] == (1600, 1200)
