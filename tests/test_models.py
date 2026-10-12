from datetime import datetime

from app.models import (
    AgentReply, Constraints, Ingredient, InventoryChange, InventoryItem, MissingReport,
    PANTRY_CATEGORIES, Preference, Recipe, ScanState, Substitution, ToolTraceItem, ValidationResult,
)

NOW = datetime(2026, 10, 12, 12, 0, 0)

RECIPE = Recipe(
    name="Spinach omelette",
    ingredients=[Ingredient(name="egg", amount="3", essential=True, category="egg")],
    steps=["Whisk", "Cook"],
    time_minutes=10,
    uses_from_inventory=["egg"],
)

INSTANCES = [
    InventoryItem(
        id="i1", name="greek yogurt", display_name="Greek yogurt", category="dairy",
        qty_level="some", location="fridge", confidence=0.9, uncertain=False,
        use_soon=True, source="photo", updated_at=NOW,
    ),
    InventoryChange(op="add", name="egg", qty_level="plenty", location="fridge"),
    Constraints(text="quick", max_minutes=30),
    Ingredient(name="egg", amount="3", essential=True, category="egg"),
    RECIPE,
    ScanState(scanned={"fridge": NOW}, freezer_declined=True),
    Preference(id="p1", text="kids dislike eggplant", avoid=["eggplant"], created_at=NOW),
    MissingReport(missing_essential=["cream"], check_first=["pasta"], missing_optional=[]),
    ValidationResult(ok=False, missing_essential=["cream"], violated_preferences=[]),
    Substitution(missing="ricotta", use_instead="cottage cheese"),
    ToolTraceItem(tool="suggest_meals", args_summary="quick", result_summary="5 candidates"),
    AgentReply(
        message="Try this", meals=[RECIPE],
        substitutions=[Substitution(missing="ricotta", use_instead="cottage cheese")],
        shopping_list=["cream"], check_first=["pasta"], questions=["Is that rice?"],
    ),
]


def test_round_trip_every_model():
    for obj in INSTANCES:
        cls = type(obj)
        assert cls.model_validate_json(obj.model_dump_json()) == obj, cls.__name__


def test_pantry_categories():
    assert "pasta" in PANTRY_CATEGORIES and "vegetable" not in PANTRY_CATEGORIES
