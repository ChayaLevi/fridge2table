# Fridge-to-Table — Work plan (Oct 12 – Oct 23, 2026)

Read `CLAUDE.md` and `docs/PRODUCT.md` first. Work through the tasks **in order**. Each task has **Done when**: do not start the next task until it holds and `uv run pytest -q` passes.

🧑 = needs the human. Stop and ask for exactly what is listed.

## Timeline at a glance

| Day | Phase | Milestone at end of day |
|---|---|---|
| Mon Oct 12 | P0 Setup | Repo runs. One vision call and one text call work. Eval folder ready for photos |
| Tue Oct 13 | P1 Tools (part 1) | Normalization, store, inventory, recognition + first accuracy number |
| Wed Oct 14 | P1 Tools (part 2) | Checks, recipes, preferences. All tools unit-tested |
| Thu Oct 15 | P2 Agent | Agent works from the terminal for Modes A and B, with self-correction and trace |
| Fri Oct 16 | P3 App | Works in a phone browser end to end. **Internal demo to team lead** |
| Mon Oct 19 | P4 Agentic features | Proactive opening, substitutions, cross-session preferences, trace UI |
| Tue Oct 20 | P5 Evaluation + user | Models compared. **Real user run #1. Decision point for stretch** |
| Wed Oct 21 | P6 Fixes (+ stretch) | Fixes from the user run. Stretch only if the decision point passed |
| Thu Oct 22 | P7 Freeze | **Real user run #2. Backup recording.** Code frozen |
| Fri Oct 23 | Demo | Live 10-minute demo |

---

## P0 — Setup (Mon Oct 12)

### T0.1 Scaffold
- `uv init`; dependencies: `pydantic-ai`, `fastapi`, `uvicorn[standard]`, `python-multipart`, `pillow`, `pyyaml`, `python-dotenv`; dev: `pytest`, `pytest-asyncio`.
- Create the folder layout from `CLAUDE.md` (empty modules are fine).
- `.env.example` with: `DEEPSEEK_API_KEY=`, `DEEPSEEK_BASE_URL=https://api.deepseek.com`, `QWEN_API_KEY=` (empty for now; for Qwen3.8 Max later), `VISION_MODEL=deepseek-v4-flash-vision-exp`, `AGENT_MODEL=deepseek-v4-pro`, `RECIPE_MODEL=deepseek-v4-flash`, `VISION_TILES=1`, `DB_PATH=data/app.db`, `UNCERTAIN_THRESHOLD=0.6`.
- Only Chinese models may be used (see `docs/PRODUCT.md` §9). Do not add other providers.
- `app/config.py` loads these with defaults.
- **Done when:** `uv run pytest -q` runs (zero tests is fine) and `uv run uvicorn app.api:app` serves a `/health` route returning `{"ok": true}`.

### T0.2 Schemas
- Implement every model in `docs/PRODUCT.md` §7 in `app/models.py`, including `ScanState`, `PANTRY_CATEGORIES`, `Ingredient.category` and `AgentReply.check_first`. Add `InventoryChange` (`op`: add | remove | set_qty | set_use_soon | rename, plus fields) and a `Constraints` model for `suggest_meals` (`text: str`, `max_minutes: int | None`).
- **Done when:** a test builds one instance of each model and round-trips it through JSON.

### T0.3 Static data
- `data/staples.json`: salt, black pepper, cooking oil, olive oil, sugar, all-purpose flour, water, white vinegar, baking soda, baking powder, dried oregano, paprika, ground cumin, chili flakes, soy sauce.
- `data/synonyms.json`: map variants to one canonical name. Start with about 60 common entries, e.g. `scallion`/`spring onion` → `green onion`; `chicken breast`/`chicken thigh`/`chicken drumstick` → `chicken`; `cilantro`/`fresh coriander` → `cilantro`; `bell pepper`/`capsicum` → `bell pepper`; `heavy cream`/`whipping cream`/`double cream` → `cream`; `minced beef`/`ground beef` → `ground beef`; `courgette` → `zucchini`; `aubergine` → `eggplant`.
- **Done when:** both files load and validate in a test.

### T0.4 Model smoke test 🧑
- 🧑 Ask the human for the DeepSeek API key in `.env`.
- `app/llm.py`: factories that build Pydantic AI models from the env strings. Check the installed Pydantic AI docs for how to connect to DeepSeek (a DeepSeek provider, or an OpenAI-compatible provider with `DEEPSEEK_BASE_URL`), and verify the current model IDs in DeepSeek's API docs. Keep the factory generic (provider + model + base URL + key), so Qwen can be added later by config.
- Also check in the smoke test that `AGENT_MODEL` supports **tool calling** and **structured output** through Pydantic AI (one tiny tool + one tiny Pydantic output). This is what the agent depends on.
- `scripts/smoke.py`: send one image (any food photo) to `VISION_MODEL` asking for a list of items; send one text prompt to `AGENT_MODEL`.
- **Done when:** both calls return sensible output, the tool call and structured output work, and the script prints latency for each.

### T0.5 Eval set structure 🧑
- Create `eval/fridges/README.md` explaining the format:
  - one folder per fridge/pantry shot set: `eval/fridges/<id>/` with 1–4 `.jpg` and a `labels.json`:
    ```json
    {"location": "fridge",
     "items": [{"name": "milk", "alt": ["whole milk"]}, {"name": "egg"}, {"name": "spinach", "use_soon": true}]}
    ```
  - `items` = what a human sees in the photos. `alt` = other names that should count as correct.
- One folder = one place (`"location"` in `labels.json` is `fridge`, `freezer` or `pantry`). Name folders `<household>_<place>`, e.g. `home1_fridge`, `home1_pantry`.
- 🧑 Ask the human to add 4–6 sets with labels: **at least 2 fridge sets and at least 2 pantry sets** (pantries test label reading on jars, cans and packages), freezer optional. Continue with P1 meanwhile; T1.4 needs them.
- **Done when:** the README exists and the human has been asked.

---

## P1 — Tools (Tue Oct 13 – Wed Oct 14)

Every tool: plain function in `app/tools/`, Pydantic I/O, unit tests with no network (mock LLM calls with fixtures in `tests/fixtures/`).

### T1.1 Normalization — `app/tools/normalize.py`
- `normalize(name: str) -> str`: lowercase, strip, collapse spaces, strip quantity words and brand-like adjectives from a small list (`fresh`, `organic`, `large`, `small`, `chopped`, `sliced`, `diced`, `minced`, `boneless`, `skinless`), simple singularization (`tomatoes → tomato`, `berries → berry`, `leaves → leaf`; keep an exception list: `asparagus`, `hummus`, `couscous`, `molasses`, `swiss chard`), then the synonyms map.
- `same_ingredient(a, b) -> bool`.
- **Done when:** ≥ 25 test cases pass, covering plurals, adjectives, synonyms and the exceptions.

### T1.2 Store — `app/store.py`
- SQLite tables: `inventory` (one row per item, JSON column is fine), `preferences`, `staples_state` (which default staples the user removed), `scan_state` (the `ScanState`), `sessions` (session_id, message history as JSON from Pydantic AI's serializable messages).
- Functions: `load_inventory`, `save_inventory`, `load_preferences`, `add_preference`, `load_scan_state`, `mark_scanned(location)`, `set_freezer_declined()`, `load_session_messages`, `save_session_messages`, `reset_all` (for tests and demo seeding).
- **Done when:** tests on a temp DB show data survives closing and reopening the connection.

### T1.3 Inventory tools — `app/tools/inventory.py`
- `get_inventory() -> list[InventoryItem]`: stored items + staples that were not removed (`is_staple=True`, `source="staple"`, `qty_level="plenty"`, `confidence=1.0`).
- `update_inventory(changes: list[InventoryChange]) -> list[InventoryItem]`. Rules: names go through `normalize`; `add` of an existing canonical name updates it instead of duplicating; `remove` of a staple records it in `staples_state`; `set_qty` lowering below `low` removes the item.
- `merge_recognized(items: list[InventoryItem])`: add new; for existing canonical names update `qty_level` and `confidence` but **never** clear `use_soon` and never override items with `source="manual"`. Recognition never removes items.
- `inventory_summary(items, scan_state) -> str`: compact text for prompts, grouped by location, `use_soon` marked, uncertain marked. Each location header says whether it was scanned ("pantry: NOT SCANNED"). Keep it under ~1,500 characters for 60 items.
- **Done when:** tests cover add/duplicate/remove/staple removal/merge rules, and the summary length.

### T1.4 Recognition — `app/tools/recognize.py` + `eval/run_vision_eval.py` 🧑
- `recognize_inventory(images: list[tuple[Path, Location]]) -> list[InventoryItem]`: each image comes with the place the user tagged. One vision call per image, **in parallel** (asyncio), structured output into a `RecognizedItem` list (name, display_name, category, qty_level, confidence, note). The location comes from the tag, not the model. The prompt tells the model which place it is looking at (e.g. "This is a pantry shelf or cabinet: expect dry goods, cans, jars and packages; read their labels."). Resize images so the long side ≤ 1600 px before sending. After recognition, `mark_scanned` each tagged place.
- Prompt rules (module constant `RECOGNITION_PROMPT`):
  - List each distinct food or drink item that is visible. Use a generic English name ("greek yogurt", "cheddar", "ketchup"), not brand names.
  - Read labels when legible, and use them for the name.
  - Do not guess the contents of opaque or closed containers. Add them as an item named by appearance ("white container") with `confidence ≤ 0.4` and a `note` with the best guess ("possibly leftover rice").
  - Quantity: `plenty` / `some` / `low` from what is visible.
  - Do not list non-food items.
- After the call: `normalize` names, merge duplicates across images (keep the higher confidence), set `uncertain = confidence < UNCERTAIN_THRESHOLD`.
- **Tiling** (`VISION_TILES`, default 1): when 2 or 4, split each image into that many crops with ~10% overlap (2 = top/bottom halves, 4 = quadrants), send each crop as its own call in parallel, and merge by canonical name (max confidence, the higher `qty_level`). Needed because the DeepSeek vision model caps each image at about 384 tokens. Keep it a pure function (`split_tiles(image, n)`) with a unit test.
- `eval/run_vision_eval.py --model <id> --tiles <1|2|4>`: for each folder in `eval/fridges/`, run recognition (with the folder's `location` as the tag), match predictions to labels with `same_ingredient` (and `alt`), and print a markdown table: per set, **per place (fridge / pantry / freezer)** and overall **recall** (labelled items found), **hallucinations per photo** (predicted items matching no label, excluding items flagged uncertain), **mean latency per photo**. Save the results as JSON in `eval/results/`.
- 🧑 Needs the photos from T0.5. If they are not there yet, build and test with 1–2 public food photos and say so.
- **Done when:** unit tests pass with a mocked model, and the eval script prints a first table on the real eval set **for tiles = 1, 2 and 4**. Set `VISION_TILES` in `.env.example` to the best one and report the numbers to the human. If recall is far below 70% even with tiling, say so clearly: it is the signal to push for the Qwen license.

### T1.5 Checks — `app/tools/checks.py` (no LLM)
- `compute_missing(recipe, inventory, scan_state) -> MissingReport` using the matching rule and the **unscanned pantry rule** in `docs/PRODUCT.md` §7.
- `validate_suggestion(recipe, inventory, preferences, scan_state) -> ValidationResult`: `ok` only if no essential ingredient is missing (including `check_first` ones) and no ingredient is in any preference's `avoid` list (compare with `same_ingredient`). When the failure is only `check_first` items, the reason says "pantry not scanned".
- `fill_uses_from_inventory(recipe, inventory) -> Recipe`: set `uses_from_inventory` (non-staple inventory items used), with `use_soon` items first.
- **Done when:** ≥ 18 tests pass: synonyms, staples, a removed staple, optional ingredients, `low` items counting as available, preference violations, an empty inventory, and the pantry rule (pantry unscanned → pasta goes to `check_first`; pantry scanned → pasta goes to `missing_essential`; a vegetable is never `check_first`).

### T1.6 Recipes — `app/tools/recipes.py`
- `suggest_meals(constraints, n=5, exclude: list[str]=[]) -> list[Recipe]`: one call to `RECIPE_MODEL` with structured output. The prompt includes `inventory_summary`, preferences, constraints, the names to exclude, and the instruction: build each dish around inventory items, prefer "use soon" items, mark ingredients `essential` honestly, use only staples from the provided list without listing them as missing, home-cooking dishes that take ≤ `max_minutes` if given.
- `get_recipe(dish: str) -> Recipe`: one structured call. Standard home recipe, essential flags honest.
- In both, every ingredient must have a `category` from the list in `docs/PRODUCT.md` §7 (the pantry rule depends on it). If the model returns an unknown category, map it with a small lookup or default to `other`.
- Both run `normalize` on ingredient names and `fill_uses_from_inventory` before returning.
- Return **n = 5** candidates so the agent has spares when some fail validation.
- **Done when:** tests with a mocked model check parsing, normalization and the exclude list. One manual run against the real model on the seeded demo inventory gives sensible dishes (print them).

### T1.7 Preferences — `app/tools/preferences.py`
- `save_preference(text: str, avoid: list[str]) -> Preference` (normalize `avoid`; dedupe against existing preferences).
- `get_preferences() -> list[Preference]`, `preferences_summary() -> str` for prompts.
- **Done when:** tests pass, including dedupe.

---

## P2 — Agent (Thu Oct 15)

### T2.1 Agent — `app/agent.py`
- A Pydantic AI `Agent` on `AGENT_MODEL`, `output_type=AgentReply`, with dependencies (a `Deps` dataclass holding the store and the session's uploaded image paths).
- **Dynamic instructions** rebuilt on every run: the rules in `docs/PRODUCT.md` §5, plus the current `inventory_summary` and `preferences_summary`. Because the inventory is in the instructions, the agent does not need to call `get_inventory` just to read it. Still register `get_inventory` for when it updates and wants the fresh state.
- Tools (thin wrappers that call `app/tools/*`): `recognize_inventory`, `get_inventory`, `update_inventory`, `suggest_meals`, `get_recipe`, `compute_missing`, `validate_suggestion`, `save_preference`. Tool docstrings tell the model when to use each one: they are part of the prompt.
- Images: the API saves uploads and passes their paths in `Deps`; the user message says "[user attached N photos]". The agent calls `recognize_inventory` (no args needed; it reads paths from `Deps`), which also runs `merge_recognized`.
- Limit tool calls per run (use Pydantic AI usage limits) to about 10.
- **Done when:** the agent runs from Python with a fixture inventory and returns a valid `AgentReply`.

### T2.2 Output validator (the self-correction guarantee)
- An `@agent.output_validator` that, for every meal in `AgentReply.meals`:
  - Mode A meals (no shopping list): `validate_suggestion` must be `ok`, otherwise `raise ModelRetry` with the meal name and the reason ("Kung pao chicken needs peanut, not in inventory. Replace it or move it to a Mode B answer with a shopping list.").
  - Mode B (a shopping list is present): `shopping_list` must equal `missing_essential` minus the substituted items, and `check_first` must equal `MissingReport.check_first`. Fix both in code if the model's lists differ (trust code over the model).
  - Every `Substitution.use_instead` must be in the inventory; otherwise `ModelRetry`.
  - Also enforce: at most 3 meals, at most 3 questions.
- Re-fill `uses_from_inventory` with code before returning.
- **Done when:** a test with a mocked model that first returns an invalid meal shows the retry, then a valid final reply.

### T2.3 Trace capture
- After each run, walk the run's new messages and build `list[ToolTraceItem]` from tool calls and returns. Summaries must be short ("added 2, removed 1", "5 candidates", "FAILED: missing cream"). Validator retries count as a trace item ("output check failed: …").
- Also record per-turn latency and token usage (for T5.2).
- **Done when:** a test asserts the trace for a mocked run.

### T2.4 Terminal chat — `scripts/chat.py`
- REPL against the real agent, using a session id, persisting history with `store`. `/photo path.jpg` attaches images. Prints the reply, the meal names and the trace.
- **Done when:** the human (or you, with the demo seed) can run Mode A and Mode B conversations in the terminal.

### T2.5 Scenario suite — `eval/scenarios.yaml` + `eval/run_scenarios.py`
- Each scenario: seed inventory and preferences, a list of user messages, expectations. Expectations can include: `tools_called` (in order, subset), `max_meals`, `meals_must_not_contain`, `max_minutes`, `shopping_list_contains` / `must_not_contain`, `preference_saved`.
- Write at least these 10:
  1. "What can I cook tonight?" → `suggest_meals` then `validate_suggestion`; 1–3 meals; all valid.
  2. "We're out of eggs, something in 30 minutes" → `update_inventory` before `suggest_meals`; no egg; ≤ 30 min.
  3. Inventory set up so the obvious dish fails (e.g. lots of pasta, no cream) → trace shows a failed check, final meals valid.
  4. "I want to make lasagna" with ricotta missing but cottage cheese present → substitution proposed; ricotta not in the shopping list.
  5. "I want to make pancakes" with everything present → empty shopping list, says so.
  6. "The kids hated the eggplant" → `save_preference` with avoid `eggplant`.
  7. New session after #6, inventory with eggplant as "use soon" → no eggplant in the meals.
  8. Photos attached (use an eval set) → `recognize_inventory` called; reply asks ≤ 3 questions.
  9. Only fridge photos attached, pantry never scanned → the reply asks once for a pantry photo.
  10. Pantry not scanned, "I want to make spaghetti bolognese", no pasta in the fridge → `spaghetti` (and canned tomatoes) in `check_first`, not in `shopping_list`. Same request after a pantry scan without pasta → pasta in `shopping_list`.
- Runs against real models. Prints pass/fail per scenario plus latency.
- **Done when:** the suite runs; at least 8/10 pass. Fix prompts and tool docstrings until they do. Report which fail.

---

## P3 — App (Fri Oct 16)

### T3.1 API — `app/api.py`
- `POST /chat` (multipart: `session_id`, `message`, up to 4 `images`, and a matching list of `locations`, one per image) → `AgentReply` + `trace` + `inventory` + `scan_state` (so the panel refreshes after every turn).
- `GET /inventory`, `PATCH /inventory` (a list of `InventoryChange`; the panel's direct edits, no agent).
- `GET /opening?session_id=` → proactive greeting (implemented in T4.1; return a static greeting for now).
- `POST /admin/seed` (demo seeding from `data/demo_seed.json`) and `POST /admin/reset`.
- Serve `app/static/index.html` at `/`.
- **Done when:** endpoint tests with FastAPI `TestClient` and a mocked agent pass.

### T3.2 Web page — `app/static/index.html`
- Build the UI in `docs/PRODUCT.md` §8, mobile first, plain JS. Session id kept in `localStorage` (wrapped in try/catch); a "New chat" button creates a new one (this is how we show cross-session memory).
- Photo attach: `<input type="file" accept="image/*" multiple capture="environment">`. Show thumbnails before sending, each with a place tag (Fridge / Freezer / Pantry) that cycles on tap. Default: the first photo is Fridge; each next photo copies the previous tag.
- Inventory panel: each location header shows "scanned …" / "not scanned yet" and a camera button that opens the picker pre-tagged with that place.
- Shopping list block: "To buy" and "Check your pantry first" as two groups.
- Meal card tap → bottom sheet with the full recipe. Trace line collapsed by default.
- Inventory drawer: tap quantity to cycle, "use soon" toggle, delete, add. Each edit calls `PATCH /inventory`.
- **Done when:** the full flow works in a phone browser on the same network: photos → panel fills → ask for meals → cards → open a recipe → edit the panel → the next answer reflects the edit.

### T3.3 First real-fridge run + internal demo 🧑
- Create `data/demo_seed.json`: a realistic inventory of about 25 items, with spinach marked "use soon".
- 🧑 Ask the human to run the flow on a real fridge and to show it to the team lead.
- Collect issues in `docs/ISSUES.md` (one line each, with the day found).
- **Done when:** the run happened and the issues are written down.

---

## P4 — Agentic features (Mon Oct 19)

### T4.1 Proactive opening
- `GET /opening`: if the inventory is empty → a fixed welcome asking for photos of the fridge and the pantry, tagged with their place (no LLM call). Otherwise run the agent with a hidden system-side message: "The user just opened the app. Greet briefly and offer one meal idea, preferring use-soon items. Validate it." Do not store this hidden message as a user turn in the history.
- **Done when:** with the demo seed, the opening mentions spinach and offers a valid meal.

### T4.2 Substitutions in Mode B
- Make sure scenario 4 passes reliably: tune the instructions and the `get_recipe` / `compute_missing` tool docstrings so the agent checks the inventory for substitutes before building the shopping list. The validator from T2.2 already guarantees that substitutes exist in the inventory.
- **Done when:** scenario 4 passes in 3 runs out of 3.

### T4.3 Preferences end to end
- Scenarios 6 and 7 pass. In the UI, after `save_preference`, the agent's message says briefly what it will remember ("Got it, no eggplant from now on.").
- **Done when:** in the browser, state a preference, press "New chat", ask for dinner: the preference is respected.

### T4.4 Trace UI polish
- The collapsed line reads as one sentence ("4 steps · updated inventory → 5 ideas → 1 failed check (no cream) → replaced"). Expanded: one line per step. Failed checks in a warning colour.
- **Done when:** the human confirms it reads well on a phone.

---

## P5 — Evaluation and the real user (Tue Oct 20)

### T5.1 Vision model comparison
- Run `eval/run_vision_eval.py` with the DeepSeek vision model at its best tile setting and, if the Qwen license has arrived, with Qwen3.8 Max (tiles = 1 and 2; optionally Qwen3.8 Flash). Only Chinese models. Write `eval/RESULTS.md`: a table of recall, hallucinations per photo, latency and cost per photo, plus a recommendation.
- Update the acceptance targets in `docs/PRODUCT.md` §10 if the data says they are off.
- **Done when:** the human picks the model and `.env` is updated.

### T5.2 Latency
- Measure: photos → inventory; a Mode A turn; a Mode B turn (use the timings from T2.3). If a Mode A turn takes > 25 s: lower `n` in `suggest_meals`, run `validate_suggestion` for all candidates in one tool call (accept a list), or switch `AGENT_MODEL` to `deepseek-v4-flash` and rerun the scenarios to check quality holds. Stream the message text if not done yet.
- **Done when:** the numbers are in `eval/RESULTS.md` and meet the targets, or the gap is explained.

### T5.3 Real user run #1 🧑
- 🧑 The human runs a session with the real user on the user's own fridge. Before: `/admin/reset`. During: the human only watches and notes every intervention.
- Add findings to `docs/ISSUES.md` and order them by impact.
- **Decision point (end of day):** stretch goals go in only if (a) the user completed the flow without the developer stepping in, (b) recognition meets the acceptance target, (c) no open issue breaks the flow. Write the decision in `docs/ISSUES.md`.

---

## P6 — Fixes and stretch (Wed Oct 21)

- Fix the top issues from T5.3 first. Rerun `eval/run_scenarios.py` after each fix.
- Only if the decision point passed:
  - **T6.1 "We cooked it":** a button on each meal card ("We cooked this") and a chat intent. Lowers each used non-staple ingredient one level (`plenty → some → low → removed`) via `update_inventory`. Add a scenario.
  - **T6.2 Share shopping list:** a "Copy list" button on the shopping-list block (plain text, one item per line).
- **Done when:** issues fixed or consciously deferred; scenarios ≥ 9/10 pass.

## P7 — Freeze (Thu Oct 22) 🧑

- Code freeze after the morning. Only demo-blocking fixes after that.
- `scripts/demo_reset.sh`: reset, then seed (spinach marked "use soon", eggplant present, no ricotta, cottage cheese present, pasta without cream). Seed the fridge only and leave the pantry unscanned, so the demo shows the agent asking for it and then scanning it live.
- 🧑 Real user run #2 on the frozen build.
- 🧑 Record a backup video of the full demo script (`docs/PRODUCT.md` §12).
- Write `README.md`: what it is, setup, env vars, how to run, how to run the evals, known limits.
- **Done when:** the demo script runs twice in a row without problems after `demo_reset.sh`.

## Demo day (Fri Oct 23) 🧑

Live demo following `docs/PRODUCT.md` §12, then the scorecard: did it work end to end live, minutes from input to a usable result, number of human interventions (inventory corrections), would the user hand it the task again, did anyone ask to share the output, and which parts are reusable by other teams (recognition, normalization, the checks).
