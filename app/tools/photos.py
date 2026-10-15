"""A photo of the finished dish for a meal card: searched by the recipe's `photo_query`, checked, downloaded
once and kept as `<PHOTO_DIR>/<recipe id>.jpg`.

Source: Pixabay when PIXABAY_API_KEY is set (Pixabay asks for images to be downloaded, not hotlinked),
else Wikimedia Commons (no key). Two filters, because a wrong photo is worse than none:
1. Code: a hit counts only if the kind of dish (the query's last word, "frittata") is in its tags (Pixabay)
   or file name (Wikimedia). Search ranks loosely ("spinach frittata" ranks salmon cakes first).
2. VISION_MODEL looks at the best candidates (CHECKS_PER_SEARCH per search) and names the dish it sees:
   tags lie (a potato tortilla tagged "pizza, lasagna, pasta").
No candidate passes: no photo, and the card shows none. A photo is decoration, not a fact the user acts
on, so a model check is enough here (rule 1 of CLAUDE.md is about ingredients and preferences).
"""

import asyncio
import logging
import re
import time
from pathlib import Path

import httpx
from pydantic import BaseModel, Field
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.models import Model

from app import config
from app.llm import thinking_settings
from app.models import Recipe

log = logging.getLogger(__name__)

PIXABAY_URL = "https://pixabay.com/api/"
WIKIMEDIA_URL = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "fridge-to-table-demo/0.1 (dish photos for a cooking demo)"  # Wikimedia requires one
SEARCH_LIMIT = 20
TIMEOUT_S = 8.0
MAX_BYTES = 3_000_000
CHECKS_PER_SEARCH = 2  # vision calls per search; two searches per dish at most
LEAD_TAGS = 3  # the first tags name the photo's subject; later ones are often stuffed in

PHOTO_CHECK_PROMPT = """\
This photo will illustrate the recipe "{name}" in a cooking app.
First name the dish the photo mainly shows, as a cook would. Then decide: is it a fair stand-in picture \
for "{name}", so a cook would think "yes, roughly that"? It must be the same kind of dish (a pasta for a \
pasta, a skillet or pan dish for a skillet) with a similar look; other details may differ (a missing or \
extra vegetable or protein, another pasta shape, a cream sauce for a tomato sauce does NOT count as \
similar). A second dish beside it is fine. Answer false for another kind of dish, even with the same \
ingredients (spinach dumplings are not a chicken skillet), raw or dried ingredients, people or hands as \
the subject, drawings, text or collages.
"""


class PhotoCheck(BaseModel):
    dish_in_photo: str = Field(description="the dish the photo mainly shows, in a few words")
    shows_dish: bool = Field(description="true only if a cook would accept the photo as the recipe's dish")


class PhotoHit(BaseModel):
    url: str  # the image itself (about 640 px wide)
    words: str  # what describes it: Pixabay tags or the Wikimedia file name


def _stem(word: str) -> str:
    """Rough singular, the same on both sides of a comparison: "noodles" -> "noodle", "tomatoes" -> "tomato",
    "berries" -> "berry", "pasta" stays."""
    if len(word) <= 3 or not word.endswith("s") or word.endswith("ss"):
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    return word[:-2] if word.endswith("oes") else word[:-1]


def _words(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[a-z]+", text.lower())}


def photo_query_for(recipe: Recipe) -> str:
    """The recipe's photo_query, or for recipes without one its name up to "with" ("Garlic pasta with basil"
    -> "garlic pasta"), at most 3 words."""
    query = recipe.photo_query or re.split(r"\bwith\b|,|\(", recipe.name, flags=re.I)[0]
    return " ".join(re.findall(r"[a-z]+", query.lower())[-3:])


def rank_photos(hits: list[PhotoHit], query: str) -> list[str]:
    """URLs of the hits whose words contain the kind of dish (the query's last word). First those that
    have it in their first LEAD_TAGS tags (the photo's subject), then those with more of the other query
    words, else in search order."""
    want = [_stem(w) for w in re.findall(r"[a-z]+", query.lower())]
    if not want:
        return []
    scored = []
    for i, hit in enumerate(hits):
        words = _words(hit.words)
        if want[-1] in words:
            lead = _words(",".join(hit.words.split(",")[:LEAD_TAGS]))
            scored.append((want[-1] not in lead, -sum(w in words for w in want[:-1]), i, hit.url))
    return [url for *_, url in sorted(scored)]


async def search_pixabay(client: httpx.AsyncClient, query: str, key: str) -> list[PhotoHit]:
    r = await client.get(PIXABAY_URL, params={
        "key": key, "q": query, "image_type": "photo", "category": "food", "safesearch": "true",
        "per_page": SEARCH_LIMIT,
    })
    r.raise_for_status()
    return [PhotoHit(url=h["webformatURL"], words=h.get("tags", "")) for h in r.json().get("hits", [])]


async def search_wikimedia(client: httpx.AsyncClient, query: str) -> list[PhotoHit]:
    r = await client.get(WIKIMEDIA_URL, params={
        "action": "query", "format": "json", "generator": "search", "gsrsearch": f"{query} filetype:bitmap",
        "gsrnamespace": 6, "gsrlimit": SEARCH_LIMIT, "prop": "imageinfo", "iiprop": "url", "iiurlwidth": 640,
    })
    r.raise_for_status()
    pages = sorted(r.json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    hits = []
    for page in pages:
        info = (page.get("imageinfo") or [{}])[0]
        url = info.get("thumburl") or info.get("url")
        if url:
            hits.append(PhotoHit(url=url, words=page.get("title", "").removeprefix("File:").rsplit(".", 1)[0]))
    return hits


async def _search(client: httpx.AsyncClient, query: str) -> list[PhotoHit]:
    if config.PIXABAY_API_KEY:
        return await search_pixabay(client, query, config.PIXABAY_API_KEY)
    return await search_wikimedia(client, query)


async def _download(client: httpx.AsyncClient, url: str) -> bytes | None:
    r = await client.get(url)
    r.raise_for_status()
    if not r.headers.get("content-type", "").startswith("image/") or len(r.content) > MAX_BYTES:
        return None
    return r.content


async def shows_dish(agent: Agent, image: bytes, recipe: Recipe) -> bool:
    start = time.perf_counter()
    result = await agent.run([PHOTO_CHECK_PROMPT.format(name=recipe.name),
                              BinaryContent(data=image, media_type="image/jpeg")],
                             model_settings=thinking_settings(False))
    log.debug("photo check for %r: %s, sees %r (%.1fs)", recipe.name, result.output.shows_dish,
              result.output.dish_in_photo, time.perf_counter() - start)
    return result.output.shows_dish


async def find_photo(client: httpx.AsyncClient, recipe: Recipe, model: Model) -> bytes | None:
    """The first candidate the vision model accepts: search the query, then only the kind of dish
    ("frittata") if the full query gave no accepted candidate; the best CHECKS_PER_SEARCH of each."""
    query = photo_query_for(recipe)
    words = query.split()
    if not words:
        return None
    agent = Agent(model, output_type=PhotoCheck)
    checked: set[str] = set()
    for q in dict.fromkeys([query, words[-1]]):
        hits = await _search(client, q)
        urls = [u for u in rank_photos(hits, query) if u not in checked]
        log.debug("photo search %r: %d hits, %d candidates", q, len(hits), len(urls))
        for url in urls[:CHECKS_PER_SEARCH]:
            checked.add(url)
            image = await _download(client, url)
            if image is not None and await shows_dish(agent, image, recipe):
                return image
    return None


def _model(model: Model | None) -> Model:
    if model is not None:
        return model
    from app.llm import vision_model  # needs the API key, so only when no model is given

    return vision_model()


async def recipe_photo(recipe: Recipe, photo_dir: Path | None = None, *,
                       client: httpx.AsyncClient | None = None, model: Model | None = None) -> Path | None:
    """The downloaded photo of the recipe's dish, or None if no photo passes both filters.

    Searched, checked and downloaded on the first call, then read from disk; a search with no accepted
    photo is remembered (`<id>.none`), a failure is not (the next call tries again). A call while the
    same photo is being fetched (the card and the recipe window at once) waits for that fetch. Raises
    httpx.HTTPError (photo service) or pydantic_ai's ModelAPIError (vision model) on failure.
    """
    photo_dir = photo_dir or config.PHOTO_DIR
    path, miss = photo_dir / f"{recipe.id}.jpg", photo_dir / f"{recipe.id}.none"
    if path.exists():
        return path
    if miss.exists():
        return None
    task = _inflight.get(path)
    if task is None:
        task = asyncio.ensure_future(_fetch(recipe, path, miss, client, model))
        _inflight[path] = task
        task.add_done_callback(lambda _: _inflight.pop(path, None))
    return await asyncio.shield(task)  # a caller that goes away does not cancel the others' fetch


_inflight: dict[Path, asyncio.Future] = {}


async def _fetch(recipe: Recipe, path: Path, miss: Path, client: httpx.AsyncClient | None,
                 model: Model | None) -> Path | None:
    own = client is None
    client = client or httpx.AsyncClient(timeout=TIMEOUT_S, headers={"User-Agent": USER_AGENT},
                                         follow_redirects=True)
    try:
        image = await find_photo(client, recipe, _model(model))
    finally:
        if own:
            await client.aclose()
    path.parent.mkdir(parents=True, exist_ok=True)
    if image is None:
        miss.touch()
        return None
    tmp = path.with_suffix(".part")
    tmp.write_bytes(image)
    tmp.replace(path)
    return path
