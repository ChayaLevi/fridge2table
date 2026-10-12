"""Canonical ingredient names. All comparisons in the app go through normalize()."""

import json
import re
from functools import lru_cache

from app.config import SYNONYMS_PATH

STRIP_WORDS = {
    "fresh", "organic", "large", "small", "chopped", "sliced", "diced", "minced", "boneless", "skinless",
}
# Words and phrases that must never be singularized.
NO_SINGULAR = {"asparagus", "hummus", "couscous", "molasses", "swiss chard", "citrus"}
# "-ies" words whose singular is not "-y".
IES_EXCEPTIONS = {"cookies": "cookie", "brownies": "brownie", "smoothies": "smoothie", "veggies": "veggie"}
# "-ves" words whose singular is "-f"; every other "-ves" word just loses the "s" (olives, cloves).
VES_TO_F = {"leaves": "leaf", "loaves": "loaf", "halves": "half", "calves": "calf"}

_QUANTITY_RE = re.compile(
    r"^\s*\d+([.,/]\d+)?\s*(x|g|kg|ml|l|oz|lb|lbs|cups?|tbsp|tsp|pcs|pieces?)?\b\s*(of\s+)?"
)


@lru_cache(maxsize=1)
def _synonyms() -> dict[str, str]:
    return json.loads(SYNONYMS_PATH.read_text(encoding="utf-8"))


def _singular_word(w: str) -> str:
    if w in NO_SINGULAR or len(w) <= 3:
        return w
    if w in IES_EXCEPTIONS:
        return IES_EXCEPTIONS[w]
    if w in VES_TO_F:
        return VES_TO_F[w]
    if w.endswith("ies"):
        return w[:-1] if len(w) <= 4 else w[:-3] + "y"
    if w.endswith("oes"):
        return w[:-2]
    if w.endswith(("sses", "ches", "shes", "xes")):
        return w[:-2]
    if w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def _singular(phrase: str) -> str:
    """Singularize the last word of a phrase."""
    if phrase in NO_SINGULAR:
        return phrase
    head, _, last = phrase.rpartition(" ")
    last = _singular_word(last)
    return f"{head} {last}" if head else last


def _clean(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"\([^)]*\)", " ", s)  # drop parentheticals
    s = _QUANTITY_RE.sub("", s)
    s = re.sub(r"[^a-z\- ]", " ", s)
    return re.sub(r"\s+", " ", s).strip(" -")


def _resolve(s: str) -> tuple[str, bool]:
    """Singularize, then apply synonyms. Returns (name, found_in_synonyms)."""
    syn = _synonyms()
    if s in syn:
        return syn[s], True
    sing = _singular(s)
    if sing in syn:
        return syn[sing], True
    return sing, False


def normalize(name: str) -> str:
    s = _clean(name)
    if not s:
        return ""
    # Synonyms first on the full phrase, so "minced beef" -> "ground beef" before "minced" is stripped.
    result, hit = _resolve(s)
    if hit:
        return result
    stripped = " ".join(w for w in s.split() if w not in STRIP_WORDS)
    if not stripped:
        return result
    return _resolve(stripped)[0]


def same_ingredient(a: str, b: str) -> bool:
    na, nb = normalize(a), normalize(b)
    return bool(na) and na == nb
