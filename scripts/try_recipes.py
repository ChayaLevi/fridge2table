"""Manual check of suggest_meals / get_recipe against the real RECIPE_MODEL on a demo inventory.

Usage: uv run python scripts/try_recipes.py [--dish lasagna] [--minutes 30] [--text "kids are eating"]
Uses an in-memory store (fridge scanned, pantry not), so nothing on disk changes.
"""

import argparse
import asyncio
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.llm import setup_observability  # noqa: E402
from app.models import Constraints, InventoryChange, Preference  # noqa: E402
from app.store import Store  # noqa: E402
from app.tools.checks import validate_suggestion  # noqa: E402
from app.tools.inventory import get_inventory, update_inventory  # noqa: E402
from app.tools.recipes import get_recipe, suggest_meals  # noqa: E402

# (name, category, qty, use_soon)
DEMO_FRIDGE = [
    ("spinach", "vegetable", "some", True), ("egg", "egg", "plenty", False), ("milk", "dairy", "some", False),
    ("cheddar", "dairy", "some", False), ("butter", "dairy", "some", False), ("greek yogurt", "dairy", "low", False),
    ("cottage cheese", "dairy", "some", False), ("chicken", "meat", "some", False), ("bacon", "meat", "low", False),
    ("tomato", "vegetable", "plenty", False), ("onion", "vegetable", "plenty", False),
    ("garlic", "vegetable", "some", False), ("carrot", "vegetable", "some", False),
    ("bell pepper", "vegetable", "some", False), ("eggplant", "vegetable", "some", True),
    ("zucchini", "vegetable", "low", False), ("lemon", "fruit", "some", False), ("apple", "fruit", "plenty", False),
    ("mushroom", "vegetable", "some", False), ("pasta", "pasta", "some", False), ("ketchup", "condiment", "some", False),
]


def demo_store() -> Store:
    store = Store(":memory:")
    update_inventory(store, [
        InventoryChange(op="add", name=n, category=c, qty_level=q, use_soon=u, location="fridge")
        for n, c, q, u in DEMO_FRIDGE
    ])
    store.mark_scanned("fridge")
    store.add_preference(Preference(id="demo", text="kids dislike eggplant", avoid=["eggplant"],
                                    created_at=datetime.now()))
    return store


def show(recipe, store) -> None:
    res = validate_suggestion(recipe, get_inventory(store), store.load_preferences(), store.load_scan_state())
    status = "OK  " if res.ok else "FAIL"
    print(f"[{status}] {recipe.name} ({recipe.time_minutes} min) uses: {', '.join(recipe.uses_from_inventory)}")
    print("       ingredients: " + ", ".join(
        f"{i.name}{'' if i.essential else '?'} [{i.category}]" for i in recipe.ingredients))
    if not res.ok:
        print(f"       check: {res.reason}")


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dish", help="also run get_recipe for this dish")
    p.add_argument("--minutes", type=int)
    p.add_argument("--text", default="")
    args = p.parse_args()
    setup_observability()
    store = demo_store()

    print(f"suggest_meals with {config.RECIPE_MODEL} (? = optional)")
    start = time.perf_counter()
    meals = await suggest_meals(store, Constraints(text=args.text, max_minutes=args.minutes))
    print(f"{len(meals)} candidates in {time.perf_counter() - start:.1f}s")
    for r in meals:
        show(r, store)

    if args.dish:
        print(f"\nget_recipe({args.dish!r})")
        start = time.perf_counter()
        r = await get_recipe(store, args.dish)
        print(f"done in {time.perf_counter() - start:.1f}s")
        show(r, store)


if __name__ == "__main__":
    asyncio.run(main())
