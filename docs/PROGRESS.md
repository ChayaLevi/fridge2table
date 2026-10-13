# Progress

Updated by Claude Code at the end of every task (see "Session protocol" in `CLAUDE.md`). Newest log entry first.

## Status

- [x] T0.1 Scaffold
- [x] T0.2 Schemas
- [x] T0.3 Static data
- [x] T0.4 Model smoke test 🧑 (skipped at first for lack of a key; done 2026-10-12)
- [~] T0.5 Eval set structure 🧑 (README done; waiting for the human's photos)
- [x] T1.1 Normalization
- [x] T1.2 Store
- [x] T1.3 Inventory tools
- [~] T1.4 Recognition + vision eval 🧑 (code + tests done; real eval waits for photos)
- [x] T1.5 Checks
- [x] T1.6 Recipes
- [x] T1.7 Preferences
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

- **Next task: T2.1 Agent** (nothing needed from the human; the DeepSeek key is in `.env`). Then T2.2-T2.5.
- **Blocked on the human:** eval photos in `eval/fridges/<household>_<place>/` (4-6 sets, >=2 fridge, >=2 pantry, each with `labels.json`) for T0.5 and the open part of T1.4. The folders `home1_fridge` and `home1_pantry` exist locally but are empty. When they arrive: run `eval/run_vision_eval.py` for tiles 1, 2 and 4, set `VISION_TILES` in `.env.example` to the best one, report the numbers, tick T1.4.
- The DeepSeek key is in `.env` (since 2026-10-12), so real-model steps are not blocked by keys.
- State: 259 tests pass. All P1 tools exist; `app/agent.py` is still an empty file.

## Current model settings

Only Chinese models (see `docs/PRODUCT.md` §9). All via the DeepSeek API (`DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL=https://api.deepseek.com`); IDs verified in T0.4 (2026-10-12) against `GET /models` and DeepSeek's pricing page.

- VISION_MODEL: `deepseek-flash` (DeepSeek-V4.1-Flash, the only DeepSeek model that accepts images; temporary, swap to Qwen3.8 Max once that license is approved; decided on our photos in T1.4/T5.1)
- AGENT_MODEL: `deepseek-v4-pro` (text only; try `deepseek-flash` only if turns are too slow, T5.2)
- RECIPE_MODEL: `deepseek-flash`
- `deepseek-v4-flash` and `deepseek-v4-flash-vision-exp` are retired aliases: still accepted, served by `deepseek-flash`.
- VISION_TILES: 1 (best value chosen in T1.4)

## Decisions and deviations from the plan

- ~~Model defaults were provisional Gemini/Claude strings~~ (superseded by the DeepSeek switch and T0.4; model values are bare DeepSeek IDs, see "Current model settings").
- Extras beyond the plan (small): `.gitignore`, `pytest.ini` (asyncio_mode=auto), `httpx` dev dependency (needed by FastAPI TestClient), `LOG_LEVEL`/`LOGFIRE_TOKEN` in `.env.example` (CLAUDE.md debugging aids).
- `data/synonyms.json` has 115 entries (112 + 3 added in the T1.1 redo) (flat map, no chains; a test enforces that targets are canonical). Ambiguous keys like bare `pepper` were left out on purpose.
- `InventoryChange` fields: `op`, `name`, optional `display_name`, `category`, `location`, `qty_level`, `use_soon`, `new_name`.
- 2026-10-12 (later): PLAN/PRODUCT were updated (pantry coverage). T0.2 re-done: added `ScanState`, `PANTRY_CATEGORIES`, `Ingredient.category`, `MissingReport.check_first`, `AgentReply.check_first`, extended category list. Tests now 6 pass. T0.1/T0.3 unaffected. T0.5 now asks for 4–6 sets (≥2 fridge, ≥2 pantry), folders `<household>_<place>`.
- Order change (user request, 2026-10-12): the human has no API keys/photos yet, so T0.4 is deferred and P1/P2 are built with mocked models. T0.4, the real run of T1.4 and T1.6, and T2.5 wait for keys/photos.
- Repo was not a git repo; `git init` done in T0.1.

## Open issues

- (T1.6) `suggest_meals` takes ~28 s with `deepseek-flash` for 5 full recipes (`get_recipe` ~10 s). Too slow for the 25 s Mode A target once the agent's own calls are added; T5.2 should lower `n` or drop `steps` from the candidates.
- (T1.6) `lasagna noodle` does not normalize to `pasta` (no synonym), so plain pasta in the inventory does not cover lasagna sheets. Arguably right; revisit if Mode B looks wrong in scenarios.

- (T0.4) The human's `.env` still sets `VISION_MODEL=deepseek-v4-flash-vision-exp` / `RECIPE_MODEL=deepseek-v4-flash` (retired aliases, still served by `deepseek-flash`). Change both to `deepseek-flash`.
- (T0.4) `CLAUDE.md`, `docs/PRODUCT.md` §9 and `docs/PLAN.md` still name the old model IDs; the human should update them or confirm the new defaults.
- (T0.5/T1.4) No eval photos yet: `eval/fridges/home1_fridge` and `home1_pantry` are empty. T1.4's "Done when" (first table on the real eval set for tiles 1, 2, 4; best `VISION_TILES`; recall vs 70%) is still open.

## Log

### 2026-10-13 — T1.7 Preferences
- Built: `app/tools/preferences.py` (`save_preference`, `get_preferences`, `preferences_summary`, `format_preferences`), `tests/test_preferences.py` (13 tests; 259 total pass). `app/tools/recipes.py`: the private `_preferences_text` is gone; the recipe prompts now use `preferences_summary(store)` (one line per preference, under a `Preferences:` header).
- API (store first, like the other tools): `save_preference(store, text, avoid=None) -> Preference`, `get_preferences(store) -> list[Preference]`, `preferences_summary(store) -> str` (`none`, or lines `- text (avoid: a, b)`), `format_preferences(prefs)` (same text from a list).
- Dedupe rules (design decision, the plan only said "dedupe"): `avoid` is normalized and deduped. Same text as an existing preference (case/space-insensitive) -> no new row, its `avoid` is extended. Otherwise avoid items already avoided by any preference are dropped; if none are left, no new row and the existing preference that covers them is returned ("kids hated the eggplant" then "no aubergine please" -> one preference). A text-only preference (empty `avoid`) is allowed, deduped by text; an empty text with avoid items gets the text `avoid <items>`; both empty -> `ValueError`.
- Next tasks must know: T2.1 wrapper = `save_preference(ctx.deps.store, text, avoid)`; the returned preference may be an existing one (same id), so the agent can say "already noted". Dynamic instructions use `preferences_summary(store)`; `validate_suggestion` takes `get_preferences(store)`.
- Open issues: none new.

**How to verify**
```
uv run pytest -q
uv run pytest tests/test_preferences.py -q
uv run python -c "from app.store import Store; from app.tools.preferences import save_preference as sp, preferences_summary as ps; s=Store(':memory:'); sp(s,'kids hated the eggplant',['Aubergines']); sp(s,'no eggplant please',['eggplant']); sp(s,'no eggplant or zucchini',['eggplant','courgettes']); print(ps(s))"
```
Expected: `259 passed`; then `13 passed`; then two lines: `- kids hated the eggplant (avoid: eggplant)` and `- no eggplant or zucchini (avoid: zucchini)` (the second call added nothing, the third kept only the new item).
Manual check: run `uv run python scripts/try_recipes.py --minutes 30` (real model, ~30 s); the demo inventory's eggplant preference still keeps eggplant out of every dish, now passed through `preferences_summary`.

### 2026-10-13 — T1.6 Recipes
- Built: `app/tools/recipes.py` (`suggest_meals`, `get_recipe`, prompts `SUGGEST_PROMPT` / `RECIPE_PROMPT` / `INGREDIENT_RULES`), `tests/test_recipes.py` (28 tests; 246 total pass), `scripts/try_recipes.py` (manual run on a built-in demo inventory, in-memory store). `app/tools/recognize.py`: `coerce_category` now also maps plurals and common off-list names (`CATEGORY_ALIASES`: produce, poultry, seafood, cheese, noodles, canned goods, oil, ...) instead of sending them all to `other`; recognition uses it too.
- API (async, store first like the other tools): `await suggest_meals(store, constraints=None, n=5, exclude=None, *, model=None) -> list[Recipe]`, `await get_recipe(store, dish, *, model=None) -> Recipe`. `model` defaults to `recipe_model()`.
- Design:
  - One `Agent(model, output_type=..., instructions=PROMPT)` call each. The model returns `RecipeDraft` (a `Recipe` without `uses_from_inventory`); `MealIdeas` wraps the list for `suggest_meals`.
  - Prompt data: `inventory_summary(get_inventory(store), scan_state)` (staples line included, NOT SCANNED places marked) and the preferences as `text (avoid: a, b)`. `suggest_meals` adds the request text, `max_minutes`, `n` and the exclude list.
  - `get_recipe` gets the same context but is told to write the usual version of the dish and not to drop/replace ingredients the household lacks (substitutions are the agent's job, Mode B); it only leaves out optional extras that conflict with preferences.
  - After the call, code: `normalize` every ingredient name, merge duplicate ingredients (essential if any copy is), drop empty names, `coerce_category`, then `fill_uses_from_inventory` (overwrites anything the model said).
  - Deviation (small, deterministic): `suggest_meals` also drops, in code, dishes named in `exclude` (case/space-insensitive), duplicate dish names and dishes over `max_minutes`, then caps at `n`. So it can return fewer than `n`.
- Real-model run (2026-10-13, `deepseek-flash`, `scripts/try_recipes.py --dish lasagna --minutes 40`): 5 candidates in 28 s, all pass `validate_suggestion`: creamy spinach & mushroom pasta, chicken & bell pepper stir-fry, bacon spinach tomato frittata, tomato cheddar soup, cottage cheese apple pancakes. Spinach (use soon) used in 2; eggplant (use soon but avoided) in none. `get_recipe("lasagna")` in 10 s: standard recipe; check fails with `missing: ground beef, ricotta, mozzarella; pantry not scanned: lasagna noodle, canned tomato not confirmed`.
- Next tasks must know: T1.7 should replace the private `_preferences_text` in `recipes.py` with `preferences_summary()`. T2.1 wrappers: `await suggest_meals(ctx.deps.store, constraints, n, exclude)` / `await get_recipe(ctx.deps.store, dish)`. The candidates are not validated; the agent must call `validate_suggestion`.
- Open issues: suggest_meals latency (28 s), `lasagna noodle` vs `pasta` (see Open issues).

**How to verify**
```
uv run pytest -q
uv run pytest tests/test_recipes.py -q
uv run python scripts/try_recipes.py --dish lasagna --minutes 40
```
Expected: `246 passed`; then `28 passed`; then (about 30-40 s, real model) `suggest_meals with deepseek-flash`, `5 candidates in ...s` (sometimes fewer if one was over 40 min), one `[OK  ]` line per dish with its time, the inventory items it uses and its ingredients (`?` = optional), none containing eggplant; then `get_recipe('lasagna')` with a `[FAIL]` line whose check lists ricotta, mozzarella and ground beef as missing and the pasta/canned items as "pantry not scanned". Dishes differ from run to run.
Manual check: run `uv run python scripts/try_recipes.py --minutes 15`; every dish listed is 15 minutes or less (longer ones are dropped by code, so you may see fewer than 5).

### 2026-10-13 — T1.5 Checks
- Built: `app/tools/checks.py` (`compute_missing`, `validate_suggestion`, `fill_uses_from_inventory`), `tests/test_checks.py` (39 tests; 218 total pass).
- Deviation (schema): `ValidationResult` got two fields with defaults: `check_first: list[str] = []` and `reason: str = ""`. `missing_essential` holds only definite misses; pantry-type items not confirmed because the pantry is unscanned are in `check_first` (they still make `ok=False`). `reason` is one line for the agent / `ModelRetry`, e.g. `missing: ground beef; pantry not scanned: pasta not confirmed; violates preferences: eggplant (kids dislike eggplant)`. When only `check_first` items fail, it starts with `pantry not scanned`.
- Design:
  - Signatures take data, not the store: `compute_missing(recipe, inventory, scan_state)`, `validate_suggestion(recipe, inventory, preferences, scan_state)`, `fill_uses_from_inventory(recipe, inventory)`. `inventory` must be `get_inventory(store)` (it already contains the non-removed staples); checks do not add staples themselves, so a removed staple is missing.
  - Matching: `normalize()` on both sides, set membership (synonyms/plurals resolved by `normalize`). Any `qty_level` counts, uncertain items count too. Output names are canonical and deduped, in recipe order.
  - Pantry rule: pantry absent from `scan_state.scanned` + essential + category in `PANTRY_CATEGORIES` -> `check_first`. Optional ingredients always go to `missing_optional`, never fail validation.
  - Preferences: every ingredient (essential or optional) is checked against every `avoid`; `violated_preferences` entries read `"<ingredient> (<preference text>)"`.
  - `fill_uses_from_inventory` returns a copy; lists non-staple (`is_staple=False`) inventory items used, use-soon first, otherwise recipe order; it overwrites whatever the model put there.
- Next tasks must know: T1.6 calls `fill_uses_from_inventory(recipe, get_inventory(store))`. T2.2's validator: Mode A -> `res = validate_suggestion(...)`, `if not res.ok: raise ModelRetry(f"{meal.name}: {res.reason}. ...")`; Mode B -> `compute_missing` gives `missing_essential` / `check_first`. Remember `spaghetti` normalizes to `pasta`.
- Open issues: none new.

**How to verify**
```
uv run pytest -q
uv run pytest tests/test_checks.py -q
uv run python -c "from datetime import datetime as D; from app.models import Recipe, Ingredient as I, ScanState as S; from app.store import Store; from app.tools.inventory import get_inventory; from app.tools.checks import validate_suggestion as v; r=Recipe(name='bolognese',ingredients=[I(name='spaghetti',amount='400 g',essential=True,category='pasta'),I(name='minced beef',amount='500 g',essential=True,category='meat'),I(name='salt',amount='1 tsp',essential=True,category='spice')],steps=['cook'],time_minutes=40); inv=get_inventory(Store(':memory:')); print(v(r,inv,[],S(scanned={'fridge':D.now()}))); print(v(r,inv,[],S(scanned={'fridge':D.now(),'pantry':D.now()})))"
```
Expected: `218 passed`; then `39 passed`; then two lines. Pantry not scanned: `ok=False missing_essential=['ground beef'] violated_preferences=[] check_first=['pasta'] reason='missing: ground beef; pantry not scanned: pasta not confirmed'`. Pantry scanned: `ok=False missing_essential=['pasta', 'ground beef'] violated_preferences=[] check_first=[] reason='missing: pasta, ground beef'`. Salt never appears (staple).
Manual check: in `uv run python`, build a recipe with an ingredient `aubergines` (category `vegetable`) and call `validate_suggestion(recipe, [], [Preference(id="1", text="kids hate eggplant", avoid=["eggplant"], created_at=datetime.now())], ScanState(scanned={}))`; `violated_preferences` is `['eggplant (kids hate eggplant)']`.

### 2026-10-13 — T1.4 Recognition + vision eval (code done; real eval waits for photos)
- Built: `app/tools/recognize.py`, `eval/run_vision_eval.py`, `tests/test_recognize.py` (15 tests), `tests/test_vision_eval.py` (2 tests); `CATEGORIES` tuple added to `app/models.py`. 179 tests pass.
- API: `await recognize_inventory(images, *, store=None, model=None, tiles=None) -> list[InventoryItem]` (async). `images` = `[(Path, Location)]`. If `store` is given, each tagged place is `mark_scanned`. It does **not** merge into the stored inventory: the T2.1 wrapper calls `merge_recognized(store, items)` after it. `model` defaults to `vision_model()`, `tiles` to `VISION_TILES`. Lower level: `recognize_images(...) -> list[ImageResult]` (per photo: items + latency), used by the eval.
- Design:
  - One `Agent(model, output_type=Recognition)` call per image or per tile, all in parallel via `asyncio.gather`. `Recognition` wraps `items: list[RecognizedItem]` (name, display_name, category, qty_level, confidence, note).
  - Prompt = `RECOGNITION_PROMPT` + a per-place hint (`PLACE_HINTS`) + `TILE_HINT` for crops. The location always comes from the tag.
  - `load_image` resizes so the long side is at most 1600 px; `split_tiles(image, n)`: 1 = as is, 2 = top/bottom, 4 = quadrants, each tile is half the image + 5% on each inner side (10% overlap).
  - `merge_items` (within one photo, across tiles): normalized name, max confidence, the higher `qty_level`, note/display name from the most confident reading, unknown category -> `other`, confidence clamped to 0..1. Across photos: the more confident reading wins (with its location).
  - `uncertain = confidence < UNCERTAIN_THRESHOLD`. Deviation: `InventoryItem` has no `note` field, so for an uncertain item the note goes into `display_name` ("white container (possibly leftover rice)"), so the agent can ask about it.
- Eval script: `--model`, `--tiles 1|2|4`, `--sets` (default `eval/fridges/`), `--out` (default `eval/results/`). Matching with `same_ingredient` against the label name and its `alt`s. A predicted item is "uncertain" (not counted as a hallucination) only if every photo of the set read it as uncertain. Exit code 1 with a clear message when there is no set with a `labels.json`.
- Real-model run (2026-10-13), only on a stand-in set because there are no eval photos: the coffee photo `tests/fixtures/coffee.jpg` labelled `coffee`, in the scratchpad. `deepseek-flash`: recall 1/1 and 0 hallucinations for tiles 1, 2 and 4; latency 3.3 / 3.2 / 3.2 s per photo. This only shows the pipeline works (structured output with images, tiling, parallel calls); it says nothing about accuracy. `VISION_TILES` stays 1 until the real run.
- Next tasks must know: T2.1's `recognize_inventory` tool wrapper = `items = await recognize_inventory(ctx.deps.image_paths_with_tags, store=ctx.deps.store)` then `merge_recognized(ctx.deps.store, items)`. T1.6 can reuse `CATEGORIES` (models) and `coerce_category` (recognize) for recipe ingredient categories.
- Open issues: the real eval (tiles 1/2/4, best `VISION_TILES`, recall vs 70%) waits for the human's photos.

**How to verify**
```
uv run pytest -q
uv run pytest tests/test_recognize.py tests/test_vision_eval.py -q
uv run python eval/run_vision_eval.py --tiles 1
```
Expected: `179 passed`; then `17 passed`; then (while `eval/fridges/` has no `labels.json`) `No labelled sets in ...\eval\fridges (each set needs a labels.json, see eval/fridges/README.md)`. Once there are sets: a markdown table with one row per set, an `all fridge` / `all pantry` row and an `overall` row (recall, halluc/photo, latency/photo), the missed and hallucinated items per set, and `Saved ...\eval\results\vision_<model>_t1_<time>.json`.
Manual check: put one photo of your fridge in `eval/fridges/home1_fridge/1.jpg` with a `labels.json` such as `{"location": "fridge", "items": [{"name": "milk"}, {"name": "egg"}]}` (the items you can see), then run `uv run python eval/run_vision_eval.py --tiles 2`. The table should show recall for that set, and the lines below it should list what was missed and what was invented.

### 2026-10-12 — T0.4 Model smoke test (was skipped, now done)
- Built: `app/llm.py` (`build_model(model_id, provider="deepseek"|"openai-compatible", base_url, api_key)`, `vision_model()`, `agent_model()`, `recipe_model()`, `setup_observability()`), `scripts/smoke.py`, `tests/test_llm.py` (5 tests, no network; 162 total pass), `tests/fixtures/coffee.jpg` (scikit-image sample photo `coffee.png`, CC0, converted to JPEG).
- Model IDs verified: `GET https://api.deepseek.com/models` lists only `deepseek-flash` (V4.1-Flash, text + image input) and `deepseek-v4-pro` (text only). DeepSeek's pricing page says `deepseek-v4-flash` and `deepseek-v4-flash-vision-exp` are retired names that are still accepted and served by `deepseek-flash` (no end date given).
- Deviation (needs the human's OK, see open issues): defaults in `app/config.py` and `.env.example` changed to `VISION_MODEL=deepseek-flash`, `RECIPE_MODEL=deepseek-flash` (`AGENT_MODEL=deepseek-v4-pro` unchanged). `CLAUDE.md`, `docs/PRODUCT.md` §9 and `docs/PLAN.md` still name the old IDs; not edited (human-owned).
- Design:
  - Pydantic AI 2.55's `DeepSeekProvider` hardcodes its base URL, so `build_model` gives it our own `AsyncOpenAI(base_url=DEEPSEEK_BASE_URL, api_key=...)`; it still gets DeepSeek's profile (thinking field, tool-choice rules).
  - pydantic-ai 2.55 does not know `deepseek-flash`; with the default profile it forces `tool_choice` and DeepSeek answers 400 "Thinking mode does not support this tool_choice" (reproduced). `_DEEPSEEK_PROFILE_ALIASES` gives `deepseek-flash` the `deepseek-v4-flash` profile; tool calls and structured output then work (tested live).
  - Images go as `BinaryContent(data, media_type="image/jpeg")` in the user prompt list; resized so the long side is at most 1600 px.
  - `setup_observability()`: `logging.basicConfig(LOG_LEVEL)`, httpx/openai request logs only at DEBUG, Logfire only if `LOGFIRE_TOKEN` is set and `logfire` is installed (it is not a dependency). Sets `PYDANTIC_AI_NO_BANNER=1`.
- Smoke results (2026-10-12, with `deepseek-flash` for vision and recipes): vision 2.8 s ("coffee" for the coffee-cup photo); agent text 2.7 s; agent tool + structured output 3.8 s (called `count_on_shelf`, returned `ShelfCount(item='eggs', count=7)`); recipe structured output 1.7 s. The same four checks also pass with `deepseek-flash` as `AGENT_MODEL` (tool call 2.5 s), and with the old alias IDs.
- Network note: from this machine only `api.deepseek.com` is reachable (Wikimedia, GitHub, jsDelivr time out), so public food photos for T1.4 cannot be downloaded; the coffee photo came from a locally installed package.
- Next tasks must know: build agents with `Agent(agent_model(), ...)`; call `setup_observability()` once at app/script start. T1.4 can reuse the image loading in `scripts/smoke.py` (`load_jpeg`). For DeepSeek V4 models, pydantic-ai sends `reasoning_content` back in later turns (required by DeepSeek with tools); keep message history intact.
- Open issues: (1) the human's `.env` still sets the old alias IDs; they work, but should be changed to `deepseek-flash`. (2) `CLAUDE.md`/`PRODUCT.md`/`PLAN.md` mention the old IDs.

**How to verify**
```
uv run pytest -q
uv run pytest tests/test_llm.py -q
uv run python scripts/smoke.py
```
Expected: `162 passed`; then `5 passed`; then four `[ OK ]` lines (vision, agent text, agent tool + structured output, recipe structured output), each with its latency in seconds and token counts, the tool line showing `tool calls: ['count_on_shelf', 'final_result']; output: ShelfCount(item='eggs', count=7)`, and a last line `ALL OK`. The model names in brackets are the ones in your `.env`.
Manual check: run `uv run python scripts/smoke.py --image path\to\any\food_photo.jpg` with a photo from your phone; the vision line should list the foods in it.

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
