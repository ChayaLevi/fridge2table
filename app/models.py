import secrets
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from pydantic.json_schema import SkipJsonSchema

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


def new_recipe_id() -> str:
    """Short random id ("a3f9c1"): what the agent puts in AgentReply.meal_ids and the API uses for steps."""
    return secrets.token_hex(3)


class Recipe(BaseModel):
    id: str = Field(default_factory=new_recipe_id)
    name: str
    ingredients: list[Ingredient]
    steps: list[str] = []  # empty until get_steps() generates them on demand (when the user opens the card)
    time_minutes: int
    servings: int = 4
    uses_from_inventory: list[str] = []  # canonical names, filled by code, not by the model


class MealCandidate(BaseModel):
    """What the agent sees of a recipe: id, name, ingredients and time, never the steps (fewer tokens)."""

    id: str
    name: str
    time_minutes: int
    ingredients: list[str]  # "tomato: 2", "parsley: a handful (optional)"
    uses_from_inventory: list[str] = []

    @classmethod
    def from_recipe(cls, recipe: Recipe) -> "MealCandidate":
        return cls(
            id=recipe.id, name=recipe.name, time_minutes=recipe.time_minutes,
            ingredients=[f"{i.name}: {i.amount}" + ("" if i.essential else " (optional)") for i in recipe.ingredients],
            uses_from_inventory=recipe.uses_from_inventory,
        )


class FailedCandidate(BaseModel):
    id: str
    name: str
    reason: str  # from validate_suggestion: "missing: cream; pantry not scanned: pasta not confirmed"


class SuggestResult(BaseModel):
    """suggest_meals output: candidates already checked by code against the inventory and preferences."""

    passed: list[MealCandidate]  # may be shown as they are
    failed: list[FailedCandidate]  # not to be shown as Mode A meals; the reason says what is missing

    def summary(self) -> str:
        """One line for logs and the trace: "passed 3: A, B, C; failed 1: D (missing: cream)"."""
        parts = [f"passed {len(self.passed)}: {', '.join(c.name for c in self.passed) or '-'}"]
        if self.failed:
            parts.append(f"failed {len(self.failed)}: " + ", ".join(f"{c.name} ({c.reason})" for c in self.failed))
        return "; ".join(parts)


class Preference(BaseModel):
    id: str
    text: str  # "kids dislike eggplant"
    avoid: list[str]  # canonical ingredients
    created_at: datetime


class MissingReport(BaseModel):
    missing_essential: list[str]  # definitely missing ("To buy")
    check_first: list[str]  # pantry-type, pantry not scanned ("Check your pantry first")
    missing_optional: list[str]

    def summary(self) -> str:
        parts = []
        if self.missing_essential:
            parts.append(f"to buy: {', '.join(self.missing_essential)}")
        if self.check_first:
            parts.append(f"check first: {', '.join(self.check_first)}")
        if self.missing_optional:
            parts.append(f"optional: {', '.join(self.missing_optional)}")
        return "; ".join(parts) or "nothing missing"


class ValidationResult(BaseModel):
    ok: bool
    missing_essential: list[str]
    violated_preferences: list[str]
    check_first: list[str] = []  # pantry-type essentials not confirmed because the pantry was not scanned
    reason: str = ""  # one line for the agent, e.g. "pantry not scanned: pasta not confirmed"


class Substitution(BaseModel):
    missing: str
    use_instead: str  # must be in the inventory (checked)


class StepTiming(BaseModel):
    """One timed step of an agent turn: a model call or a tool call (for the trace and for T5.2)."""

    kind: Literal["model", "tool"]
    name: str  # model: "agent deepseek-v4-pro" / "recipe deepseek-flash"; tool: the tool name
    seconds: float
    detail: str = ""  # model: what it returned ("-> suggest_meals", "thinking 1200 chars"); tool: result summary
    input_tokens: int | None = None
    output_tokens: int | None = None


class ToolTraceItem(BaseModel):
    tool: str
    args_summary: str
    result_summary: str


class AgentReply(BaseModel):
    message: str  # short text
    meal_ids: list[str] = []  # ids of recipes returned by tools in this run: Mode A cards (max 3) or the Mode B recipe
    meals: SkipJsonSchema[list[Recipe]] = []  # filled by code from the run's recipe cache, never by the model
    substitutions: list[Substitution] = []
    shopping_list: list[str] = []  # "To buy"
    check_first: list[str] = []  # "Check your pantry first"
    questions: list[str] = []  # clarifying questions about uncertain items (max 3)
    # trace is attached by the server from the run's messages, not produced by the model
