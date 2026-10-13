from datetime import datetime
from typing import Literal

from pydantic import BaseModel

QtyLevel = Literal["plenty", "some", "low"]
Location = Literal["fridge", "freezer", "pantry"]

CATEGORIES = (
    "vegetable", "fruit", "meat", "fish", "dairy", "egg", "grain", "pasta", "canned", "baking",
    "sauce", "condiment", "spice", "snack", "drink", "frozen", "other",
)


class InventoryItem(BaseModel):
    id: str
    name: str  # canonical, from normalize()
    display_name: str  # what the user sees, e.g. "Greek yogurt"
    category: str  # vegetable, fruit, meat, fish, dairy, egg, grain, pasta, canned, baking, sauce, condiment, spice, snack, drink, frozen, other
    qty_level: QtyLevel
    location: Location
    confidence: float  # 0..1, from recognition; 1.0 for manual
    uncertain: bool  # confidence below threshold, or flagged by the model
    use_soon: bool = False
    is_staple: bool = False
    source: Literal["photo", "chat", "manual", "staple"]
    updated_at: datetime


class InventoryChange(BaseModel):
    op: Literal["add", "remove", "set_qty", "set_use_soon", "rename"]
    name: str  # ingredient the change applies to
    display_name: str | None = None  # add
    category: str | None = None  # add
    location: Location | None = None  # add
    qty_level: QtyLevel | None = None  # add, set_qty
    use_soon: bool | None = None  # add, set_use_soon
    new_name: str | None = None  # rename


class Constraints(BaseModel):
    text: str = ""
    max_minutes: int | None = None


class Ingredient(BaseModel):
    name: str  # canonical
    amount: str  # free text, "300 g", "2", "a handful"
    essential: bool
    category: str  # same categories as InventoryItem; used to decide what is pantry-type


PANTRY_CATEGORIES = {"grain", "pasta", "canned", "baking", "sauce", "condiment", "spice", "snack"}


class ScanState(BaseModel):
    scanned: dict[Location, datetime]  # place -> last scan time; absent = never scanned
    freezer_declined: bool = False


class Recipe(BaseModel):
    name: str
    ingredients: list[Ingredient]
    steps: list[str]
    time_minutes: int
    servings: int = 4
    uses_from_inventory: list[str] = []  # canonical names, filled by code, not by the model


class Preference(BaseModel):
    id: str
    text: str  # "kids dislike eggplant"
    avoid: list[str]  # canonical ingredients
    created_at: datetime


class MissingReport(BaseModel):
    missing_essential: list[str]  # definitely missing ("To buy")
    check_first: list[str]  # pantry-type, pantry not scanned ("Check your pantry first")
    missing_optional: list[str]


class ValidationResult(BaseModel):
    ok: bool
    missing_essential: list[str]
    violated_preferences: list[str]


class Substitution(BaseModel):
    missing: str
    use_instead: str  # must be in the inventory (checked)


class ToolTraceItem(BaseModel):
    tool: str
    args_summary: str
    result_summary: str


class AgentReply(BaseModel):
    message: str  # short text
    meals: list[Recipe] = []  # Mode A cards (max 3) or the Mode B recipe
    substitutions: list[Substitution] = []
    shopping_list: list[str] = []  # "To buy"
    check_first: list[str] = []  # "Check your pantry first"
    questions: list[str] = []  # clarifying questions about uncertain items (max 3)
    # trace is attached by the server from the run's messages, not produced by the model
