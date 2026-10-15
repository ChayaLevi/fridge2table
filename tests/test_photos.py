"""Dish photos: the query, the ranking, Pixabay / Wikimedia parsing, the vision check and the disk cache
(no network: httpx.MockTransport plays both services, a FunctionModel plays VISION_MODEL)."""

import asyncio

import httpx
import pytest
from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app import config
from app.models import Recipe
from app.tools.photos import PhotoHit, photo_query_for, rank_photos, recipe_photo

JPEG = b"\xff\xd8\xff\xe0fake-jpeg"


def recipe(name="Spinach and feta frittata", photo_query="spinach frittata", rid="abc123"):
    return Recipe(id=rid, name=name, ingredients=[], time_minutes=20, photo_query=photo_query)


def hit(url, words):
    return PhotoHit(url=url, words=words)


# --- query and ranking ----------------------------------------------------------------------------

@pytest.mark.parametrize("name, query, expected", [
    ("Spinach and feta frittata", "spinach frittata", "spinach frittata"),
    ("Garlic pasta with basil", "", "garlic pasta"),
    ("Chicken curry (mild), with rice", "", "chicken curry"),
    ("Quick Weeknight Tomato Lentil Soup", "", "tomato lentil soup"),
    ("Shakshuka", " Shakshuka! ", "shakshuka"),
])
def test_photo_query_for(name, query, expected):
    assert photo_query_for(recipe(name, query)) == expected


def test_rank_needs_the_kind_of_dish():
    # Pixabay ranks salmon cakes first for "spinach frittata"
    hits = [hit("salmon", "salmon cakes, pancake, omelette"), hit("frit", "frittata, eggs, skillet")]
    assert rank_photos(hits, "spinach frittata") == ["frit"]
    assert rank_photos([hit("salmon", "salmon cakes, pancake")], "spinach frittata") == []
    assert rank_photos([hit("x", "anything")], "") == []


def test_rank_puts_the_subject_first_then_more_query_words():
    hits = [
        hit("stuffed", "cooking, food, kitchen, chicken, pasta, tomatoes"),  # pasta only in the late tags
        hit("a", "pasta, italian"),
        hit("b", "spaghetti, tomatoes, pasta"),  # plurals match
        hit("c", "tomato, pasta"),
    ]
    assert rank_photos(hits, "tomato chicken pasta") == ["b", "c", "a", "stuffed"]


def test_rank_matches_words_inside_tags_and_file_names():
    assert rank_photos([hit("w", "Bowl of lentil soup with green lentils")], "lentil soup") == ["w"]
    assert rank_photos([hit("s", "wok, stir-fry, vegetables")], "vegetable stir fry") == ["s"]
    assert rank_photos([hit("x", "fryer")], "stir fry") == []


# --- search, check and download ------------------------------------------------------------------

class FakeWeb:
    """Pixabay, Wikimedia and the image host. An image's bytes are JPEG + its URL, so the fake vision model
    can tell them apart; `searches` records each search query."""

    def __init__(self, pixabay=None, wikimedia=None, image_status=200, content_type="image/jpeg"):
        self.pixabay = pixabay or {}
        self.wikimedia = wikimedia or {}
        self.image_status, self.content_type = image_status, content_type
        self.searches: list[tuple[str, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if request.url.host == "pixabay.com":
            self.searches.append(("pixabay", params["q"]))
            assert params["key"] == "test-key" and params["category"] == "food"
            hits = [{"webformatURL": u, "tags": t} for u, t in self.pixabay.get(params["q"], [])]
            return httpx.Response(200, json={"hits": hits})
        if request.url.host == "commons.wikimedia.org":
            q = params["gsrsearch"].removesuffix(" filetype:bitmap")
            self.searches.append(("wikimedia", q))
            found = self.wikimedia.get(q, [])
            # pages come keyed by page id, in no order; "index" is the search rank
            pages = {str(100 - i): {"index": i + 1, "title": f"File:{t}.jpg", "imageinfo": [{"thumburl": u}]}
                     for i, (u, t) in reversed(list(enumerate(found)))}
            return httpx.Response(200, json={"query": {"pages": pages}} if pages else {})
        return httpx.Response(self.image_status, content=JPEG + str(request.url).encode(),
                              headers={"content-type": self.content_type})

    def client(self):
        return httpx.AsyncClient(transport=httpx.MockTransport(self))


def vision(accept: str = "good"):
    """A vision model that accepts images whose URL contains `accept`; records each URL it saw."""
    seen: list[str] = []

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        prompt = messages[-1].parts[-1].content
        image = next(c for c in prompt if isinstance(c, BinaryContent))
        url = image.data.removeprefix(JPEG).decode()
        seen.append(url)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "dish_in_photo": "something", "shows_dish": accept in url})])

    return FunctionModel(fn), seen


@pytest.fixture
def pixabay_key(monkeypatch):
    monkeypatch.setattr(config, "PIXABAY_API_KEY", "test-key")


@pytest.fixture
def no_key(monkeypatch):
    monkeypatch.setattr(config, "PIXABAY_API_KEY", None)


async def test_checked_photo_is_downloaded_once(pixabay_key, tmp_path):
    web = FakeWeb(pixabay={"spinach frittata": [("https://img/salmon.jpg", "salmon cakes"),
                                                ("https://img/good-frit.jpg", "frittata, spinach")]})
    model, seen = vision()
    async with web.client() as client:
        path = await recipe_photo(recipe(), tmp_path, client=client, model=model)
        assert path == tmp_path / "abc123.jpg" and path.read_bytes() == JPEG + b"https://img/good-frit.jpg"
        assert await recipe_photo(recipe(), tmp_path, client=client, model=model) == path
    assert web.searches == [("pixabay", "spinach frittata")]
    assert seen == ["https://img/good-frit.jpg"]  # the salmon cakes never reach the model


async def test_the_check_rejects_a_photo_whose_tags_lie(pixabay_key, tmp_path):
    web = FakeWeb(pixabay={"tomato pasta": [("https://img/tortilla.jpg", "pasta, pizza, lasagna"),
                                            ("https://img/good-penne.jpg", "pasta, tomato, penne")]})
    model, seen = vision()
    async with web.client() as client:
        path = await recipe_photo(recipe("Tomato pasta", "tomato pasta"), tmp_path, client=client, model=model)
    assert path.read_bytes().endswith(b"good-penne.jpg")
    # the penne has both query words, so it is checked first
    assert seen == ["https://img/good-penne.jpg"]


async def test_two_checks_per_search_then_the_kind_of_dish(pixabay_key, tmp_path):
    web = FakeWeb(pixabay={
        "spinach frittata": [(f"https://img/bad{i}.jpg", "frittata") for i in range(4)],
        "frittata": [("https://img/bad0.jpg", "frittata"), ("https://img/good.jpg", "frittata")],
    })
    model, seen = vision()
    async with web.client() as client:
        assert await recipe_photo(recipe(), tmp_path, client=client, model=model) is not None
    assert web.searches == [("pixabay", "spinach frittata"), ("pixabay", "frittata")]
    assert seen == ["https://img/bad0.jpg", "https://img/bad1.jpg", "https://img/good.jpg"]  # bad0 not twice


async def test_no_candidate_is_remembered(pixabay_key, tmp_path):
    web = FakeWeb(pixabay={"frittata": [("https://img/fritter.jpg", "sweetcorn fritter balls")]})
    model, seen = vision()
    async with web.client() as client:
        assert await recipe_photo(recipe(), tmp_path, client=client, model=model) is None
        assert await recipe_photo(recipe(), tmp_path, client=client, model=model) is None
    assert len(web.searches) == 2 and seen == [] and (tmp_path / "abc123.none").exists()


async def test_rejected_by_the_check_is_remembered(pixabay_key, tmp_path):
    web = FakeWeb(pixabay={"frittata": [("https://img/bad.jpg", "frittata")]})
    model, seen = vision()
    async with web.client() as client:
        assert await recipe_photo(recipe(), tmp_path, client=client, model=model) is None
    assert seen == ["https://img/bad.jpg"] and (tmp_path / "abc123.none").exists()


async def test_without_a_key_searches_wikimedia(no_key, tmp_path):
    web = FakeWeb(wikimedia={"lentil soup": [("https://up/sweet.jpg", "Sweet corn"),
                                             ("https://up/good-soup.jpg", "Bowl of lentil soup"),
                                             ("https://up/good-soup2.jpg", "Lentil soup in Beirut")]})
    model, seen = vision()
    async with web.client() as client:
        path = await recipe_photo(recipe("Lentil soup", ""), tmp_path, client=client, model=model)
    assert path is not None and web.searches == [("wikimedia", "lentil soup")]
    assert seen == ["https://up/good-soup.jpg"]  # search rank kept


async def test_a_non_image_is_not_checked(pixabay_key, tmp_path):
    web = FakeWeb(pixabay={"spinach frittata": [("https://img/good.jpg", "frittata")]}, content_type="text/html")
    model, seen = vision()
    async with web.client() as client:
        assert await recipe_photo(recipe(), tmp_path, client=client, model=model) is None
    assert seen == [] and not (tmp_path / "abc123.jpg").exists()


async def test_a_network_failure_raises_and_is_not_remembered(pixabay_key, tmp_path):
    web = FakeWeb(pixabay={"spinach frittata": [("https://img/good.jpg", "frittata")]}, image_status=503)
    model, _ = vision()
    async with web.client() as client:
        with pytest.raises(httpx.HTTPStatusError):
            await recipe_photo(recipe(), tmp_path, client=client, model=model)
    assert list(tmp_path.iterdir()) == []


async def test_two_calls_at_once_share_one_fetch(pixabay_key, tmp_path):
    web = FakeWeb(pixabay={"spinach frittata": [("https://img/good.jpg", "frittata")]})
    model, seen = vision()
    async with web.client() as client:
        a, b = await asyncio.gather(recipe_photo(recipe(), tmp_path, client=client, model=model),
                                    recipe_photo(recipe(), tmp_path, client=client, model=model))
    assert a == b == tmp_path / "abc123.jpg"
    assert len(web.searches) == 1 and len(seen) == 1
