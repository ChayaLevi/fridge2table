"""Household preferences: save (normalized, deduped), read, and summarize for prompts.

A preference is a short text ("kids dislike eggplant") plus the canonical ingredients to avoid.
The checks in `checks.py` use `avoid`; the text is context for the LLMs.

Dedupe rules in save_preference:
- same text (case/space-insensitive) as an existing preference -> its avoid list is extended, no new row;
- avoid items already avoided by an existing preference are dropped from the new one;
- if that leaves nothing new (the new one only repeats what is avoided), no new row: the existing
  preference that covers it is returned.
"""

import uuid
from datetime import datetime

from app.models import Preference
from app.store import Store
from app.tools.normalize import normalize


def _text_key(text: str) -> str:
    return " ".join(text.lower().split())


def _normalize_avoid(avoid: list[str]) -> list[str]:
    out: list[str] = []
    for name in avoid:
        canon = normalize(name)
        if canon and canon not in out:
            out.append(canon)
    return out


def save_preference(store: Store, text: str, avoid: list[str] | None = None) -> Preference:
    """Store a preference and return it (or the existing preference it duplicates)."""
    text = " ".join(text.split())
    avoid = _normalize_avoid(avoid or [])
    existing = store.load_preferences()

    for pref in existing:
        if _text_key(pref.text) == _text_key(text):
            extra = [a for a in avoid if a not in pref.avoid]
            if extra:
                pref = pref.model_copy(update={"avoid": pref.avoid + extra})
                store.add_preference(pref)
            return pref

    if avoid:
        covered = {a for p in existing for a in p.avoid}
        new_avoid = [a for a in avoid if a not in covered]
        if not new_avoid:
            return next(p for p in existing if avoid[0] in p.avoid)
        avoid = new_avoid
    elif not text:
        raise ValueError("a preference needs a text or an avoid list")

    pref = Preference(id=uuid.uuid4().hex, text=text or f"avoid {', '.join(avoid)}", avoid=avoid,
                      created_at=datetime.now())
    store.add_preference(pref)
    return pref


def get_preferences(store: Store) -> list[Preference]:
    return store.load_preferences()


def format_preferences(prefs: list[Preference]) -> str:
    """One line per preference, `text (avoid: a, b)`; `none` when there are none."""
    if not prefs:
        return "none"
    return "\n".join(
        f"- {p.text} (avoid: {', '.join(p.avoid)})" if p.avoid else f"- {p.text}" for p in prefs
    )


def preferences_summary(store: Store) -> str:
    """Compact text for prompts."""
    return format_preferences(get_preferences(store))
