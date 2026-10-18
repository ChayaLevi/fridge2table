import secrets
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, computed_field
from pydantic.json_schema import SkipJsonSchema

from app.amounts import Unit, format_amount

QtyLevel = Literal["plenty", "some", "low"]
Location = Literal["fridge", "freezer", "pantry"]
# The user's switch in the page (T4.5): "home" = suggested meals use only what is there; "shop" = each
# suggested meal may need up to MAX_TO_BUY items to buy. A dish the user names gets its list either way.
CookMode = Literal["home", "shop"]
MAX_TO_BUY = 3

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
    # Was in a place the user photographed again, but not recognized in the new photos (maybe finished).
    # Kept until the user confirms (still there) or removes it, or a later photo shows it.
    not_seen: bool = False
    is_staple: bool = False
    source: Literal["photo", "chat", "manual", "staple"]
    updated_at: datetime
    # Optional exact amount (T6.3), only from the user (panel or chat), stored as entered; recognition never
    # sets it. Independent of qty_level, which stays the level the checks use.
    amount: float | None = None
    unit: Unit | None = None

    @computed_field
    @property
    def amount_text(self) -> str:
        """For display: "2 l", "1.5 kg", "" when there is no amount."""
        return format_amount(self.amount, self.unit)


class InventoryChange(BaseModel):
    op: Literal["add", "remove", "set_qty", "set_use_soon", "rename", "add_staple", "confirm", "set_amount"]
    name: str  # ingredient the change applies to
    display_name: str | None = None  # add
    category: str | None = None  # add
    location: Location | None = None  # add
    qty_level: QtyLevel | None = None  # add, set_qty
    use_soon: bool | None = None  # add, set_use_soon
    new_name: str | None = None  # rename
    amount: float | None = Field(default=None, ge=0)  # set_amount (None or 0 clears it), add
    unit: Unit | None = None  # set_amount, add; None = the default unit for the item's category


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
    requested: bool = False  # True for a dish the user named (get_recipe), False for a suggest_meals idea
    photo_query: str = ""  # 1-3 words for the card's photo search ("spinach frittata"); "" = search by the name


class MealCandidate(BaseModel):
    """What the agent sees of a recipe: id, name, ingredients and time, never the steps (fewer tokens)."""

    id: str
    name: str
    time_minutes: int
    ingredients: list[str]  # "tomato: 2", "parsley: a handful (optional)"
    uses_from_inventory: list[str] = []
    # what the household lacks for it (code): shop-mode suggestions and get_recipe; the lists are built by code
    to_buy: list[str] = []
    check_first: list[str] = []
    not_enough: list[str] = []  # "not enough egg (have 4, need 5)" for items in to_buy / check_first

    @classmethod
    def from_recipe(cls, recipe: Recipe, report: "MissingReport | None" = None) -> "MealCandidate":
        return cls(
            id=recipe.id, name=recipe.name, time_minutes=recipe.time_minutes,
            ingredients=[f"{i.name}: {i.amount}" + ("" if i.essential else " (optional)") for i in recipe.ingredients],
            uses_from_inventory=recipe.uses_from_inventory,
            to_buy=report.missing_essential if report else [], check_first=report.check_first if report else [],
            not_enough=[s.text() for s in report.not_enough] if report else [],
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


class Shortfall(BaseModel):
    """An ingredient the household has, but less of than the recipe needs (T6.3b): only when the user
    entered an exact amount and the recipe amount parses in a unit of the same kind."""

    name: str  # canonical
    have: str  # "4", "200 g" (amount_short)
    need: str  # "5", "300 g"

    def text(self) -> str:
        return f"not enough {self.name} (have {self.have}, need {self.need})"


class MissingReport(BaseModel):
    missing_essential: list[str]  # definitely missing ("To buy"); includes the names in not_enough
    check_first: list[str]  # pantry-type, pantry not scanned ("Check your pantry first")
    missing_optional: list[str]
    not_enough: list[Shortfall] = []  # essentials there but short (also listed in missing_essential or check_first)

    def summary(self) -> str:
        parts = []
        if self.missing_essential:
            parts.append(f"to buy: {', '.join(self.missing_essential)}")
        if self.check_first:
            parts.append(f"check first: {', '.join(self.check_first)}")
        if self.missing_optional:
            parts.append(f"optional: {', '.join(self.missing_optional)}")
        parts += [s.text() for s in self.not_enough]
        return "; ".join(parts) or "nothing missing"


class ValidationResult(BaseModel):
    ok: bool
    missing_essential: list[str]
    violated_preferences: list[str]
    check_first: list[str] = []  # pantry-type essentials not confirmed because the pantry was not scanned
    not_enough: list[Shortfall] = []  # essentials there but short (also in missing_essential / check_first)
    reason: str = ""  # one line for the agent, e.g. "pantry not scanned: pasta not confirmed"


class Substitution(BaseModel):
    missing: str
    use_instead: str  # must be in the inventory (checked)


class StepTiming(BaseModel):
    """One timed step of an agent turn: a model call, a tool call or the output check (for the trace and T5.2)."""

    kind: Literal["model", "tool", "check"]
    name: str  # model: "agent deepseek-v4-pro" / "recipe deepseek-flash"; tool: the tool name; check: "output check"
    seconds: float
    detail: str = ""  # model: what it returned ("-> suggest_meals"); tool: result summary; check: "ok" / "output check failed: ..."
    input_tokens: int | None = None
    output_tokens: int | None = None
    call_id: str | None = None  # tool / check: the tool call id, so the trace can attach the seconds


class ToolTraceItem(BaseModel):
    """One line of the trace the user sees under an agent reply (built by app/trace.py)."""

    tool: str  # tool name, or "output check" for the validator of the final reply
    args_summary: str  # short: "remove egg", "'quick' max 30 min", "Lasagna"
    result_summary: str  # short: "removed 1", "5 candidates: 4 passed, 1 failed (Carbonara: missing: cream)"
    failed: bool = False  # a failed check (incl. failed candidates), a retry or an error (warning colour, T4.4)
    seconds: float | None = None  # from TurnResult.steps; None when the call never ran (bad args)
    label: str = ""  # plain words for the collapsed line: "5 ideas, 1 failed check (no cream)" (T4.4)


class TurnUsage(BaseModel):
    """Latency and token usage of one agent turn (for T5.2)."""

    latency_s: float
    requests: int
    tool_calls: int
    input_tokens: int
    output_tokens: int


class AgentReply(BaseModel):
    message: str  # short text
    meal_ids: list[str] = []  # ids of recipes returned by tools in this run: Mode A cards (max 3) or the Mode B recipe
    meals: SkipJsonSchema[list[Recipe]] = []  # filled by code from the run's recipe cache, never by the model
    substitutions: list[Substitution] = []
    shopping_list: list[str] = []  # "To buy"
    check_first: list[str] = []  # "Check your pantry first"
    # items of shopping_list / check_first the household has too little of ("egg: have 4, need 5"); set by code
    not_enough: SkipJsonSchema[list[Shortfall]] = []
    questions: list[str] = []  # clarifying questions about uncertain items (max 3)
    # True when the message is not about food or the kitchen; code then replaces message with a fixed reply
    off_topic: bool = False
    # Set by code in home mode when the turn showed fewer than 2 suggested meals: the page offers a
    # "Shopping OK" button (T4.5). Never set by the model.
    offer_shop: SkipJsonSchema[bool] = False
    # trace is attached by the server from the run's messages, not produced by the model
