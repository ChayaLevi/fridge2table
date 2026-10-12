"""Canonical ingredient names. All comparisons in the app go through normalize().

Pipeline: clean (ASCII-fold, lowercase, drop parentheticals, "tomatoes, canned" -> "canned tomatoes")
-> look up the full phrase -> strip quantities ("2", "500g", "a can of") -> look up
-> strip descriptor words ("fresh", "chopped", ...) -> look up -> singularize the last word.

Lookups go through one index built from data/synonyms.json (keys and targets) and
data/staples.json. The index is keyed by `_key()` (hyphens as spaces, last word singular), so
"chili flake", "chili-flakes" and "chilli flakes" all reach the canonical "chili flakes".
Phrases in the index are matched before descriptor words are stripped, which protects names
like "minced beef" and "frozen yogurt". normalize() is idempotent.
"""

import json
import re
import unicodedata
from functools import lru_cache

from app.config import STAPLES_PATH, SYNONYMS_PATH

# Descriptor words dropped when the full phrase is not a known name.
STRIP_WORDS = {
    "fresh", "organic", "large", "small", "chopped", "sliced", "diced", "minced", "boneless", "skinless",
    "medium", "extra", "extra-large", "ripe", "raw", "frozen", "peeled", "grated", "shredded",
}
# Words that are never singularized.
NO_SINGULAR = {"asparagus", "hummus", "couscous", "molasses", "citrus", "brussels", "swiss"}
# Plurals the suffix rules get wrong.
IRREGULAR = {
    "leaves": "leaf", "loaves": "loaf", "halves": "half", "calves": "calf", "knives": "knife",
    "cookies": "cookie", "brownies": "brownie", "smoothies": "smoothie", "veggies": "veggie",
    "pierogies": "pierogi", "chilies": "chili", "chillies": "chilli",
    "quiches": "quiche", "brioches": "brioche", "ganaches": "ganache",
}
# Quantity words: dropped only at the start of the name ("a dozen eggs", "some milk").
NUMBER_WORDS = {
    "a", "an", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "dozen", "half", "quarter", "couple", "few", "several", "some",
}
# Units: dropped only right after a quantity or right before "of" ("3 cloves garlic", "can of
# tomatoes"), so "cloves" alone (the spice) and "white container" survive.
UNITS = {
    "x", "g", "gr", "gram", "kg", "kilo", "kilogram", "mg", "ml", "cl", "l", "liter", "litre",
    "oz", "ounce", "lb", "lbs", "pound", "cup", "tbsp", "tablespoon", "tsp", "teaspoon",
    "pinch", "dash", "handful", "bunch", "can", "tin", "jar", "bag", "pack", "packet", "box",
    "bottle", "carton", "tub", "pot", "container", "clove", "slice", "piece", "pc", "pcs",
    "head", "stalk", "sprig", "stick", "loaf", "fillet",
}
_NUMBER_TOKEN = re.compile(r"\d+[a-z]*|x\d+")  # "2", "500g", "1l", "12pcs", "x12"


def _singular_word(w: str) -> str:
    if len(w) <= 3 or w in NO_SINGULAR or not w.endswith("s"):
        return w
    if w in IRREGULAR:
        return IRREGULAR[w]
    if w.endswith("ies"):
        return w[:-1] if len(w) <= 4 else w[:-3] + "y"  # pies -> pie, berries -> berry
    if w.endswith(("oes", "sses", "ches", "shes", "xes")):
        return w[:-2]
    if w.endswith(("ss", "us")):
        return w
    return w[:-1]  # carrots, olives, cloves, kiwis


def _key(phrase: str) -> str:
    """Lookup form: hyphens as spaces, last word singular."""
    words = phrase.replace("-", " ").split()
    if not words:
        return ""
    words[-1] = _singular_word(words[-1])
    return " ".join(words)


@lru_cache(maxsize=1)
def _index() -> dict[str, str]:
    """_key(variant) -> canonical name, for every synonym key, synonym target and staple."""
    synonyms: dict[str, str] = json.loads(SYNONYMS_PATH.read_text(encoding="utf-8"))
    staples: list[str] = json.loads(STAPLES_PATH.read_text(encoding="utf-8"))
    pairs = [(c, c) for c in [*synonyms.values(), *staples]] + list(synonyms.items())
    index: dict[str, str] = {}
    for variant, canonical in pairs:
        k = _key(" ".join(_tokens(variant)))
        if index.setdefault(k, canonical) != canonical:
            raise ValueError(f"'{variant}' maps to both '{index[k]}' and '{canonical}'")
    return index


def _lookup(tokens: list[str]) -> str | None:
    return _index().get(_key(" ".join(tokens)))


def _tokens(name: str) -> list[str]:
    s = unicodedata.normalize("NFKD", name).replace("⁄", "/")  # "½" -> "1⁄2" -> "1/2"
    s = s.encode("ascii", "ignore").decode().lower()  # "jalapeño" -> "jalapeno"
    s = re.sub(r"\([^)]*\)", " ", s)  # drop parentheticals: "milk (2%)"
    parts = s.split(",")
    if len(parts) > 1:  # "tomatoes, canned" -> "canned tomatoes"
        s = " ".join(parts[1:] + parts[:1])
    s = s.replace("&", " and ").replace("'", "")
    s = re.sub(r"[^a-z0-9\- ]", " ", s)
    return [t for t in (t.strip("-") for t in s.split()) if t]


def _is_unit(t: str) -> bool:
    return t in UNITS or _singular_word(t) in UNITS


def _strip_quantities(tokens: list[str]) -> list[str]:
    out: list[str] = []
    after_qty = False  # previous token was a dropped quantity or unit
    for i, t in enumerate(tokens):
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if _NUMBER_TOKEN.fullmatch(t) or (t in NUMBER_WORDS and not out):
            after_qty = True
        elif _is_unit(t) and (after_qty or nxt == "of"):
            after_qty = True
        elif t == "of" and after_qty:
            after_qty = False
        else:
            out.append(t)
            after_qty = False
    # "2 cloves": everything looked like a quantity, so keep the words and drop only the numbers.
    return out or [t for t in tokens if not _NUMBER_TOKEN.fullmatch(t)]


def normalize(name: str) -> str:
    """Canonical ingredient name: lowercase, singular, no quantities or descriptors, synonyms resolved."""
    tokens = _tokens(name)
    if not tokens:
        return ""
    if hit := _lookup(tokens):  # "half & half", "minced beef"
        return hit
    tokens = _strip_quantities(tokens)
    if hit := _lookup(tokens):
        return hit
    kept = [t for t in tokens if t not in STRIP_WORDS]
    if kept and kept != tokens:
        if hit := _lookup(kept):
            return hit
        tokens = kept
    return _key(" ".join(tokens))


def same_ingredient(a: str, b: str) -> bool:
    na = normalize(a)
    return bool(na) and na == normalize(b)
