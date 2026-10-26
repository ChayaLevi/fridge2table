"""Grocery deliveries: from an order's lines to inventory changes (docs/MAIL_DEMO_PLAN.md, D2).

No LLM: the final list, the cooking filter and the apply step are deterministic. In the demo the order
comes from data/demo_delivery.json; the full mail pipeline (docs/MAIL_PLAN.md) will feed the same
GroceryOrder from the retailer's emails.
"""

from typing import Literal, get_args

from app.amounts import Unit, format_amount
from app.models import BoughtItem, DeliveredItem, DeliveryNotice, GroceryOrder, OrderLine
from app.store import Store
from app.tools import inventory
from app.tools.normalize import normalize

Relevance = Literal["cooking_ingredient", "non_food", "uncertain"]

# The retailer's section → our category. A section not listed here gives no category.
RETAILER_CATEGORIES = {
    "fruit & veg": "vegetable", "fruit and veg": "vegetable", "produce": "vegetable", "vegetables": "vegetable",
    "fruit": "fruit", "dairy & eggs": "dairy", "dairy": "dairy", "eggs": "egg", "cheese": "dairy",
    "meat & fish": "meat", "meat": "meat", "poultry": "meat", "fish": "fish", "seafood": "fish",
    "pantry": "grain", "dry goods": "grain", "bakery": "grain", "pasta & rice": "pasta", "canned": "canned",
    "baking": "baking", "spices": "spice", "sauces": "sauce", "condiments": "condiment", "frozen": "frozen",
}
# Sections and words that mean "not something to cook with": never added to the inventory.
NON_FOOD_CATEGORIES = {
    "household", "cleaning", "pet", "pets", "personal care", "toiletries", "health & beauty", "baby", "home",
}
NON_FOOD_WORDS = (
    "toilet paper", "paper towel", "kitchen roll", "tissue", "dish soap", "soap", "detergent", "bleach",
    "sponge", "trash bag", "bin bag", "foil", "cling film", "shampoo", "toothpaste", "diaper", "nappy",
    "cat food", "dog food", "pet food", "cat litter", "litter",
)
_DROPPED: set[str] = {"missing", "refunded"}
_UNITS: set[str] = set(get_args(Unit))


def final_lines(lines: list[OrderLine]) -> list[OrderLine]:
    """What actually arrived: missing and refunded lines are dropped, a substituted line replaces the line
    it names (substitute_for), a weighed line keeps its actual weight. Other lines count as delivered."""
    replaced = {s.substitute_for.strip().lower() for s in lines if s.line_status == "substituted" and s.substitute_for}
    return [ln for ln in lines
            if ln.line_status not in _DROPPED
            and not (ln.line_status != "substituted" and ln.raw_name.strip().lower() in replaced)]


def classify_line(line: OrderLine) -> tuple[Relevance, str | None]:
    """Is this line something to cook with? Returns the relevance and our category (None if unknown).

    Non-food section or words → non_food; a food section → cooking_ingredient; otherwise uncertain
    (the panel asks the user)."""
    section = (line.retailer_category or "").strip().lower()
    words = f" {' '.join(line.raw_name.lower().split())} "
    if section in NON_FOOD_CATEGORIES or any(f" {w} " in words for w in NON_FOOD_WORDS):
        return "non_food", None
    category = RETAILER_CATEGORIES.get(section)
    return ("cooking_ingredient" if category else "uncertain"), category


def line_amount(line: OrderLine) -> tuple[float, Unit] | None:
    """qty × pack size when the unit is one the inventory knows (T6.3), else None (plenty only)."""
    unit = (line.pack_unit or "").strip().lower()
    if line.pack_size is None or unit not in _UNITS:
        return None
    return round(line.qty * line.pack_size, 6), unit  # type: ignore[return-value]


def apply_delivery(store: Store, order: GroceryOrder) -> DeliveryNotice:
    """Put a delivered order's cooking ingredients in the inventory and save a notice for the page.

    Each one is added like a "Bought" item (inventory.mark_bought): plenty, its place by category, and
    the delivered amount when the unit is supported (added to the amount the item had). Uncertain lines
    are added flagged uncertain, so the panel asks keep / remove. Non-food, missing and refunded lines
    are never added; a substitute goes in under its own name. One undo token takes it all back out.
    """
    final = final_lines(order.lines)
    bought: list[BoughtItem] = []
    uncertain: list[str] = []
    skipped: list[str] = []
    for line in final:
        relevance, category = classify_line(line)
        if relevance == "non_food":
            skipped.append(line.raw_name)
            continue
        amount = line_amount(line)
        bought.append(BoughtItem(name=line.raw_name, category=category,
                                 amount=amount[0] if amount else None, unit=amount[1] if amount else None))
        if relevance == "uncertain":
            uncertain.append(line.raw_name)

    token = inventory.undo_point(store, [b.name for b in bought])
    inventory.mark_bought(store, bought, source="chat")
    unsure = {normalize(n) for n in uncertain}
    if unsure:
        stored = store.load_inventory()
        for item in stored:
            if item.name in unsure:
                item.uncertain, item.confidence = True, 0.5
        store.save_inventory(stored)

    staples = set(inventory.all_staples(store))
    added = [DeliveredItem(name=n, display_name=b.name.strip(),
                           amount_text=format_amount(b.amount, b.unit) if b.amount and b.unit else None)
             for b in bought if (n := normalize(b.name)) and n not in staples]
    notice = DeliveryNotice(
        retailer=order.retailer, order_id=order.order_id, added=added, uncertain=uncertain, skipped=skipped,
        unavailable=[ln.raw_name for ln in order.lines if ln.line_status in _DROPPED],
        substituted=[(ln.substitute_for, ln.raw_name) for ln in final
                     if ln.line_status == "substituted" and ln.substitute_for],
        undo=token,
    )
    store.add_notice(notice)
    return notice
