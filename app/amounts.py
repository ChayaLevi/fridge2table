"""Exact amounts (T6.3): optional, entered only by the user; recognition never sets them.

Deterministic helpers, no LLM: parse free text ("300 g", "1.5 kg", "a handful" -> None), convert to base
units (g, ml, pcs, pack), format for display, pick a default unit for a category, and split an amount off
an item typed in the panel's add field ("milk 2 l", "6 eggs"). The checks stay presence-based; T6.1
("I made it") and T6.4 ("Bought it") will subtract / add with these helpers when the units are compatible.
"""

import re
from typing import Literal

Unit = Literal["pcs", "g", "kg", "ml", "l", "pack"]
UNITS: tuple[Unit, ...] = ("pcs", "g", "kg", "ml", "l", "pack")
BaseUnit = Literal["pcs", "g", "ml", "pack"]

_TO_BASE: dict[str, tuple[BaseUnit, float]] = {
    "pcs": ("pcs", 1), "g": ("g", 1), "kg": ("g", 1000), "ml": ("ml", 1), "l": ("ml", 1000), "pack": ("pack", 1),
}

# Words people and recipes write for each unit (lowercase).
_UNIT_WORDS: dict[str, Unit] = {
    **dict.fromkeys(["pc", "pcs", "piece", "pieces"], "pcs"),
    **dict.fromkeys(["g", "gr", "grs", "gram", "grams", "gramme", "grammes"], "g"),
    **dict.fromkeys(["kg", "kgs", "kilo", "kilos", "kilogram", "kilograms", "kilogramme", "kilogrammes"], "kg"),
    **dict.fromkeys(["ml", "milliliter", "milliliters", "millilitre", "millilitres"], "ml"),
    **dict.fromkeys(["l", "lt", "ltr", "liter", "liters", "litre", "litres"], "l"),
    **dict.fromkeys(["pack", "packs", "packet", "packets", "package", "packages", "pkg"], "pack"),
}

# Liquids filed under another category (milk is dairy): their default unit is litres.
_LIQUIDS = {"milk", "cream", "heavy cream", "buttermilk", "juice", "orange juice", "apple juice", "kefir"}

_NUM = r"(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?|[.,]\d+)"
_UNIT_RX = "|".join(sorted(map(re.escape, _UNIT_WORDS), key=len, reverse=True))
# number, optional unit; the unit must end at a word boundary ("2 large" has no unit, "2 lemons" is not litres)
_AMOUNT = re.compile(rf"(?P<num>{_NUM})\s*(?:(?P<unit>{_UNIT_RX})\b\.?)?", re.I)
_ARTICLE = re.compile(rf"(?:a|an|one)\s+(?P<unit>{_UNIT_RX})\b\.?", re.I)
# size words after a bare count still mean pieces: "5 large" = 5 pcs
_SIZE = re.compile(r"^(?:large|medium|small|big|whole|extra[- ]large)\b", re.I)
_HEDGE = re.compile(r"^(?:about|approx\.?|approximately|around|roughly|~)\s*", re.I)


def _number(text: str) -> float:
    text = text.strip()
    text = text.replace(",", "") if re.fullmatch(r"\d+,\d{3}", text) else text.replace(",", ".")  # 1,000 g / 1,5 kg
    if " " in text:  # "1 1/2"
        whole, frac = text.split(None, 1)
        return float(whole) + _number(frac)
    if "/" in text:
        top, bottom = text.split("/")
        return float(top) / float(bottom)
    return float(text)


def _match_amount(text: str) -> tuple[re.Match | None, float, Unit] | None:
    """The amount at the start of `text`: (match, value, unit), or None."""
    if m := _ARTICLE.match(text):
        return m, 1.0, _UNIT_WORDS[m["unit"].lower()]
    if not (m := _AMOUNT.match(text)):
        return None
    try:
        value = _number(m["num"])
    except (ValueError, ZeroDivisionError):
        return None
    if value <= 0:
        return None
    return m, value, _UNIT_WORDS[m["unit"].lower()] if m["unit"] else "pcs"


def parse_amount(text: str) -> tuple[float, Unit] | None:
    """Free-text amount -> (amount, unit), or None when it is not a plain amount in our units.

    "300 g" -> (300, "g"); "1.5 kg"; "500ml"; "2 l"; "2" -> (2, "pcs"); "1/2 l" -> (0.5, "l");
    "about 300 g"; "300 g (2 cups)" -> (300, "g"); "5 large" -> (5, "pcs").
    "a handful", "2 tbsp", "1 lb", "to taste" -> None.
    """
    text = _HEDGE.sub("", (text or "").strip())
    found = _match_amount(text)
    if found is None:
        return None
    m, value, unit = found
    rest = text[m.end():].strip()
    if unit == "pcs" and (size := _SIZE.match(rest)):
        rest = rest[size.end():].strip()
    if rest and rest[0] not in "(,;":  # "2 tbsp", "2 cloves": a unit we do not track
        return None
    return value, unit


def to_base(amount: float, unit: Unit) -> tuple[float, BaseUnit]:
    """kg -> g x1000, l -> ml x1000; g, ml, pcs and pack stay as they are."""
    base, factor = _TO_BASE[unit]
    return amount * factor, base


def same_kind(a: Unit, b: Unit) -> bool:
    """True when the two units convert to the same base unit (g and kg, ml and l)."""
    return _TO_BASE[a][0] == _TO_BASE[b][0]


def _num_text(x: float) -> str:
    return f"{round(x, 2):g}"


def format_amount(amount: float | None, unit: Unit | None) -> str:
    """For display: 1500 g -> "1.5 kg", 0.5 l -> "500 ml", 6 pcs -> "6 pcs", 2 pack -> "2 packs". None -> ""."""
    if amount is None or unit is None:
        return ""
    value, base = to_base(amount, unit)
    if base == "g":
        return f"{_num_text(value / 1000)} kg" if value >= 1000 else f"{_num_text(value)} g"
    if base == "ml":
        return f"{_num_text(value / 1000)} l" if value >= 1000 else f"{_num_text(value)} ml"
    if base == "pack":
        return f"{_num_text(value)} pack" + ("" if value == 1 else "s")
    return f"{_num_text(value)} pcs"


def amount_short(amount: float, unit: Unit) -> str:
    """Like format_amount, but a count is a bare number: "4" for 4 pcs, "300 g", "1.5 kg" (for have / need)."""
    text = format_amount(amount, unit)
    return text.removesuffix(" pcs")


def sum_base(amounts: list[tuple[float, Unit]]) -> tuple[float, BaseUnit] | None:
    """The amounts added up in their base unit ("3" + "2" eggs -> (5, "pcs")); None if empty or of mixed kinds."""
    total, base = 0.0, None
    for amount, unit in amounts:
        value, b = to_base(amount, unit)
        if base is not None and b != base:
            return None
        total, base = total + value, b
    return (total, base) if base is not None else None


def default_unit(category: str, name: str = "") -> Unit:
    """The unit chip preselected for an item: eggs, fruit, vegetables by the piece; meat, cheese, grains,
    pasta, baking by weight; drinks and milk in litres, sauces in ml; anything else by the piece."""
    if name in _LIQUIDS or category == "drink":
        return "l"
    if category == "sauce":
        return "ml"
    if category in ("meat", "fish", "dairy", "grain", "pasta", "baking"):
        return "g"
    return "pcs"


def split_amount(text: str) -> tuple[str, float, Unit | None] | None:
    """An item typed with an amount: "milk 2 l" -> ("milk", 2, "l"), "6 eggs" -> ("eggs", 6, None),
    "2 liters of milk" -> ("milk", 2, "l"). The unit is None when none was typed (the caller picks the
    category default). None when the text has no amount at its start or end.
    """
    text = " ".join((text or "").split())
    # amount first: "6 eggs", "500g flour", "2 l of milk", "a pack of butter"
    found = _match_amount(text)
    if found is not None:
        m, value, unit = found
        name = re.sub(r"^of\s+", "", text[m.end():].strip(), flags=re.I)
        typed_unit = m.re is _ARTICLE or bool(m["unit"])
        # a bare number needs a space after it: "6 eggs" yes, "7up" no
        if name and (typed_unit or text[m.end("num"):m.end("num") + 1] == " "):
            return name, value, unit if typed_unit else None
    # amount last: "milk 2 l", "milk 2l", "eggs 6"
    parts = text.rsplit(" ", 2)
    for k in (2, 1):
        if len(parts) <= k:
            continue
        tail = " ".join(parts[-k:])
        if (m := _AMOUNT.fullmatch(tail)) and (parsed := parse_amount(tail)):
            return " ".join(parts[:-k]), parsed[0], parsed[1] if m["unit"] else None
    return None
