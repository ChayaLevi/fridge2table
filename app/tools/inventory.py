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
from collections.abc import Iterable
from functools import lru_cache
from typing import Literal

from app.amounts import Unit, default_unit, format_amount, parse_amount, same_kind, split_amount, sum_base, to_base
from app.config import STAPLES_PATH
from app.models import (
    PANTRY_CATEGORIES, BoughtItem, InventoryChange, InventoryItem, Location, MadeChange, MadeResult, PackSize, Recipe,
    ScanState, Substitution,
)
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
    - confirm: the user says the item is right and still there (clears uncertain and not_seen).
    - add_staple: the name becomes a staple (assumed always present); a stored item with that name
      is replaced by the staple.
    - set_qty with qty_level=None means "below low": the item is removed.
    - set_amount sets the optional exact amount (unit None = the category's default unit); amount None or
      0 clears it. It never changes qty_level. add takes amount/unit too, or reads them from the name
      ("milk 2 l", "6 eggs"); an add without an amount keeps the stored one.
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
        item.source, item.confidence, item.uncertain, item.not_seen, item.updated_at = source, 1.0, False, False, now

    def set_amount(item: InventoryItem, amount: float | None, unit) -> None:
        if not amount:
            item.amount, item.unit = None, None
        else:
            item.amount, item.unit = amount, unit or default_unit(item.category, item.name)

    for ch in changes:
        if ch.op == "add" and ch.amount is None and (split := split_amount(ch.name)) is not None:
            typed, amount, unit = split
            ch = ch.model_copy(update={"name": typed, "amount": amount, "unit": unit})
        name = normalize(ch.name)
        if not name:
            continue
        if ch.op == "confirm":  # stored items only: a virtual staple needs no confirming
            if (item := next((i for i in stored if i.name == name), None)) is not None:
                touch(item)
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
            if ch.amount is not None:
                set_amount(item, ch.amount, ch.unit)
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
        elif ch.op == "set_amount":
            set_amount(item, ch.amount, ch.unit)
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
                if existing.amount is None:
                    existing.amount, existing.unit = item.amount, item.unit
                drop(item)
                item = existing
            else:
                item.name = new
                item.is_staple = is_staple(new)
            item.display_name = ch.display_name or (ch.new_name or "").strip()
            touch(item)

    store.save_inventory(stored)
    return get_inventory(store)


def merge_recognized(
    store: Store, items: list[InventoryItem], places: Iterable[Location] = (),
) -> list[InventoryItem]:
    """Merge recognition results into the stored inventory and return the full inventory.

    New names are added. For a name already stored: qty_level, confidence and uncertain are updated,
    but use_soon is never cleared and items with source="manual" are left alone.
    Recognition never removes anything. `places` are the places photographed in this scan: their
    stored items that were not recognized get not_seen=True (the user confirms or removes them);
    a recognized item gets not_seen=False.
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
        if old is not None:
            old.not_seen = False
    places = set(places)
    for item in stored:
        if item.location in places and not item.is_staple and item.name not in incoming:
            item.not_seen = True
    store.save_inventory(stored)
    return get_inventory(store)


def _item_text(i: InventoryItem) -> str:
    flags = [format_amount(i.amount, i.unit), i.qty_level] if i.amount is not None else [i.qty_level]
    if i.use_soon:
        flags.append("USE SOON")
    if i.uncertain:
        flags.append("UNCERTAIN")
    if i.not_seen:
        flags.append("NOT SEEN IN LAST PHOTO")
    return f"{i.name} ({', '.join(flags)})"


def inventory_summary(items: list[InventoryItem], scan_state: ScanState) -> str:
    """Compact inventory text for prompts: one line per place, then the staples.

    Each place says when it was scanned or "NOT SCANNED". Items read
    "name ([amount, ]qty[, USE SOON][, UNCERTAIN])", e.g. "milk (2 l, some)".
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
        here.sort(key=lambda i: (not i.uncertain, not i.not_seen, not i.use_soon))
        body = ", ".join(_item_text(i) for i in here) if here else "nothing"
        lines.append(f"{header}: {body}")
    staples = [i.name for i in items if i.source == "staple"]
    lines.append("staples (assumed present): " + (", ".join(staples) if staples else "none"))
    return "\n".join(lines)


# --- "Bought it" (T6.4) ------------------------------------------------------------------------------

# Common package sizes for the chips after "Bought": by canonical name first, then by category.
_SIZES_BY_NAME: dict[str, list[tuple[float, Unit]]] = {
    "egg": [(6, "pcs"), (12, "pcs"), (18, "pcs")],
    "milk": [(1, "l"), (2, "l")],
    "butter": [(250, "g"), (500, "g")],
    "cream": [(200, "ml"), (500, "ml")],
    "heavy cream": [(200, "ml"), (500, "ml")],
    "greek yogurt": [(500, "g"), (1, "kg")],
    "yogurt": [(500, "g"), (1, "kg")],
    "bread": [(1, "pack"), (2, "pack")],
    **dict.fromkeys(["sugar", "all-purpose flour", "rice", "pasta", "lasagna noodle", "spaghetti", "oats"],
                    [(500, "g"), (1, "kg")]),
    **dict.fromkeys(["cheddar", "mozzarella", "parmesan", "ricotta", "cottage cheese", "cream cheese", "feta"],
                    [(200, "g"), (500, "g")]),
}
_SIZES_BY_CATEGORY: dict[str, list[tuple[float, Unit]]] = {
    "egg": [(6, "pcs"), (12, "pcs"), (18, "pcs")],
    "meat": [(500, "g"), (1, "kg")],
    "fish": [(500, "g"), (1, "kg")],
    "dairy": [(200, "g"), (500, "g")],
    "vegetable": [(1, "pcs"), (3, "pcs"), (1, "kg")],
    "fruit": [(3, "pcs"), (6, "pcs"), (1, "kg")],
    "grain": [(500, "g"), (1, "kg")],
    "pasta": [(500, "g"), (1, "kg")],
    "baking": [(500, "g"), (1, "kg")],
    "canned": [(1, "pcs"), (2, "pcs"), (4, "pcs")],
    "sauce": [(250, "ml"), (500, "ml")],
    "condiment": [(250, "ml"), (500, "ml")],
    "drink": [(1, "l"), (2, "l")],
    "frozen": [(500, "g"), (1, "kg")],
}
_DEFAULT_SIZES: list[tuple[float, Unit]] = [(1, "pack"), (2, "pack")]


def package_sizes(name: str, category: str | None) -> list[PackSize]:
    """The 2-3 chips offered after "Bought" (a fixed table: by name, then by category, then 1 / 2 packs)."""
    name = normalize(name)
    sizes = _SIZES_BY_NAME.get(name) or _SIZES_BY_CATEGORY.get(category or "") or _DEFAULT_SIZES
    return [PackSize(amount=a, unit=u, text=format_amount(a, u)) for a, u in sizes]


def location_for(category: str | None) -> Location:
    """Where a bought item goes: pantry-type categories to the pantry, frozen to the freezer, else the fridge."""
    if category in PANTRY_CATEGORIES:
        return "pantry"
    if category == "frozen":
        return "freezer"
    return "fridge"


def _add_amount(base: tuple[float, Unit] | None, amount: float, unit: Unit) -> tuple[float, Unit]:
    """`amount unit` on top of `base`, in base's unit when the kinds match (1 kg + 500 g = 1.5 kg); else just the new one."""
    if base is None or not same_kind(base[1], unit):
        return amount, unit
    factor = to_base(1, base[1])[0]
    total = to_base(*base)[0] + to_base(amount, unit)[0]
    return round(total / factor, 6), base[1]


def mark_bought(
    store: Store, items: list[BoughtItem], source: Literal["chat", "manual"] = "manual",
) -> dict[str, tuple[float, Unit] | None]:
    """Put bought shopping-list items in the inventory; return, per name, the amount it had before.

    - A new item: added with qty_level plenty, the place by category (location_for), and an exact amount
      only if one was given.
    - An item already there: qty_level plenty, place kept. With an amount, it is added to the amount the
      item has (or to had_amount/had_unit, what it had before an earlier "Bought" cleared it) when the
      units are of the same kind, else it replaces it. Without an amount, the old exact amount is cleared:
      it no longer says what is there ("plenty only").
    - A staple (assumed always there) is ignored; a staple the user had removed comes back.
    The recipe's amount is never used.
    """
    inv = {i.name: i for i in get_inventory(store)}
    staples = set(all_staples(store))
    previous: dict[str, tuple[float, Unit] | None] = {}
    changes: list[InventoryChange] = []
    for b in items:
        name = normalize(b.name)
        if not name or name in previous:
            continue
        item = inv.get(name)
        previous[name] = (item.amount, item.unit) if item is not None and item.amount is not None else None
        if name in staples:
            if item is None:  # removed by the user: bring it back
                changes.append(InventoryChange(op="add_staple", name=name))
            continue
        if item is None:
            changes.append(InventoryChange(op="add", name=name, display_name=b.name.strip(),
                                           category=b.category or "other", location=location_for(b.category),
                                           qty_level="plenty"))
            if b.amount is not None:
                changes.append(InventoryChange(op="set_amount", name=name, amount=b.amount,
                                               unit=b.unit or default_unit(b.category or "other", name)))
            continue
        changes.append(InventoryChange(op="set_qty", name=name, qty_level="plenty"))
        if b.amount is None:
            changes.append(InventoryChange(op="set_amount", name=name, amount=None))
            continue
        unit = b.unit or item.unit or default_unit(item.category, name)
        base = previous[name] or ((b.had_amount, b.had_unit) if b.had_amount and b.had_unit else None)
        amount, unit = _add_amount(base, b.amount, unit)
        changes.append(InventoryChange(op="set_amount", name=name, amount=amount, unit=unit))
    if changes:
        update_inventory(store, changes, source=source)
    return previous


# --- "I made it" (T6.1) ------------------------------------------------------------------------------

_STEP_DOWN = {"plenty": "some", "some": "low", "low": None}  # None = removed


def mark_made(
    store: Store, recipe: Recipe, substitutions: Iterable[Substitution] = (),
    source: Literal["chat", "manual"] = "manual",
) -> MadeResult:
    """Deduct a cooked recipe's ingredients from the inventory; return what changed and an undo token.

    Per ingredient (amounts of one name added up; a substituted ingredient counts against its substitute):
    - The item has an exact amount and the recipe amounts parse to the same kind of unit (to_base):
      subtract, in the item's unit; at 0 or below the item is removed. qty_level is left as it is.
    - Otherwise qty_level goes one step down (plenty → some → low → removed); an exact amount that
      could not be subtracted (other units, "a handful") is left as it is.
    - Staples are never deducted; ingredients not in the inventory are skipped (optional ones too).
    The touched items are saved as they were, so undo_made(token) restores them exactly.
    """
    subs = {normalize(s.missing): normalize(s.use_instead) for s in substitutions}
    stored = {i.name: i for i in store.load_inventory()}
    need: dict[str, list[str]] = {}
    for ing in recipe.ingredients:
        name = normalize(ing.name)
        if name:
            need.setdefault(subs.get(name, name), []).append(ing.amount)

    changes: list[MadeChange] = []
    edits: list[InventoryChange] = []
    snapshot: list[InventoryItem] = []
    for name, amounts in need.items():
        item = stored.get(name)
        if item is None or item.is_staple:
            continue
        snapshot.append(item)
        parsed = [parse_amount(a) for a in amounts]
        total = sum_base(parsed) if all(p is not None for p in parsed) else None
        if item.amount is not None and item.unit is not None and total is not None \
                and total[1] == to_base(1, item.unit)[1]:
            before = format_amount(item.amount, item.unit)
            factor = to_base(1, item.unit)[0]
            left = round((to_base(item.amount, item.unit)[0] - total[0]) / factor, 6)
            if left <= 1e-9:
                edits.append(InventoryChange(op="remove", name=name))
                after = "removed"
            else:
                edits.append(InventoryChange(op="set_amount", name=name, amount=left, unit=item.unit))
                after = format_amount(left, item.unit)
        else:
            before, step = item.qty_level, _STEP_DOWN[item.qty_level]
            if step is None:
                edits.append(InventoryChange(op="remove", name=name))
                after = "removed"
            else:
                edits.append(InventoryChange(op="set_qty", name=name, qty_level=step))
                after = step
        changes.append(MadeChange(name=name, display_name=item.display_name, before=before, after=after))

    token = uuid.uuid4().hex
    store.save_undo(token, json.dumps([i.model_dump(mode="json", exclude={"amount_text"}) for i in snapshot]))
    if edits:
        update_inventory(store, edits, source=source)
    return MadeResult(changes=changes, token=token)


def bought_undo_points(store: Store, names: Iterable[str]) -> dict[str, str]:
    """Before "Bought": one undo token per item, so unticking one item puts it back as it was.

    The token's snapshot holds the item as it is now (it will become plenty), or, for an item not in the
    inventory yet, its name to remove again. Staples (assumed always there) get no token. Keys are
    canonical names.
    """
    stored = {i.name: i for i in store.load_inventory()}
    staples = set(all_staples(store))
    tokens: dict[str, str] = {}
    for raw in names:
        name = normalize(raw)
        if not name or name in tokens or name in staples:
            continue
        item = stored.get(name)
        data = {"items": [item.model_dump(mode="json", exclude={"amount_text"})] if item else [],
                "added": [] if item else [name]}
        tokens[name] = uuid.uuid4().hex
        store.save_undo(tokens[name], json.dumps(data))
    return tokens


def undo_made(store: Store, token: str) -> bool:
    """Put back the items an "I made it" or a "Bought" touched, exactly as they were; items the "Bought"
    added are removed again. False if the token is unknown or already used."""
    data = store.pop_undo(token)
    if data is None:
        return False
    raw = json.loads(data)
    # "I made it" saves a list of items; "Bought" saves {"items": [...], "added": [names]}.
    items, added = (raw, []) if isinstance(raw, list) else (raw["items"], raw["added"])
    snapshot = [InventoryItem.model_validate(d) for d in items]
    stored = [i for i in store.load_inventory() if i.name not in added]
    for old in snapshot:
        k = next((n for n, i in enumerate(stored) if i.id == old.id or i.name == old.name), None)
        if k is None:
            stored.append(old)
        else:
            stored[k] = old
    store.save_inventory(stored)
    return True
