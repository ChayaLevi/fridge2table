"""Inventory tools: read, edit, merge recognition results, and summarize for prompts.

The store holds only real items. Staples (data/staples.json) are virtual: get_inventory() adds
every staple the user has not removed, unless a stored item already has that name (stored wins).
Editing a staple (set_qty, set_use_soon, rename) turns it into a stored item; removing it records
the removal in staples_state. The user can add staples of their own (op add_staple, kept in
custom_staples); they behave like the default ones, and removing one deletes it.
"""

import json
import uuid
from datetime import datetime
from functools import lru_cache
from typing import Literal

from app.config import STAPLES_PATH
from app.models import InventoryChange, InventoryItem, Location, ScanState
from app.store import Store
from app.tools.normalize import normalize

LOCATIONS: tuple[Location, ...] = ("fridge", "freezer", "pantry")

# Category of each default staple (anything not listed is "other").
STAPLE_CATEGORIES = {
    "salt": "spice", "black pepper": "spice", "dried oregano": "spice", "paprika": "spice",
    "ground cumin": "spice", "chili flakes": "spice",
    "cooking oil": "condiment", "olive oil": "condiment", "white vinegar": "condiment",
    "soy sauce": "sauce",
    "sugar": "baking", "all-purpose flour": "baking", "baking soda": "baking", "baking powder": "baking",
    "water": "drink",
}


@lru_cache(maxsize=1)
def staple_names() -> tuple[str, ...]:
    """Canonical names of the default staples, in file order."""
    return tuple(normalize(s) for s in json.loads(STAPLES_PATH.read_text(encoding="utf-8")))


def all_staples(store: Store) -> tuple[str, ...]:
    """The default staples, then the ones the user added (canonical names, no duplicates)."""
    return tuple(dict.fromkeys([*staple_names(), *store.load_custom_staples()]))


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _staple_item(name: str, now: datetime) -> InventoryItem:
    return InventoryItem(
        id=f"staple:{name}", name=name, display_name=name, category=STAPLE_CATEGORIES.get(name, "other"),
        qty_level="plenty", location="pantry", confidence=1.0, uncertain=False,
        is_staple=True, source="staple", updated_at=now,
    )


def get_inventory(store: Store) -> list[InventoryItem]:
    """Stored items, then the staples that were not removed and are not already stored."""
    stored = store.load_inventory()
    have = {i.name for i in stored}
    removed = store.load_removed_staples()
    now = datetime.now()
    staples = [_staple_item(s, now) for s in all_staples(store) if s not in removed and s not in have]
    return stored + staples


def update_inventory(
    store: Store, changes: list[InventoryChange], source: Literal["chat", "manual"] = "chat"
) -> list[InventoryItem]:
    """Apply changes and return the full inventory.

    `source` is "manual" for the side panel (those items are then protected from recognition) and
    "chat" for the agent. Rules:
    - add: an existing canonical name is updated, not duplicated.
    - remove: removing a staple records it in staples_state (a user-added staple is deleted).
    - add_staple: the name becomes a staple (assumed always present); a stored item with that name
      is replaced by the staple.
    - set_qty with qty_level=None means "below low": the item is removed.
    - Names that are not in the inventory are ignored for remove/set_qty/set_use_soon/rename.
    """
    stored = store.load_inventory()
    removed = store.load_removed_staples()
    custom = set(store.load_custom_staples())
    now = datetime.now()

    def is_staple(name: str) -> bool:
        return name in staple_names() or name in custom

    def find(name: str) -> InventoryItem | None:
        """The stored item with this canonical name; a visible staple is materialized on demand."""
        for i in stored:
            if i.name == name:
                return i
        if is_staple(name) and name not in removed:
            item = _staple_item(name, now).model_copy(update={"id": _new_id()})
            stored.append(item)
            return item
        return None

    def drop(item: InventoryItem) -> None:
        stored.remove(item)
        if item.name in custom:
            custom.discard(item.name)
            store.set_custom_staple(item.name, present=False)
        elif item.name in staple_names():
            removed.add(item.name)
            store.set_staple_removed(item.name)

    def touch(item: InventoryItem) -> None:
        # A user or agent edit confirms the item.
        item.source, item.confidence, item.uncertain, item.updated_at = source, 1.0, False, now

    for ch in changes:
        name = normalize(ch.name)
        if not name:
            continue
        if ch.op == "add_staple":
            if name in removed:
                removed.discard(name)
                store.set_staple_removed(name, removed=False)
            if name not in staple_names() and name not in custom:
                custom.add(name)
                store.set_custom_staple(name)
            stored = [i for i in stored if i.name != name]
            continue
        if ch.op == "add":
            if name in removed:
                removed.discard(name)
                store.set_staple_removed(name, removed=False)
            item = find(name)
            if item is None:
                item = InventoryItem(
                    id=_new_id(), name=name, display_name=ch.display_name or ch.name.strip(),
                    category=ch.category or STAPLE_CATEGORIES.get(name, "other"),
                    qty_level=ch.qty_level or "some", location=ch.location or "fridge",
                    confidence=1.0, uncertain=False, use_soon=bool(ch.use_soon),
                    is_staple=is_staple(name), source=source, updated_at=now,
                )
                stored.append(item)
            else:
                for field in ("display_name", "category", "location", "qty_level", "use_soon"):
                    if (value := getattr(ch, field)) is not None:
                        setattr(item, field, value)
            touch(item)
            continue

        item = find(name)
        if item is None:
            continue
        if ch.op == "remove" or (ch.op == "set_qty" and ch.qty_level is None):
            drop(item)
        elif ch.op == "set_qty":
            item.qty_level = ch.qty_level
            touch(item)
        elif ch.op == "set_use_soon":
            item.use_soon = True if ch.use_soon is None else ch.use_soon
            touch(item)
        elif ch.op == "rename":
            new = normalize(ch.new_name or "")
            if not new:
                continue
            existing = next((i for i in stored if i.name == new and i is not item), None)
            if existing is not None:  # renamed onto an item we already have: keep one
                existing.use_soon = existing.use_soon or item.use_soon
                drop(item)
                item = existing
            else:
                item.name = new
                item.is_staple = is_staple(new)
            item.display_name = ch.display_name or (ch.new_name or "").strip()
            touch(item)

    store.save_inventory(stored)
    return get_inventory(store)


def merge_recognized(store: Store, items: list[InventoryItem]) -> list[InventoryItem]:
    """Merge recognition results into the stored inventory and return the full inventory.

    New names are added. For a name already stored: qty_level, confidence and uncertain are updated,
    but use_soon is never cleared and items with source="manual" are left alone.
    Recognition never removes anything.
    """
    # Two photos of the same item: keep the more confident reading.
    incoming: dict[str, InventoryItem] = {}
    for rec in items:
        name = normalize(rec.name)
        if not name:
            continue
        prev = incoming.get(name)
        if prev is None or rec.confidence > prev.confidence:
            incoming[name] = rec.model_copy(update={"name": name, "use_soon": rec.use_soon or (prev is not None and prev.use_soon)})
        else:
            prev.use_soon = prev.use_soon or rec.use_soon

    stored = store.load_inventory()
    by_name = {i.name: i for i in stored}
    staples = all_staples(store)
    for name, rec in incoming.items():
        old = by_name.get(name)
        if old is None:
            stored.append(rec.model_copy(update={"is_staple": name in staples}))
        elif old.source != "manual":
            old.qty_level, old.confidence, old.uncertain = rec.qty_level, rec.confidence, rec.uncertain
            old.use_soon = old.use_soon or rec.use_soon
            old.updated_at = rec.updated_at
    store.save_inventory(stored)
    return get_inventory(store)


def _item_text(i: InventoryItem) -> str:
    flags = [i.qty_level]
    if i.use_soon:
        flags.append("USE SOON")
    if i.uncertain:
        flags.append("UNCERTAIN")
    return f"{i.name} ({', '.join(flags)})"


def inventory_summary(items: list[InventoryItem], scan_state: ScanState) -> str:
    """Compact inventory text for prompts: one line per place, then the staples.

    Each place says when it was scanned or "NOT SCANNED". Items read "name (qty[, USE SOON][, UNCERTAIN])".
    """
    lines = []
    for loc in LOCATIONS:
        when = scan_state.scanned.get(loc)
        if when is not None:
            header = f"{loc} (scanned {when:%Y-%m-%d})"
        elif loc == "freezer" and scan_state.freezer_declined:
            header = f"{loc} (NOT SCANNED, user declined)"
        else:
            header = f"{loc} (NOT SCANNED)"
        here = [i for i in items if i.location == loc and i.source != "staple"]
        here.sort(key=lambda i: (not i.uncertain, not i.use_soon))
        body = ", ".join(_item_text(i) for i in here) if here else "nothing"
        lines.append(f"{header}: {body}")
    staples = [i.name for i in items if i.source == "staple"]
    lines.append("staples (assumed present): " + (", ".join(staples) if staples else "none"))
    return "\n".join(lines)
