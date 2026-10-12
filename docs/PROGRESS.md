# Progress

Updated by Claude Code at the end of every task (see "Session protocol" in `CLAUDE.md`). Newest log entry first.

## Status

- [x] T0.1 Scaffold
- [x] T0.2 Schemas
- [x] T0.3 Static data
- [ ] T0.4 Model smoke test 🧑
- [~] T0.5 Eval set structure 🧑 (README done; waiting for the human's photos)
- [x] T1.1 Normalization
- [x] T1.2 Store
- [x] T1.3 Inventory tools
- [ ] T1.4 Recognition + vision eval 🧑
- [ ] T1.5 Checks
- [ ] T1.6 Recipes
- [ ] T1.7 Preferences
- [ ] T2.1 Agent
- [ ] T2.2 Output validator
- [ ] T2.3 Trace capture
- [ ] T2.4 Terminal chat
- [ ] T2.5 Scenario suite
- [ ] T3.1 API
- [ ] T3.2 Web page
- [ ] T3.3 First real-fridge run + internal demo 🧑
- [ ] T4.1 Proactive opening
- [ ] T4.2 Substitutions in Mode B
- [ ] T4.3 Preferences end to end
- [ ] T4.4 Trace UI polish
- [ ] T5.1 Vision model comparison
- [ ] T5.2 Latency
- [ ] T5.3 Real user run #1 + decision point 🧑
- [ ] P6 Fixes (+ T6.1, T6.2 if the decision point passed)
- [ ] P7 Freeze 🧑

## Next up

- **Next task: T1.5 Checks** (`app/tools/checks.py`; T1.4 needs photos, so it is skipped for now). Then T1.7, then T1.4/T1.6 with mocked models, then P2/P3.
- **Blocked on the human (do not wait for these, build with mocks):** API keys in `.env` (`GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`) for T0.4; eval photos in `eval/fridges/<household>_<place>/` (4-6 sets, >=2 fridge, >=2 pantry) for T0.5/T1.4.
- Deferred and to be done once keys exist: T0.4 smoke test (verify exact model IDs/format, replace provisional defaults in `app/config.py`), the real runs of T1.4 and T1.6, T2.5.
- State: 157 tests pass. `app/llm.py`, `app/agent.py` and `app/tools/{recognize,recipes,checks,preferences}.py` are still empty files.

## Current model settings

Only Chinese models (see `docs/PRODUCT.md` §9). All via the DeepSeek API (`DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL=https://api.deepseek.com`); model IDs still to be verified in T0.4.

- VISION_MODEL: `deepseek-v4-flash-vision-exp` (temporary; swap to Qwen3.8 Max once that license is approved; decided on our photos in T1.4/T5.1)
- AGENT_MODEL: `deepseek-v4-pro` (try `deepseek-v4-flash` only if turns are too slow, T5.2)
- RECIPE_MODEL: `deepseek-v4-flash`
- VISION_TILES: 1 (best value chosen in T1.4)

## Decisions and deviations from the plan

- Model defaults in `app/config.py` are provisional strings (`google-gla:gemini-3.5-flash`, `anthropic:claude-sonnet-5-5`); exact IDs/format are verified in T0.4. `.env.example` leaves `VISION_MODEL`/`AGENT_MODEL` empty per the plan.
- Extras beyond the plan (small): `.gitignore`, `pytest.ini` (asyncio_mode=auto), `httpx` dev dependency (needed by FastAPI TestClient), `LOG_LEVEL`/`LOGFIRE_TOKEN` in `.env.example` (CLAUDE.md debugging aids).
- `data/synonyms.json` has 115 entries (112 + 3 added in the T1.1 redo) (flat map, no chains; a test enforces that targets are canonical). Ambiguous keys like bare `pepper` were left out on purpose.
- `InventoryChange` fields: `op`, `name`, optional `display_name`, `category`, `location`, `qty_level`, `use_soon`, `new_name`.
- 2026-10-12 (later): PLAN/PRODUCT were updated (pantry coverage). T0.2 re-done: added `ScanState`, `PANTRY_CATEGORIES`, `Ingredient.category`, `MissingReport.check_first`, `AgentReply.check_first`, extended category list. Tests now 6 pass. T0.1/T0.3 unaffected. T0.5 now asks for 4–6 sets (≥2 fridge, ≥2 pantry), folders `<household>_<place>`.
- Order change (user request, 2026-10-12): the human has no API keys/photos yet, so T0.4 is deferred and P1/P2 are built with mocked models. T0.4, the real run of T1.4 and T1.6, and T2.5 wait for keys/photos.
- Repo was not a git repo; `git init` done in T0.1.

## Open issues

(none yet)

## Log

### 2026-10-12 — Switch to DeepSeek models (docs change, no task)
- Why: the human replaced `CLAUDE.md`, `docs/PRODUCT.md` (§3, §9) and `docs/PLAN.md` (T0.1, T0.4, T1.4, T5.1, T5.2): only Chinese models are allowed; DeepSeek for now, Qwen3.8 Max for vision later.
- Changed: `.env.example` (now `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `QWEN_API_KEY`, `VISION_MODEL=deepseek-v4-flash-vision-exp`, `AGENT_MODEL=deepseek-v4-pro`, `RECIPE_MODEL=deepseek-v4-flash`, `VISION_TILES=1`; `GOOGLE_API_KEY`/`ANTHROPIC_API_KEY`/`OPENAI_API_KEY` removed); `app/config.py` (same defaults, new `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `QWEN_API_KEY`, `VISION_TILES`; `RECIPE_MODEL` no longer falls back to `AGENT_MODEL`).
- Model values are now bare model IDs (no `provider:` prefix); T0.4 `app/llm.py` builds the Pydantic AI model from ID + `DEEPSEEK_BASE_URL` + key.
- Next tasks must know: older entries in this file that mention Gemini/Claude, `GOOGLE_API_KEY`/`ANTHROPIC_API_KEY` or the `google-gla:`/`anthropic:` defaults are superseded by this entry. T1.4 now also needs tiling (`split_tiles`, `VISION_TILES`). The human now owes only `DEEPSEEK_API_KEY` for T0.4.
- Not changed: `pyproject.toml`/`uv.lock` still install the full `pydantic-ai` (which pulls the Google/Anthropic SDKs as optional extras); harmless, nothing uses them.
- Open issues: none.

**How to verify**
```
uv run pytest -q
uv run python -c "from app import config; print(config.VISION_MODEL, config.AGENT_MODEL, config.RECIPE_MODEL, config.DEEPSEEK_BASE_URL, config.VISION_TILES)"
```
Expected: `157 passed`; then `deepseek-v4-flash-vision-exp deepseek-v4-pro deepseek-v4-flash https://api.deepseek.com 1` (if your `.env` sets other values, those are printed instead).
Manual check: open `.env.example`; it names only DeepSeek/Qwen keys and the three DeepSeek model IDs.

### 2026-10-12 — T1.3 Inventory tools
- Built: `app/tools/inventory.py` (`staple_names`, `get_inventory`, `update_inventory`, `merge_recognized`, `inventory_summary`), `tests/test_inventory.py` (30 tests; 157 total pass).
- Deviation: every function takes the `Store` as its first argument (`get_inventory(store)`, `update_inventory(store, changes, source="chat")`, `merge_recognized(store, items)`); the plan's signatures had no store. The agent wrappers (T2.1) pass `ctx.deps.store`.
- Design:
  - Staples are virtual: `get_inventory` = stored items, then every staple not removed and not already stored (a stored item wins). Staples get location `pantry`, `qty_level="plenty"`, a category from `STAPLE_CATEGORIES`, id `staple:<name>`.
  - `update_inventory(..., source)`: `"manual"` for the side panel (T3.1 `PATCH /inventory`), `"chat"` for the agent. Every edit sets `confidence=1.0`, `uncertain=False`. `add` of an existing canonical name updates only the fields given; `add` of a removed staple restores it. `remove` of a staple records it in `staples_state`. **`set_qty` with `qty_level=None` means "below low" and removes the item** (QtyLevel has no "none" value). `set_qty`/`set_use_soon`/`rename` on a staple turns it into a stored item (`is_staple=True`). `rename` onto a name that already exists merges into that item. Unknown names in remove/set_qty/set_use_soon/rename are ignored silently.
  - `merge_recognized`: dedupes the incoming list by canonical name (higher confidence wins, `use_soon` OR'd), adds new names, updates `qty_level`/`confidence`/`uncertain` of existing ones, never clears `use_soon`, skips `source="manual"` items, never removes.
  - `inventory_summary`: one line per place, `fridge (scanned 2026-10-12): ...` or `pantry (NOT SCANNED): ...` (freezer: `NOT SCANNED, user declined`), items as `name (qty[, USE SOON][, UNCERTAIN])`, uncertain then use-soon first; last line lists the staples. 60 items fit under 1,500 characters (tested).
- Next tasks must know: T1.5 checks can use `staple_names()` and `get_inventory()` (staples already appear as items with `is_staple=True`, removed ones are absent). T1.4 should call `merge_recognized(store, items)` and then `mark_scanned`.
- Open issues: none.

**How to verify**
```
uv run pytest -q
uv run pytest tests/test_inventory.py -q
uv run python -c "from app.store import Store; from app.models import InventoryChange as C; from app.tools.inventory import update_inventory, inventory_summary; s=Store(':memory:'); s.mark_scanned('fridge'); inv=update_inventory(s,[C(op='add',name='Fresh Scallions'),C(op='add',name='spinach',use_soon=True,qty_level='low'),C(op='remove',name='soy sauce')]); print(inventory_summary(inv, s.load_scan_state()))"
```
Expected: `157 passed`; then `30 passed`; then four lines: `fridge (scanned <today>): spinach (low, USE SOON), green onion (some)`, `freezer (NOT SCANNED): nothing`, `pantry (NOT SCANNED): nothing`, and a staples line without `soy sauce`.
Manual check: in `uv run python`, create `s = Store(':memory:')`, store an item with `source="manual"` via `update_inventory(s, [InventoryChange(op="add", name="cheddar", qty_level="plenty")], source="manual")`, then call `merge_recognized` with a cheddar item at `qty_level="low"`; `get_inventory(s)` still shows cheddar as `plenty`.

### 2026-10-12 — T1.2 Store
- Built: `app/store.py` (class `Store`), `tests/test_store.py` (8 tests; 127 total pass).
- Design: one `Store(path=None)` per DB file (default `config.DB_PATH`, parent dir created), one SQLite connection, `close()`. Methods are the plan's functions: `load_inventory`, `save_inventory` (replaces all, keeps order), `load_preferences`, `add_preference(pref: Preference)` (insert-or-replace by id), `load_scan_state`, `mark_scanned(location, when=None)`, `set_freezer_declined(declined=True)`, `load_session_messages(session_id)`, `save_session_messages(session_id, messages)`, `reset_all`. Rows hold the Pydantic models as JSON; messages use `ModelMessagesTypeAdapter` (pydantic-ai 2.55.0).
- Deviation (small): added `load_removed_staples()` and `set_staple_removed(name, removed=True)` for the `staples_state` table; T1.3 needs them.
- Next tasks must know: the store holds only stored items. Staples are not in `inventory`; T1.3 `get_inventory` adds them. `add_preference` does not dedupe; `save_preference` (T1.7) does. `Deps` (T2.1) should hold a `Store` instance; tests should use `Store(tmp_path / "x.db")`.
- Open issues: none.

**How to verify**
```
uv run pytest -q
uv run pytest tests/test_store.py -q
uv run python -c "from app.store import Store; s=Store(':memory:'); s.mark_scanned('fridge'); print(s.load_scan_state())"
```
Expected: `127 passed`; then `8 passed`; then a line starting with `scanned={'fridge': datetime.datetime(`.
Manual check: in `uv run python`, create `Store("demo.db")`, call `mark_scanned("pantry")`, `close()`, open `Store("demo.db")` again and print `load_scan_state()`; pantry is still there. Delete `demo.db` afterwards.

### 2026-10-12 — T1.1 redone (normalization)
- Why: the user asked for T1.1 to be redone with a stronger model. The first version had matching bugs: the staple `chili flakes` became `chili flake` while `chilli flakes` became `chili flakes` (no match); accents were mangled (`jalapeños` -> `jalape os`); `chilies` -> `chily`, `quiches` -> `quich`, `kiwis` was not singularized; quantity words were not stripped (`a can of chickpeas`, `3 cloves garlic`, `a dozen eggs`, `milk 1l`); `all purpose flour` did not equal `all-purpose flour`.
- Built: rewrote `app/tools/normalize.py`; rewrote `tests/test_normalize.py` (113 tests: 108 cases plus data-wide checks); `data/synonyms.json` now has 115 entries (added `half and half` -> `half-and-half`, `froyo` -> `frozen yogurt`, `chilli pepper` -> `chili`).
- Design: one lookup index built from the synonym keys, synonym targets **and staples**, keyed hyphen- and plural-insensitively (`_key`: hyphens as spaces, last word singular). Pipeline: clean (ASCII-fold accents, drop parentheticals, `X, Y` -> `Y X`, `&` -> `and`) -> look up -> strip quantities (numbers like `500g`/`1l` anywhere; number words such as `a`/`some`/`dozen` only at the start; unit words only after a quantity or before `of`, so `cloves` alone and `white container` survive) -> look up -> strip descriptor words -> look up -> singularize the last word. Known names are matched before descriptors are stripped (`minced beef`, `frozen yogurt`).
- Deviation: the descriptor list is the plan's 10 words plus `medium`, `extra`, `extra-large`, `ripe`, `raw`, `frozen`, `peeled`, `grated`, `shredded` (so `frozen peas` in the freezer matches `peas` in a recipe). `whole`, `dried`, `ground` and `canned` are deliberately **not** stripped.
- Next tasks must know: canonical names from the data files (staples, synonym targets) are fixed points of `normalize`. Unknown names come back with hyphens as spaces (`stir fry sauce`). `_index()` raises `ValueError` if a data edit maps one variant to two canonical names (a test covers this). Note for T2.5 scenario 10: `spaghetti` normalizes to `pasta` (existing synonym), so check lists with `same_ingredient`, not by raw string.

**How to verify**
```
uv run pytest -q
uv run pytest tests/test_normalize.py -q
uv run python -c "from app.tools.normalize import normalize as n; print(n('Fresh Scallions'), '|', n('a can of chickpeas'), '|', n('chilli flakes'), '|', n('tomatoes, canned'))"
```
Expected: `119 passed`; then `113 passed`; then `green onion | chickpea | chili flakes | canned tomato`.
Manual check: in `uv run python`, run `from app.tools.normalize import same_ingredient` and then `same_ingredient("2 large eggs", "egg")` (True) and `same_ingredient("cloves", "garlic")` (False).

### 2026-10-12 — T0.5 (README part), T1.1
- Built: `eval/fridges/README.md`; `app/tools/normalize.py` (`normalize`, `same_ingredient`); `tests/test_normalize.py` (57 tests total pass).
- Design: synonyms are tried on the full phrase before adjectives are stripped (so "minced beef" -> "ground beef"), then again after stripping; only the last word is singularized; leading quantities ("2", "500 g of") and parentheticals are dropped. `normalize` is idempotent.
- Human still owes: photos in `eval/fridges/<household>_<place>/` (4-6 sets, >=2 fridge, >=2 pantry) and `.env` keys.

**How to verify**
```
uv run pytest tests/test_normalize.py -q
uv run python -c "from app.tools.normalize import normalize as n; print(n('Fresh Scallions'), n('chicken thighs'), n('tomatoes'))"
```
Expected (at the time): `51 passed`; then `green onion chicken tomato`.

### 2026-10-12 — T0.1, T0.2, T0.3
- Built: `pyproject.toml` (uv, deps per plan), folder layout from CLAUDE.md (empty modules), `.env.example`, `app/config.py`, `app/api.py` (`/health`), `app/models.py` (all §7 models + `InventoryChange`, `Constraints`), `data/staples.json` (15), `data/synonyms.json` (112), tests `tests/test_models.py`, `tests/test_data.py`, `tests/test_health.py` (5 pass).
- Next task must know: `config.py` exposes `VISION_MODEL`, `AGENT_MODEL`, `RECIPE_MODEL`, `DB_PATH`, `UNCERTAIN_THRESHOLD`, `STAPLES_PATH`, `SYNONYMS_PATH`. Run via `uv run` (a stray `VIRTUAL_ENV` warning from conda is harmless).
- Open issues: none.

**How to verify**
```
uv sync
uv run pytest -q
uv run uvicorn app.api:app --port 8000
curl localhost:8000/health
```
Expected (at the time): `5 passed`; the last command (in a second terminal) prints `{"ok":true}`.
Manual check: open http://localhost:8000/docs in a browser and call `GET /health` from there.
