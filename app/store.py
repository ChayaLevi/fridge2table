"""SQLite persistence: inventory, preferences, removed and added staples, scan state, chat sessions.

One `Store` per database file. Rows hold the Pydantic models as JSON, so the
schema stays small and the models in `app/models.py` remain the source of truth.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter

from app import config
from app.models import InventoryItem, Location, Preference, Recipe, ScanState

_SCHEMA = """
CREATE TABLE IF NOT EXISTS inventory (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS preferences (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS staples_state (
    name TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS custom_staples (
    name TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS scan_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    messages TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recipes (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
"""

_TABLES = ("inventory", "preferences", "staples_state", "custom_staples", "scan_state", "sessions", "recipes")


class Store:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path is not None else config.DB_PATH
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        # The connection is shared across threads (FastAPI handlers, pydantic-ai worker threads); the
        # sqlite3 module serializes access to one connection, so this is safe for a single process.
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    # inventory (stored items only; staples are added by app/tools/inventory.py)

    def load_inventory(self) -> list[InventoryItem]:
        rows = self._conn.execute("SELECT data FROM inventory ORDER BY rowid").fetchall()
        return [InventoryItem.model_validate_json(r[0]) for r in rows]

    def save_inventory(self, items: list[InventoryItem]) -> None:
        """Replace the whole stored inventory."""
        with self._conn:
            self._conn.execute("DELETE FROM inventory")
            self._conn.executemany(
                "INSERT INTO inventory (id, data) VALUES (?, ?)",
                [(i.id, i.model_dump_json()) for i in items],
            )

    # preferences

    def load_preferences(self) -> list[Preference]:
        rows = self._conn.execute("SELECT data FROM preferences ORDER BY rowid").fetchall()
        return [Preference.model_validate_json(r[0]) for r in rows]

    def add_preference(self, pref: Preference) -> None:
        """Insert or replace by id. Deduplication is the job of save_preference (T1.7)."""
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO preferences (id, data) VALUES (?, ?)",
                (pref.id, pref.model_dump_json()),
            )

    # staples the user removed

    def load_removed_staples(self) -> set[str]:
        rows = self._conn.execute("SELECT name FROM staples_state").fetchall()
        return {r[0] for r in rows}

    def set_staple_removed(self, name: str, removed: bool = True) -> None:
        with self._conn:
            if removed:
                self._conn.execute("INSERT OR IGNORE INTO staples_state (name) VALUES (?)", (name,))
            else:
                self._conn.execute("DELETE FROM staples_state WHERE name = ?", (name,))

    # staples the user added (beyond data/staples.json), in the order added

    def load_custom_staples(self) -> list[str]:
        rows = self._conn.execute("SELECT name FROM custom_staples ORDER BY rowid").fetchall()
        return [r[0] for r in rows]

    def set_custom_staple(self, name: str, present: bool = True) -> None:
        with self._conn:
            if present:
                self._conn.execute("INSERT OR IGNORE INTO custom_staples (name) VALUES (?)", (name,))
            else:
                self._conn.execute("DELETE FROM custom_staples WHERE name = ?", (name,))

    # recipes (every recipe a tool returned, by id, so steps can be generated later for a card)

    def save_recipe(self, recipe: Recipe) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO recipes (id, data) VALUES (?, ?)", (recipe.id, recipe.model_dump_json()),
            )

    def load_recipe(self, recipe_id: str) -> Recipe | None:
        row = self._conn.execute("SELECT data FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
        return Recipe.model_validate_json(row[0]) if row else None

    # scan state

    def load_scan_state(self) -> ScanState:
        row = self._conn.execute("SELECT data FROM scan_state WHERE id = 1").fetchone()
        if row is None:
            return ScanState(scanned={})
        return ScanState.model_validate_json(row[0])

    def _save_scan_state(self, state: ScanState) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO scan_state (id, data) VALUES (1, ?)",
                (state.model_dump_json(),),
            )

    def mark_scanned(self, location: Location, when: datetime | None = None) -> None:
        state = self.load_scan_state()
        state.scanned[location] = when or datetime.now()
        self._save_scan_state(state)

    def set_freezer_declined(self, declined: bool = True) -> None:
        state = self.load_scan_state()
        state.freezer_declined = declined
        self._save_scan_state(state)

    # chat sessions (Pydantic AI's serializable message history)

    def load_session_messages(self, session_id: str) -> list[ModelMessage]:
        row = self._conn.execute(
            "SELECT messages FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return []
        return ModelMessagesTypeAdapter.validate_json(row[0])

    def save_session_messages(self, session_id: str, messages: list[ModelMessage]) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO sessions (session_id, messages) VALUES (?, ?)",
                (session_id, ModelMessagesTypeAdapter.dump_json(messages).decode()),
            )

    # tests and demo seeding

    def reset_all(self) -> None:
        with self._conn:
            for table in _TABLES:
                self._conn.execute(f"DELETE FROM {table}")
