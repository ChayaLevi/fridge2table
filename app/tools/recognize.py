"""Recognition: photos of a fridge, freezer or pantry -> inventory items.

One vision call per image (or per tile, see `split_tiles`), all in parallel. The place comes from the
user's tag, never from the model. Names are normalized and duplicates across images/tiles merged.
"""

import asyncio
import io
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image
from pydantic import BaseModel
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.models import Model

from app import config
from app.models import CATEGORIES, InventoryItem, Location, QtyLevel
from app.store import Store
from app.tools.normalize import normalize

log = logging.getLogger(__name__)

MAX_SIDE = 1600
TILE_OVERLAP = 0.10  # fraction of the image size shared by neighbouring tiles

RECOGNITION_PROMPT = """\
You are looking at a photo of a home kitchen storage place and must list the food in it.
{place_hint}
{tile_hint}
Rules:
- List each distinct food or drink item that is visible, once. Use a generic English name \
("greek yogurt", "cheddar", "ketchup"), not a brand name. display_name may be a little more specific \
("Greek yogurt, plain").
- Read labels on packages, jars, cans and bottles when they are legible, and use them for the name.
- Do not guess the contents of opaque or closed containers. Add such a container as an item named by \
its appearance ("white container", "foil package") with confidence 0.4 or lower, and put your best \
guess in note ("possibly leftover rice").
- category: one of {categories}.
- qty_level from what is visible: "plenty", "some" or "low".
- confidence: 0 to 1, how sure you are of the name. Use below 0.6 when you are not sure.
- Do not list non-food items (dishes, cleaning products, medicine, containers you can see are empty).
- If no food is visible, return an empty list.
"""

PLACE_HINTS: dict[str, str] = {
    "fridge": "This is a fridge: expect fresh produce, dairy, eggs, meat, leftovers, drinks and condiments, "
    "including items in the door shelves.",
    "freezer": "This is a freezer: expect frozen vegetables, meat, fish, bread, ready meals and ice cream, "
    "often in bags or boxes; read their labels.",
    "pantry": "This is a pantry shelf or cabinet: expect dry goods, cans, jars and packages; read their labels.",
}
TILE_HINT = "This image is one crop of a larger photo: items may be cut off at the edges; list them anyway."

_QTY_RANK = {"low": 0, "some": 1, "plenty": 2}


class RecognizedItem(BaseModel):
    name: str
    display_name: str
    category: str
    qty_level: QtyLevel
    confidence: float
    note: str = ""


class Recognition(BaseModel):
    items: list[RecognizedItem]


@dataclass
class ImageResult:
    """Recognition of one photo (all its tiles), already normalized and merged."""

    path: Path
    location: Location
    items: list[RecognizedItem]
    latency_s: float


def load_image(path: Path, max_side: int = MAX_SIDE) -> Image.Image:
    """RGB image, resized so the long side is at most `max_side` pixels."""
    img = Image.open(path)
    img.load()
    img = img.convert("RGB")
    img.thumbnail((max_side, max_side))
    return img


def split_tiles(image: Image.Image, n: int) -> list[Image.Image]:
    """Split into 1, 2 (top/bottom) or 4 (quadrants) crops that overlap by about 10%."""
    if n == 1:
        return [image]
    if n not in (2, 4):
        raise ValueError(f"tiles must be 1, 2 or 4, got {n}")
    w, h = image.size

    def spans(size: int) -> list[tuple[int, int]]:
        half, pad = size / 2, size * TILE_OVERLAP / 2
        return [(0, round(half + pad)), (round(half - pad), size)]

    rows = spans(h)
    cols = spans(w) if n == 4 else [(0, w)]
    return [image.crop((x0, y0, x1, y1)) for (y0, y1) in rows for (x0, x1) in cols]


def to_jpeg(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


# Common off-list categories models return, mapped onto CATEGORIES (the pantry rule depends on them).
CATEGORY_ALIASES = {
    "produce": "vegetable", "veg": "vegetable", "veggie": "vegetable", "herb": "vegetable",
    "fresh herb": "vegetable", "poultry": "meat", "seafood": "fish", "shellfish": "fish",
    "cheese": "dairy", "milk": "dairy", "rice": "grain", "bread": "grain", "cereal": "grain",
    "noodle": "pasta", "canned good": "canned", "legume": "canned", "bean": "canned", "oil": "condiment", "fat": "condiment", "vinegar": "condiment",
    "dried herb": "spice", "seasoning": "spice", "nut": "snack", "seed": "snack", "beverage": "drink",
}


def coerce_category(category: str) -> str:
    """A category from CATEGORIES: exact, singular, or via CATEGORY_ALIASES; anything else is "other"."""
    c = " ".join(category.strip().lower().split())
    for key in (c, c[:-1] if c.endswith("s") else c):
        if key in CATEGORIES:
            return key
        if key in CATEGORY_ALIASES:
            return CATEGORY_ALIASES[key]
    return "other"


def merge_items(items: list[RecognizedItem]) -> list[RecognizedItem]:
    """Normalize names and merge by canonical name: max confidence, the higher qty_level.

    The note and display name come from the most confident reading. Order of first appearance is kept.
    """
    merged: dict[str, RecognizedItem] = {}
    for it in items:
        name = normalize(it.name)
        if not name:
            continue
        it = it.model_copy(update={
            "name": name,
            "category": coerce_category(it.category),
            "confidence": min(1.0, max(0.0, it.confidence)),
        })
        prev = merged.get(name)
        if prev is None:
            merged[name] = it
            continue
        best = it if it.confidence > prev.confidence else prev
        qty = it.qty_level if _QTY_RANK[it.qty_level] > _QTY_RANK[prev.qty_level] else prev.qty_level
        merged[name] = best.model_copy(update={"qty_level": qty})
    return list(merged.values())


def _prompt(location: Location, tiled: bool) -> str:
    return RECOGNITION_PROMPT.format(
        place_hint=PLACE_HINTS[location], tile_hint=TILE_HINT if tiled else "", categories=", ".join(CATEGORIES)
    )


async def _recognize_crop(agent: Agent, jpeg: bytes, location: Location, tiled: bool) -> list[RecognizedItem]:
    start = time.perf_counter()
    result = await agent.run([_prompt(location, tiled), BinaryContent(data=jpeg, media_type="image/jpeg")])
    usage = result.usage
    log.debug("vision call: %s, %d bytes, %.1fs, %s in / %s out tokens, %d items",
              location, len(jpeg), time.perf_counter() - start, usage.input_tokens, usage.output_tokens,
              len(result.output.items))
    return result.output.items


async def recognize_images(
    images: list[tuple[Path, Location]], *, model: Model | None = None, tiles: int | None = None
) -> list[ImageResult]:
    """Recognize each photo separately (tiles and photos all run in parallel)."""
    tiles = tiles or config.VISION_TILES
    if model is None:
        from app.llm import vision_model  # needs the API key, so only when no model is given

        model = vision_model()
    agent = Agent(model, output_type=Recognition)

    async def one(path: Path, location: Location) -> ImageResult:
        start = time.perf_counter()
        crops = split_tiles(load_image(path), tiles)
        found = await asyncio.gather(*(_recognize_crop(agent, to_jpeg(c), location, tiles > 1) for c in crops))
        items = merge_items([it for part in found for it in part])
        return ImageResult(path, location, items, time.perf_counter() - start)

    return list(await asyncio.gather(*(one(Path(p), loc) for p, loc in images)))


def to_inventory_items(results: list[ImageResult]) -> list[InventoryItem]:
    """Merge across photos by canonical name (higher confidence wins) and build InventoryItems.

    For an uncertain item with a note, the note goes into display_name ("white container (possibly
    leftover rice)") so the agent can ask about it.
    """
    best: dict[str, tuple[RecognizedItem, Location]] = {}
    for r in results:
        for it in r.items:
            prev = best.get(it.name)
            if prev is None or it.confidence > prev[0].confidence:
                best[it.name] = (it, r.location)
    now = datetime.now()
    out = []
    for name, (it, location) in best.items():
        uncertain = it.confidence < config.UNCERTAIN_THRESHOLD
        display = it.display_name.strip() or name
        if uncertain and it.note.strip():
            display = f"{display} ({it.note.strip()})"
        out.append(InventoryItem(
            id=uuid.uuid4().hex[:12], name=name, display_name=display, category=it.category,
            qty_level=it.qty_level, location=location, confidence=it.confidence, uncertain=uncertain,
            source="photo", updated_at=now,
        ))
    return out


async def recognize_inventory(
    images: list[tuple[Path, Location]],
    *,
    store: Store | None = None,
    model: Model | None = None,
    tiles: int | None = None,
) -> list[InventoryItem]:
    """Photos tagged with their place -> inventory items. Marks each tagged place scanned in `store`.

    Does not merge into the stored inventory; the caller does that with `merge_recognized`.
    """
    results = await recognize_images(images, model=model, tiles=tiles)
    if store is not None:
        for location in dict.fromkeys(loc for _, loc in images):
            store.mark_scanned(location)
    return to_inventory_items(results)
