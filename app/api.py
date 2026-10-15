"""FastAPI routes: the chat turn, the inventory panel, recipe steps, the opening, demo admin.

The agent, the store and the recipe model are FastAPI dependencies (`get_store`, `get_turn_runner`,
`get_opening_runner`, `get_recipe_model`), so tests swap them with `app.dependency_overrides` and run without a network.
Model and agent failures come back as JSON `{"detail": "..."}` with a message the page can show,
never as a 500 traceback.
"""

import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, get_args

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, computed_field
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.models import Model

from app import config
from app.agent import TurnResult, run_opening, run_turn
from app.llm import setup_observability
from app.models import (
    AgentReply, CookMode, InventoryChange, InventoryItem, Location, Preference, Recipe, ScanState, Substitution, ToolTraceItem,
    TurnUsage,
)
from app.store import Store
from app.tools import inventory, recipes
from app.trace import trace_sentence

log = logging.getLogger(__name__)

MAX_IMAGES = 4
LOCATIONS: tuple[str, ...] = get_args(Location)
STATIC_DIR = Path(__file__).resolve().parent / "static"

# Shown when the proactive opening fails (model down, bad reply): the page never opens on an error.
OPENING_MESSAGE = (
    "Hi! Send me photos of your fridge and pantry (tag each with its place), "
    "or ask me what you can cook tonight."
)
MODEL_DOWN = "The model service did not answer. Please try again."
AGENT_FAILED = "Sorry, I could not put together a valid answer this time. Please try again or rephrase."


# --- dependencies ---------------------------------------------------------------------------------

_store: Store | None = None


def get_store() -> Store:
    """One store per process, opened on first use (DB_PATH)."""
    global _store
    if _store is None:
        _store = Store()
    return _store


TurnRunner = Callable[..., Awaitable[TurnResult]]


def get_turn_runner() -> TurnRunner:
    """The agent turn (`app.agent.run_turn` on AGENT_MODEL); tests inject one on a FunctionModel."""
    return run_turn


def get_opening_runner() -> TurnRunner:
    """The proactive greeting (`app.agent.run_opening`); tests inject one on a FunctionModel."""
    return run_opening


def get_recipe_model() -> Model | None:
    """Model for recipe steps; None = RECIPE_MODEL from config."""
    return None


StoreDep = Annotated[Store, Depends(get_store)]


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_observability()
    yield
    global _store
    if _store is not None:
        _store.close()
        _store = None


app = FastAPI(title="Fridge-to-Table", lifespan=lifespan)


# --- response models ------------------------------------------------------------------------------

class InventoryState(BaseModel):
    """What the side panel shows: every item (staples included) and which places were scanned."""

    inventory: list[InventoryItem]
    scan_state: ScanState


class ChatResponse(InventoryState):
    reply: AgentReply  # meals are filled (full recipes, without steps)
    trace: list[ToolTraceItem]
    usage: TurnUsage | None = None  # None when no model ran (welcome or fallback greeting)

    @computed_field
    @property
    def trace_summary(self) -> str:
        """The collapsed trace line: "3 steps · updated the inventory (removed egg) → 5 ideas → checked by code"."""
        return trace_sentence(self.trace)


def _state(store: Store) -> dict:
    return {"inventory": inventory.get_inventory(store), "scan_state": store.load_scan_state()}


# --- routes ---------------------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


def _locations(raw: list[str], n_images: int) -> list[Location]:
    """One place tag per image. Accepts repeated fields or one comma-separated field (/docs sends that)."""
    tags = [t.strip().lower() for value in raw for t in value.split(",") if t.strip()]
    if len(tags) != n_images:
        raise HTTPException(400, f"Send one location per image: got {n_images} image(s) and {len(tags)} location(s).")
    bad = [t for t in tags if t not in LOCATIONS]
    if bad:
        raise HTTPException(400, f"Unknown location(s) {', '.join(bad)}; use one of: {', '.join(LOCATIONS)}.")
    return tags  # type: ignore[return-value]


async def _save_uploads(images: list[UploadFile]) -> list[Path]:
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    for image in images:
        suffix = Path(image.filename or "").suffix.lower() or ".jpg"
        path = config.UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
        path.write_bytes(await image.read())
        paths.append(path)
    return paths


@app.post("/chat")
async def chat(
    store: StoreDep,
    runner: Annotated[TurnRunner, Depends(get_turn_runner)],
    session_id: Annotated[str, Form()],
    message: Annotated[str, Form()] = "",
    images: Annotated[list[UploadFile], File(description=f"Up to {MAX_IMAGES} photos")] = [],
    locations: Annotated[list[str], Form(description="One of fridge|freezer|pantry per image, in order")] = [],
    cook_mode: Annotated[CookMode, Form(description="home = only what is there; shop = a few items to buy are OK")] = "home",
) -> ChatResponse:
    """One chat turn: the agent's reply with meal cards, the trace, and the refreshed inventory panel."""
    images = [i for i in images if i.filename]  # /docs sends an empty file part when none is chosen
    if len(images) > MAX_IMAGES:
        raise HTTPException(400, f"At most {MAX_IMAGES} photos per message.")
    tags = _locations(locations, len(images))
    if not message.strip() and not images:
        raise HTTPException(400, "Send a message or at least one photo.")
    paths = await _save_uploads(images)
    try:
        turn = await runner(store, session_id, message, list(zip(paths, tags)), cook_mode=cook_mode)
    except ModelAPIError as e:
        log.warning("chat %s: model API error: %s", session_id, e)
        raise HTTPException(503, MODEL_DOWN) from e
    except (UnexpectedModelBehavior, UsageLimitExceeded) as e:
        log.warning("chat %s: agent failed: %s", session_id, e)
        raise HTTPException(502, AGENT_FAILED) from e
    return ChatResponse(reply=turn.reply, trace=turn.trace, usage=turn.usage, **_state(store))


@app.get("/inventory")
def get_inventory(store: StoreDep) -> InventoryState:
    return InventoryState(**_state(store))


@app.patch("/inventory")
def patch_inventory(store: StoreDep, changes: list[InventoryChange]) -> InventoryState:
    """The panel's direct edits (no agent). Items edited here are `source="manual"` and win over photos."""
    inventory.update_inventory(store, changes, source="manual")
    return InventoryState(**_state(store))


@app.post("/inventory/reset")
def reset_inventory(store: StoreDep) -> InventoryState:
    """The panel's "Start over" (the user confirmed it): every item and every scan date is deleted, so new
    photos rebuild the inventory. Preferences, staples (added or removed) and chats stay; /admin/reset is
    the one that deletes everything."""
    store.clear_inventory()
    return InventoryState(**_state(store))


@app.get("/recipe/{recipe_id}/steps")
async def recipe_steps(
    recipe_id: str, store: StoreDep, model: Annotated[Model | None, Depends(get_recipe_model)],
    sub: Annotated[list[str], Query(description="A substitute from the reply, as missing:use_instead "
                                                "(e.g. ricotta:cottage cheese); repeat for several")] = [],
) -> Recipe:
    """The recipe with its steps: one RECIPE_MODEL call the first time, then from the store.

    With `sub`, the steps use the substitutes ("mix the cottage cheese ...") and are stored separately.
    """
    pairs = [s.split(":", 1) for s in sub if ":" in s]
    substitutions = [Substitution(missing=m.strip(), use_instead=u.strip()) for m, u in pairs if m.strip() and u.strip()]
    try:
        return await recipes.get_steps(store, recipe_id, substitutions, model=model)
    except KeyError as e:
        raise HTTPException(404, f"Unknown recipe id {recipe_id!r}.") from e
    except ModelAPIError as e:
        raise HTTPException(503, MODEL_DOWN) from e
    except (UnexpectedModelBehavior, ValueError) as e:
        log.warning("steps for %s failed: %s", recipe_id, e)
        raise HTTPException(502, "Could not write the steps for this recipe. Please try again.") from e


@app.get("/opening")
async def opening(
    store: StoreDep, runner: Annotated[TurnRunner, Depends(get_opening_runner)], session_id: str,
) -> ChatResponse:
    """Greeting when the page opens or a new chat starts (T4.1).

    Empty inventory: a fixed welcome asking for photos (no model call). Otherwise the agent greets and
    offers one validated meal, preferring use-soon items. If that fails, a static greeting.
    """
    try:
        turn = await runner(store, session_id)
    except (ModelAPIError, UnexpectedModelBehavior, UsageLimitExceeded) as e:
        log.warning("opening %s failed, static greeting: %s", session_id, e)
        return ChatResponse(reply=AgentReply(message=OPENING_MESSAGE), trace=[], **_state(store))
    usage = turn.usage if turn.result is not None else None
    return ChatResponse(reply=turn.reply, trace=turn.trace, usage=usage, **_state(store))


# --- demo admin -----------------------------------------------------------------------------------

def seed_store(store: Store, seed: dict) -> None:
    """Apply a demo seed on top of the current state (see data/demo_seed.json for the format)."""
    changes = [InventoryChange(op="add", **item) for item in seed.get("inventory", [])]
    inventory.update_inventory(store, changes, source="chat")  # not "manual": photos may still update them
    for place in seed.get("scanned", []):
        store.mark_scanned(place)
    for pref in seed.get("preferences", []):
        store.add_preference(Preference.model_validate(pref))


@app.post("/admin/seed")
def admin_seed(store: StoreDep) -> InventoryState:
    """Add the demo inventory from data/demo_seed.json (run /admin/reset first for a clean demo)."""
    seed_store(store, json.loads(config.DEMO_SEED_PATH.read_text(encoding="utf-8")))
    return InventoryState(**_state(store))


@app.post("/admin/reset")
def admin_reset(store: StoreDep) -> InventoryState:
    """Delete everything: inventory, preferences, removed staples, scan state, chat sessions, recipes."""
    store.reset_all()
    return InventoryState(**_state(store))
