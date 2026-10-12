# Progress

Updated by Claude Code at the end of every task (see "Session protocol" in `CLAUDE.md`). Newest log entry first.

## Status

- [x] T0.1 Scaffold
- [x] T0.2 Schemas
- [x] T0.3 Static data
- [ ] T0.4 Model smoke test 🧑
- [~] T0.5 Eval set structure 🧑 (README done; waiting for the human's photos)
- [x] T1.1 Normalization
- [ ] T1.2 Store
- [ ] T1.3 Inventory tools
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

- **Next task: T1.2 Store** (`app/store.py`; include `scan_state` table and its functions per the updated PLAN). Then T1.3, T1.5, T1.7, then T1.4/T1.6 with mocked models, then P2/P3.
- **Blocked on the human (do not wait for these, build with mocks):** API keys in `.env` (`GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`) for T0.4; eval photos in `eval/fridges/<household>_<place>/` (4-6 sets, >=2 fridge, >=2 pantry) for T0.5/T1.4.
- Deferred and to be done once keys exist: T0.4 smoke test (verify exact model IDs/format, replace provisional defaults in `app/config.py`), the real runs of T1.4 and T1.6, T2.5.
- State at hand-off: 57 tests pass, last commit is "T0.5 (README), T1.1". `app/store.py`, `app/llm.py`, `app/agent.py` and the other `app/tools/*` modules are still empty files.

## Current model settings

- VISION_MODEL: Gemini 3.5 Flash (to confirm in T5.1)
- AGENT_MODEL: Claude Sonnet 5.5

## Decisions and deviations from the plan

- Model defaults in `app/config.py` are provisional strings (`google-gla:gemini-3.5-flash`, `anthropic:claude-sonnet-5-5`); exact IDs/format are verified in T0.4. `.env.example` leaves `VISION_MODEL`/`AGENT_MODEL` empty per the plan.
- Extras beyond the plan (small): `.gitignore`, `pytest.ini` (asyncio_mode=auto), `httpx` dev dependency (needed by FastAPI TestClient), `LOG_LEVEL`/`LOGFIRE_TOKEN` in `.env.example` (CLAUDE.md debugging aids).
- `data/synonyms.json` has 112 entries (flat map, no chains; a test enforces that targets are canonical). Ambiguous keys like bare `pepper` were left out on purpose.
- `InventoryChange` fields: `op`, `name`, optional `display_name`, `category`, `location`, `qty_level`, `use_soon`, `new_name`.
- 2026-10-12 (later): PLAN/PRODUCT were updated (pantry coverage). T0.2 re-done: added `ScanState`, `PANTRY_CATEGORIES`, `Ingredient.category`, `MissingReport.check_first`, `AgentReply.check_first`, extended category list. Tests now 6 pass. T0.1/T0.3 unaffected. T0.5 now asks for 4–6 sets (≥2 fridge, ≥2 pantry), folders `<household>_<place>`.
- Order change (user request, 2026-10-12): the human has no API keys/photos yet, so T0.4 is deferred and P1/P2 are built with mocked models. T0.4, the real run of T1.4 and T1.6, and T2.5 wait for keys/photos.
- Repo was not a git repo; `git init` done in T0.1.

## Open issues

(none yet)

## Log

### 2026-10-12 — T0.5 (README part), T1.1
- Built: `eval/fridges/README.md`; `app/tools/normalize.py` (`normalize`, `same_ingredient`); `tests/test_normalize.py` (57 tests total pass).
- Design: synonyms are tried on the full phrase before adjectives are stripped (so "minced beef" -> "ground beef"), then again after stripping; only the last word is singularized; leading quantities ("2", "500 g of") and parentheticals are dropped. `normalize` is idempotent.
- Human still owes: photos in `eval/fridges/<household>_<place>/` (4-6 sets, >=2 fridge, >=2 pantry) and `.env` keys.

**How to verify**
```
uv run pytest tests/test_normalize.py -q    # expect: 51 passed
uv run python -c "from app.tools.normalize import normalize as n; print(n('Fresh Scallions'), n('chicken thighs'), n('tomatoes'))"
```
Expected output: `green onion chicken tomato`.

### 2026-10-12 — T0.1, T0.2, T0.3
- Built: `pyproject.toml` (uv, deps per plan), folder layout from CLAUDE.md (empty modules), `.env.example`, `app/config.py`, `app/api.py` (`/health`), `app/models.py` (all §7 models + `InventoryChange`, `Constraints`), `data/staples.json` (15), `data/synonyms.json` (112), tests `tests/test_models.py`, `tests/test_data.py`, `tests/test_health.py` (5 pass).
- Next task must know: `config.py` exposes `VISION_MODEL`, `AGENT_MODEL`, `RECIPE_MODEL`, `DB_PATH`, `UNCERTAIN_THRESHOLD`, `STAPLES_PATH`, `SYNONYMS_PATH`. Run via `uv run` (a stray `VIRTUAL_ENV` warning from conda is harmless).
- Open issues: none.

**How to verify**
```
uv sync
uv run pytest -q          # expect: 5 passed
uv run uvicorn app.api:app --port 8000
curl localhost:8000/health   # expect: {"ok":true}
```
Manual check: open http://localhost:8000/docs in a browser and call `GET /health` from there.
