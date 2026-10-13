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
- [x] T2.1 Agent
- [x] T2.1b Latency fix (reply by id, validation inside suggest_meals, steps on demand, per-step timing, thinking off)
- [x] T2.2 Output validator (+ essential-flag fix)
- [x] T2.3 Trace capture
- [x] T2.4 Terminal chat
- [x] T2.5 Scenario suite
- [x] T3.1 API
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

- **Next task: T3.2 Web page** (nothing needed from the human until the phone check). The API is in `app/api.py`; every route returns the panel state (`inventory` + `scan_state`) so the page can redraw it after any call; `/chat` and `/opening` share one response shape (`reply`, `trace`, `usage`, `inventory`, `scan_state`). Errors come back as `{"detail": "..."}` (400 bad input, 502 agent failed, 503 model service down): show `detail` in the chat. Replace the placeholder `app/static/index.html`.
- **Blocked on the human:** eval photos in `eval/fridges/<household>_<place>/` (4-6 sets, >=2 fridge, >=2 pantry, each with `labels.json`) for T0.5 and the open part of T1.4. The folders `home1_fridge` and `home1_pantry` exist locally but are empty. When they arrive: run `eval/run_vision_eval.py` for tiles 1, 2 and 4, set `VISION_TILES` in `.env.example` to the best one, report the numbers, tick T1.4.
- The DeepSeek key is in `.env` (since 2026-10-12), so real-model steps are not blocked by keys.
- State: 353 tests pass. The FastAPI app (`app/api.py`) serves all T3.1 routes. Scenario suite (`eval/run_scenarios.py`): 10/10 pass on real models (39/40 over the T2.5 runs, the one failure a network error). All P1 tools, the agent (`app/agent.py`, `run_turn`), per-step timing, the output validator, the trace (`app/trace.py`, `TurnResult.trace` / `.usage`) and the terminal chat (`scripts/chat.py`) exist.

## Current model settings

Only Chinese models (see `docs/PRODUCT.md` §9). All via the DeepSeek API (`DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL=https://api.deepseek.com`); IDs verified in T0.4 (2026-10-12) against `GET /models` and DeepSeek's pricing page.

- VISION_MODEL: `deepseek-flash` (DeepSeek-V4.1-Flash, the only DeepSeek model that accepts images; temporary, swap to Qwen3.8 Max once that license is approved; decided on our photos in T1.4/T5.1)
- AGENT_MODEL: `deepseek-v4-pro` (text only; try `deepseek-flash` only if turns are too slow, T5.2)
- RECIPE_MODEL: `deepseek-flash`
- `deepseek-v4-flash` and `deepseek-v4-flash-vision-exp` are retired aliases: still accepted, served by `deepseek-flash`.
- VISION_TILES: 1 (best value chosen in T1.4)
- AGENT_THINKING / RECIPE_THINKING: `off` (2026-10-13; DeepSeek V4 thinks by default; off = `reasoning_effort: none` via pydantic-ai's `thinking=False`)

## Decisions and deviations from the plan

- ~~Model defaults were provisional Gemini/Claude strings~~ (superseded by the DeepSeek switch and T0.4; model values are bare DeepSeek IDs, see "Current model settings").
- Extras beyond the plan (small): `.gitignore`, `pytest.ini` (asyncio_mode=auto), `httpx` dev dependency (needed by FastAPI TestClient), `LOG_LEVEL`/`LOGFIRE_TOKEN` in `.env.example` (CLAUDE.md debugging aids).
- `data/synonyms.json` has 115 entries (112 + 3 added in the T1.1 redo) (flat map, no chains; a test enforces that targets are canonical). Ambiguous keys like bare `pepper` were left out on purpose.
- `InventoryChange` fields: `op`, `name`, optional `display_name`, `category`, `location`, `qty_level`, `use_soon`, `new_name`.
- 2026-10-12 (later): PLAN/PRODUCT were updated (pantry coverage). T0.2 re-done: added `ScanState`, `PANTRY_CATEGORIES`, `Ingredient.category`, `MissingReport.check_first`, `AgentReply.check_first`, extended category list. Tests now 6 pass. T0.1/T0.3 unaffected. T0.5 now asks for 4–6 sets (≥2 fridge, ≥2 pantry), folders `<household>_<place>`.
- Order change (user request, 2026-10-12): the human has no API keys/photos yet, so T0.4 is deferred and P1/P2 are built with mocked models. T0.4, the real run of T1.4 and T1.6, and T2.5 wait for keys/photos.
- Repo was not a git repo; `git init` done in T0.1.

## Open issues

- (T2.5) Scenarios 8 and 9 use `tests/fixtures/coffee.jpg` (one coffee photo) because `eval/fridges` is still empty; swap in a real eval set when it exists (`photos:` in `eval/scenarios.yaml`).
- (T2.5) Turn latency varies with the API: the same Mode A turn took 11 s and 21 s on the same day, sequentially. With `--jobs 4` turns take 20-36 s (parallel load), so use `--jobs 1` for latency numbers (T5.2).
- (T2.5) `ModelAPIError: Connection error` happened once in about 45 real turns; `run_turn` does not retry it. Since T3.1 `/chat` returns 503 with "The model service did not answer. Please try again."
- (T2.4) Recipe ids are per run (`Deps.recipes`): when the user refers back to a dish from an earlier turn, the agent sometimes reuses the old id, gets an "unknown meal id" output-check retry, and then calls `get_recipe` again (seen once in a real run, +5 s). Correct (the validator catches it) but slow (seen again in T3.1: a photo turn after a Mode A turn reused the 3 old ids, +~8 s, 24 s total); if it shows up often, preload `Deps.recipes` with the recipes named in the session's last reply.
- ~~(T2.1) Mode A turn takes 50-80 s~~ Fixed 2026-10-13 (T2.1b): Mode A 11-14 s, Mode B 9-10 s. See the T2.1b log entry.
- (T2.1b, for T4.2) Mode B prose: the agent sometimes proposes a substitute only in `message` prose instead of `substitutions`, and the prose can contradict the code-fixed lists (T2.2 real runs: "you'd need to buy ... ricotta" while ricotta is substituted and not in `shopping_list`). The lists are right (code wins); the message text is not checked.
- ~~(T2.1b) `deepseek-flash` marked ground beef / parmesan optional in lasagna~~ Fixed 2026-10-13 (T2.2): essential defined with examples in `INGREDIENT_RULES` + code rule `force_named_essential`. 3/3 real lasagna runs had all four essentials.
- (T2.2) One real lasagna run substituted chicken for ground beef ("a chicken lasagna"). Valid (chicken is in the inventory) but a stretch; watch in T4.2.
- (T2.1) Synonym gaps seen in real Mode B runs: ~~`ricotta cheese` != `ricotta`~~ (fixed in T2.5), `crushed tomato` / `tomato paste` are separate names (both correct but noisy in `check_first`); `lasagna noodle` vs `pasta` as before.
- ~~(T1.6) `suggest_meals` takes ~28 s~~ Fixed 2026-10-13: 5-7 s without steps and without thinking (`get_recipe` 2-3 s).
- (T1.6) `lasagna noodle` does not normalize to `pasta` (no synonym), so plain pasta in the inventory does not cover lasagna sheets. Arguably right; revisit if Mode B looks wrong in scenarios.

- (T0.4) The human's `.env` still sets `VISION_MODEL=deepseek-v4-flash-vision-exp` / `RECIPE_MODEL=deepseek-v4-flash` (retired aliases, still served by `deepseek-flash`). Change both to `deepseek-flash`.
- (T0.4) `CLAUDE.md`, `docs/PRODUCT.md` §9 and `docs/PLAN.md` still name the old model IDs; the human should update them or confirm the new defaults.
- (T0.5/T1.4) No eval photos yet: `eval/fridges/home1_fridge` and `home1_pantry` are empty. T1.4's "Done when" (first table on the real eval set for tiles 1, 2, 4; best `VISION_TILES`; recall vs 70%) is still open.

## Log

### 2026-10-13 — T3.1 API
- Built / changed:
  - `app/api.py`: `POST /chat` (multipart `session_id`, `message`, up to 4 `images`, `locations` one per image as repeated fields or one comma-separated field, which is what `/docs` sends) -> `ChatResponse` (`reply` with `meals` filled, `trace`, `usage`, `inventory`, `scan_state`). `GET /inventory`, `PATCH /inventory` (list of `InventoryChange`, applied with `source="manual"`) -> `InventoryState` (`inventory` incl. staples, `scan_state`). `GET /recipe/{id}/steps` -> `Recipe` via `recipes.get_steps` (404 unknown id). `GET /opening?session_id=` -> a static greeting in the `ChatResponse` shape (`trace: []`, `usage: null`), so T4.1 can swap in an agent run without changing the page. `POST /admin/seed`, `POST /admin/reset` -> `InventoryState`. `/` serves `app/static/index.html`. Logging/Logfire set up in the app lifespan (`setup_observability`).
  - Errors: bad input -> 400 with a reason (location count, unknown place, > 4 photos, no message and no photo); `ModelAPIError` -> 503 "The model service did not answer. Please try again."; `UnexpectedModelBehavior` / `UsageLimitExceeded` -> 502 "Sorry, I could not put together a valid answer this time. ..."; steps failures likewise. Always `{"detail": "..."}`.
  - Dependencies `get_store` (one `Store` per process on `DB_PATH`), `get_turn_runner` (`run_turn`) and `get_recipe_model` (None = config) so tests override them.
  - `app/config.py`: `DEMO_SEED_PATH` (`data/demo_seed.json`), `UPLOAD_DIR` (env, default `data/uploads/`, git-ignored): uploaded photos are saved there as `<uuid>.<ext>` and passed to the agent with their tags.
  - `data/demo_seed.json` (new): the 21-item demo fridge of `scripts/try_recipes.py` (spinach use soon, eggplant, cottage cheese, pasta; no ricotta, no cream), `scanned: ["fridge"]` (pantry unscanned), no preferences. Format: `inventory` = `InventoryChange` add fields without `op`, `scanned` = places, `preferences` = `Preference` dicts.
  - `app/static/index.html`: placeholder page linking to `/docs` (T3.2 replaces it).
  - `tests/test_api.py` (new, 19 tests): Mode A through the real `run_turn` on a scripted model (meals, trace, inventory, history saved), photo upload with tags (repeated and comma-separated), 5 bad-input cases, 503/502 errors, GET/PATCH inventory (manual source, staple removal, 422 on an unknown op), steps generated once then from the store, 404, opening, index, reset + seed, seed file valid.
- Decisions / deviations:
  - `data/demo_seed.json` was created here (the plan puts it in T3.3) because `/admin/seed` needs it; T3.3 may extend it to ~25 items.
  - `/admin/seed` adds on top of the current state (does not reset): call `/admin/reset` first for a clean demo (as `demo_reset.sh` in P7 will). Seeded items use `source="chat"`, not `manual`, so a photo scan can still update them.
  - `/chat` nests the agent reply under `reply` instead of flattening `AgentReply` fields into the top level.
  - Uploaded photos are kept on disk (not deleted after the turn); `/admin/reset` does not delete them.
- Real run (2026-10-13, uvicorn on a temp DB, real models): seed -> `/chat` "What can I cook tonight in 30 minutes?" 12.4 s, 3 meals, trace `suggest_meals -> 5 candidates`, `output check -> ok`. Steps for the omelette: 3.9 s the first time, 0.24 s the second. `/chat` with `coffee.jpg` tagged pantry: 24 s, pantry marked scanned, but the trace shows the known reused-id retry (see Open issues).
- Next task must know: T3.2 reads `reply.meals` (full `Recipe` without steps) for the cards and calls `/recipe/{id}/steps` when one opens; `trace[].failed` for the warning colour; send photos as `images` + `locations` fields in the same order.
- Open issues: reused recipe ids across turns (existing issue, seen again).

**How to verify**
```
uv run pytest -q
uv run pytest tests/test_api.py -q
uv run uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```
Expected: `353 passed`; then `19 passed`; then the server logs `Uvicorn running on http://0.0.0.0:8000`.
Manual check: open http://localhost:8000/docs . Run `POST /admin/reset`, then `POST /admin/seed` (the response lists spinach with `"use_soon": true` and `scan_state` with only `fridge`). Run `POST /chat` with `session_id` = `test` and `message` = `What can I cook tonight?`: after about 10-20 s the response has `reply.message`, 1-3 `reply.meals`, a `trace` ending in `output check` -> `ok`, and the full `inventory`. Copy one meal `id` into `GET /recipe/{recipe_id}/steps`: the first call takes a few seconds and returns `steps`, the second is instant. Note: this uses the real `DB_PATH` (`data/app.db`); reset it afterwards with `POST /admin/reset` if you want an empty app.

### 2026-10-13 — T2.5 Scenario suite
- Built / changed:
  - `eval/scenarios.yaml` (new): the 10 scenarios of the plan. Named seed inventories (`demo` = the `try_recipes.py` fridge, `pasta_no_cream`, `pancakes`), one item per string `"name, category, qty[, place][, soon]"`. Scenario keys: `seed` (inventory, add, remove, scanned, preferences), `after: <id>` (reuse that scenario's store in a new session: scenario 7 builds on 6), `turns` (message, photos, `scan` before the turn, `new_session`). 21 expectation keys, documented at the top of the file (`tools_called` in order incl. `output check`, `first_tool`, `failed_check`, meal counts / minutes / `meals_valid` / `meals_must_not_contain`, shopping list and check-first contains / not / empty, `substitution_for`, `preference_saved`, `inventory_lacks`, `max_questions`, `message_matches`, `asks_for_photo`).
  - `eval/run_scenarios.py` (new): `load_suite` (rejects unknown expect keys and bad `after`), `seed_store`, `check_turn(expect, reply, trace, store) -> list[str]` (plain function; ingredient matching with `same_ingredient` or a whole word of a longer name, so "ricotta" matches "ricotta cheese"), `run_suite`. Options: `--only 4,10` (dependencies run too, unreported), `--repeat N`, `--jobs N` (scenario groups in parallel), `-v`. Prints one line per turn (latency, tools in order), the reply and trace of failed turns, a markdown table (passes over repeats, mean latency per turn), and saves JSON in `eval/results/scenarios_<time>.json`. Any exception in a turn is a failed turn, not a crash.
  - `tests/test_scenarios.py` (new, 10 tests, no network): the suite file loads and every seed is valid, `check_turn` pass/fail cases for Modes A and B, preferences and messages, dependency selection, `run_suite` with a fake `run_turn` (shared store via `after`, new session).
  - Prompt fix, `SUGGEST_PROMPT` in `app/tools/recipes.py` (scenario 3): the first run passed 9/10. With "creamy pasta" and no cream, the recipe model made "Parmesan Cream Pasta" with no cream in it (a misleading name, so no check failed). Two new rules: a dish name never names an ingredient that is not in the dish; when the request names a dish or style the inventory cannot make, the first candidate is the classic version with its missing ingredients marked essential, and only that one may need anything missing. Now the trace shows e.g. `! suggest_meals -> 5 candidates: 2 passed, 3 failed (Fettuccine Alfredo: missing: cream ...)` and the message says alfredo needs cream and offers the dishes that can be made.
  - `data/synonyms.json`: `ricotta cheese -> ricotta` (open issue from T2.1; scenario 4), `fettuccine`, `rigatoni`, `farfalle -> pasta` (seen in scenario 3).
- Results (real models: `deepseek-v4-pro` agent, `deepseek-flash` recipes and vision):

  | Run | Result | Notes |
  |---|---|---|
  | 1 (before the fix) | 9/10 | #3: no failed check ("cream pasta" without cream) |
  | 3 repeats, `--jobs 4` | 29/30 | #3 once: all 5 candidates needed cream, the agent answered Mode B (alfredo + buy cream); fixed by "only the first dish may need missing ingredients" |
  | #3 alone x5 after the 2nd fix | 5/5 | |
  | final, sequential | 9/10 | #2 failed on `ModelAPIError: Connection error` (network), then 2/2 on rerun |

  Sequential latency per turn: Mode A 13-21 s, Mode B 10-21 s, save preference 8 s, photo turns 9 s (one coffee photo).
- Decisions / deviations:
  - Scenario 1 expects `suggest_meals` then `output check`, not `validate_suggestion`: since T2.1b the candidates are validated inside `suggest_meals` and the final reply by the output validator (both in the trace).
  - Scenarios 8 and 9 use `tests/fixtures/coffee.jpg` (no eval photos yet), as allowed by the plan.
  - Scenario 10 checks only pasta (canned tomato depends on what `get_recipe` lists: it was in to-buy in 1 of 2 runs, fresh tomato in the other). The agent sometimes substitutes chicken for ground beef in bolognese (valid, a stretch; same as the open lasagna issue).
  - `--jobs` was added to shorten the edit-run loop (about 70 s instead of 3 min); it inflates latency.
- Next tasks must know: T3.1: handle `ModelAPIError` (see Open issues). T4.2: scenario 4 passed 4/4 runs here; the T4.2 check is `uv run python eval/run_scenarios.py --only 4 --repeat 3`. T4.3: `--only 7` runs 6 then 7. T5.2: per-turn latency is in the JSON (`usage`).
- Open issues: coffee photo in 8/9, latency variance, network errors (see Open issues).

**How to verify**
```
uv run pytest -q
uv run pytest tests/test_scenarios.py -q
uv run python eval/run_scenarios.py
```
Expected: `334 passed`; then `10 passed`; then (real models, about 3 min) one `[PASS]` / `[FAIL]` line per scenario with its tools in order, e.g. `ok turn 1: 12.8 s  tools: get_recipe > compute_missing > output check`, then a markdown table ending in `| | **total** | **10/10** | |` (at least 8/10 is the bar), and `saved eval\results\scenarios_<time>.json`. Dishes and latencies differ from run to run; a `FAIL: error: ModelAPIError` line is a network error, not the agent.
Manual check:
```
uv run python eval/run_scenarios.py --only 3 -v
```
Expected: `[PASS] #3 ...`, the message says the creamy classic needs cream and offers 1-3 dishes you can make now; under it the trace has a line starting with `! suggest_meals(` and showing `failed (Fettuccine Alfredo: missing: cream` (or a similar dish), then `- output check(...) -> ok`.

### 2026-10-13 — T2.3 Trace capture, T2.4 Terminal chat
- Built / changed:
  - `app/trace.py` (new, a plain function, no agent/store/model): `build_trace(messages, steps=None, recipes=None) -> list[ToolTraceItem]` walks a run's `new_messages()`, pairs each `ToolCallPart` with its `ToolReturnPart` / `RetryPromptPart` by tool call id, and writes `args_summary` / `result_summary` per tool (`args_summary()`, `result_summary()`, both <= 100 chars via `short()`). Examples: `update_inventory(remove egg, add chicken) -> removed 1, added 1`; `suggest_meals('quick' max 30 min) -> 5 candidates: 4 passed, 1 failed (Carbonara: missing: cream)`; `validate_suggestion(Carbonara) -> FAILED: missing: cream`; `compute_missing(Lasagna) -> to buy: ricotta; check first: pasta`. Recipe ids are shown as dish names (from `Deps.recipes`). A tool's `ModelRetry` -> `retry: ...`; args that failed validation -> `retry: invalid arguments` (no seconds: the tool never ran). Calls of the output tool `reply` become `output check` items: `ok`, `ok (fixed ...)` or `output check failed: ...` (the validator's verdict from the `check` step). `format_trace()` prints one line per item (`-` ok, `!` failed). Tool returns stored as dicts (history reloaded from the store) are summarized too.
  - `app/models.py`: `ToolTraceItem` gained `failed: bool = False` (a failed check, incl. a `suggest_meals` result with failed candidates, a retry or an error; for the warning colour in T4.4) and `seconds: float | None`; new `TurnUsage(latency_s, requests, tool_calls, input_tokens, output_tokens)`; `StepTiming.call_id` (tool call id, set by `TimedToolset` and the output validator) so the trace gets exact seconds per call.
  - `app/agent.py`: `TurnResult.trace` and `TurnResult.usage`; `OUTPUT_TOOL_NAME` / `OUTPUT_CHECK` now live in `app/trace.py` (imported, same names).
  - `scripts/chat.py` (new, T2.4): REPL on the real agent. `--session` (default `terminal`), `--db` (default `DB_PATH`; history persisted by `run_turn` in the store, so a restart with the same session continues), `--demo` (the in-memory demo inventory of `try_recipes.py`, nothing on disk changes), `--debug` (timing breakdown + full message list as JSON per run, and the DEBUG tool log). Commands: `/photo <path>... [fridge|freezer|pantry]` (attached to the next message; Enter alone sends the photos only), `/inventory`, `/new`, `/help`, `/quit`. Prints the message, meal cards (name, time, id, uses), substitutions, to buy, check first, questions, then `trace (N steps, latency, requests, tokens)` and the trace lines. `UnexpectedModelBehavior` / `UsageLimitExceeded` are printed and the REPL continues.
  - `scripts/try_agent.py` also prints the trace.
  - Tests: 324 pass (was 312). `tests/test_trace.py` (10: summaries, `build_trace` on hand-made messages incl. a bad-args retry, the trace of mocked Mode A runs with a failed output check, Mode B, a no-tool turn, history round trip), `tests/test_chat_script.py` (2: `/photo` parsing; one REPL session with a scripted model: photo sent with the next message only, history stored).
- Decisions / deviations:
  - The trace code is in `app/trace.py`, not inside `app/agent.py` (the CLAUDE.md layout puts trace capture in agent.py): a pure function is easier to test and to reuse in the API (T3.1) and the scenarios (T2.5).
  - A successful output check is also a trace item (`output check(...) -> ok`), not only failures: it shows the user that the final reply was checked by code.
  - Per-turn usage is returned (`TurnResult.usage`) and logged, not stored in the database; T5.2 reads it from the turn.
- Real-model run (2026-10-13, `scripts/chat.py --demo`): Mode A "under 30 minutes, kids" 10.1 s, trace `suggest_meals -> 5 candidates`, `output check -> ok`, 3 meals. Mode B "lasagna" 8.5 s: `get_recipe`, `compute_missing -> to buy: ground beef, ricotta, mozzarella, parmesan; check first: lasagna noodle`, cottage cheese for ricotta. Then `/photo tests/fixtures/coffee.jpg pantry` + Enter, 15.4 s: `recognize_inventory`, `! output check failed: unknown meal id(s) 00e1a2` (the agent reused the previous turn's lasagna id), `get_recipe`, `compute_missing`, `output check -> ok`; with the pantry scanned, `lasagna noodle` moved from check-first to to-buy. "The kids hated the eggplant" 3.4 s: `save_preference -> Already noted`.
- Next tasks must know: T2.5: `turn.trace` (tool names in order, `failed` flags) and `turn.usage`. T3.1: return `turn.trace` with the reply (`ToolTraceItem` is JSON-ready). T4.4: the collapsed sentence can be built from `ToolTraceItem.tool` / `failed`.
- Open issues: per-run recipe ids (see Open issues).

**How to verify**
```
uv run pytest -q
uv run pytest tests/test_trace.py tests/test_chat_script.py -q
uv run python scripts/chat.py --demo
```
Expected: `324 passed`; then `12 passed`; then `demo inventory (in memory) ...` and a `you>` prompt. Type `What can I cook tonight? Something under 30 minutes, the kids are eating.` (about 10 s): a one-line answer, up to 3 `[n] Dish (minutes, id ...)` lines, then `trace (2 steps, ...)` with `- suggest_meals(...) -> 5 candidates...` and `- output check(...) -> ok`. Type `I want to make lasagna`: `- get_recipe(lasagna)`, `- compute_missing(Lasagna) -> to buy: ...; check first: lasagna noodle`, a `to buy:` line and `check your pantry first: lasagna noodle`. Type `/quit` to leave.
Manual check: start `uv run python scripts/chat.py --demo` again, type `/photo tests/fixtures/coffee.jpg pantry`, then press Enter on the empty `you (1 photo attached)>` prompt; the trace starts with `- recognize_inventory() -> Recognized 1 items in 1 photo(s) of: pantry.`, and `/inventory` then shows `pantry (scanned <today>)`. Then run `uv run python scripts/chat.py --demo --debug` and type `thanks`: after the trace you see a `timing:` block and a `messages:` JSON list.

### 2026-10-13 — T2.2 Output validator (+ essential-flag fix)
- Built / changed:
  - `app/tools/checks.py`: `check_reply(reply, recipes, inventory, preferences, scan_state) -> ReplyCheck(reply, problems, fixes)`, a plain function (no LLM, no agent) with the whole validator logic; `MAX_MEALS = MAX_QUESTIONS = 3`. Rules: every `meal_ids` id must be in the run's cache (unknown -> problem listing the known `id (name)`s); at most 3 meals / 3 questions; every `Substitution.use_instead` must be in the inventory (normalized); **Mode A** (no `shopping_list`, `check_first` or `substitutions`) -> each meal re-run through `validate_suggestion` on the current inventory, failure text like "Kung pao chicken needs peanut, not in inventory. Replace it or move it to a Mode B answer with a shopping list"; **Mode B** (any of the three present) -> `shopping_list` / `check_first` recomputed from `compute_missing` of the meals minus the substituted items, and replaced in code (`fixes` records the difference). Ids are deduped.
  - `app/agent.py`: `@agent.output_validator check_output` calls `check_reply` with `ctx.deps.recipes` and the store; problems -> `ModelRetry("Your reply was not sent. Fix it and call reply again: ...")`; returns the fixed reply. Every check appends `StepTiming(kind="check", name="output check")` to `Deps.steps` with `detail` = `ok`, `ok (fixed shopping_list [...] -> [...])` or `output check failed: ...` (for the T2.3 trace). `fill_meals` still fills `meals` after the run. `app/models.py`: `StepTiming.kind` gained `"check"`.
  - Essential flags: `INGREDIENT_RULES` (used by both recipe prompts) now defines essential = main protein, the base (pasta, rice, bread, dough, tortilla) and every ingredient named in the dish; optional = garnishes, decorative herbs, toppings, "to taste"; three short examples (lasagna, chicken fried rice, spinach omelette). Code safety rule in `recipes.py`: `dish_name_ingredients(*names)` (canonical names of every 1-3 word phrase of the dish name) and `force_named_essential(ingredients, *names)`, applied in `_clean` after `normalize` to the model's dish name and, in `get_recipe`, also to the dish the user asked for ("spaghetti with ground beef" forces pasta + ground beef). Whole phrases only: "Eggplant parmesan" does not force egg.
  - Tests: 312 pass (was 285). `test_checks.py` +13 (`check_reply`), `test_agent.py` +5 (mocked model: bad id -> retry -> valid reply; cached omelette fails after "out of eggs" -> retry -> reply without it; substitute not in inventory -> retry; Mode B lists fixed in code without a retry; gives up with `UnexpectedModelBehavior` after the retry limit), `test_recipes.py` +11 (prompt, `dish_name_ingredients`, `force_named_essential`, both tools).
- Decisions / deviations:
  - Mode B is detected by the reply's content (a shopping list, check_first or substitutions), not only by `shopping_list` as in the plan: a Mode B answer with nothing to buy but something to check is still Mode B. A Mode B reply with all three empty is checked as Mode A, so a "forgotten" shopping list becomes a retry instead of a silently wrong answer.
  - In Mode B the lists are the union over all meals in the reply (normally one dish). Preference violations are not enforced in Mode B (the user asked for that dish); `get_recipe` already drops optional extras that conflict.
  - Retry limit unchanged: `retries=2` on the agent (also the output retries); a third failing reply raises `UnexpectedModelBehavior` (T3.1 decides what to show).
- Real-model check (2026-10-13, demo store, pantry not scanned, `scripts/try_agent.py "I want to make lasagna"`, 3 runs, 8.7-8.9 s each, output check `ok` with no retries and no fixes):

  | Run | compute_missing: missing_essential | substitutions | to buy | check first |
  |---|---|---|---|---|
  | 1 | ground beef, ricotta, mozzarella, parmesan | cottage cheese for ricotta, chicken for ground beef | mozzarella, parmesan | lasagna noodle |
  | 2 | ground beef, ricotta, mozzarella, parmesan | cottage cheese for ricotta | ground beef, mozzarella, parmesan | lasagna noodle |
  | 3 | ground beef, ricotta, mozzarella, parmesan | cottage cheese for ricotta | ground beef, mozzarella, parmesan | lasagna noodle |

  Basil was the only optional ingredient (runs 1-2). Before the fix, one T2.1b run had ground beef and parmesan optional.
- Next tasks must know: T2.3 builds the trace from `TurnResult.steps` (kind `check` = the validator) or from `RetryPromptPart(tool_name="reply")` in `turn.result.new_messages()`. T4.2: the message prose is not checked (see Open issues). T3.1: `run_turn` can raise `UnexpectedModelBehavior` after 3 bad replies.
- Open issues: Mode B prose vs lists, chicken-for-beef substitution (see Open issues).

**How to verify**
```
uv run pytest -q
uv run pytest tests/test_agent.py tests/test_checks.py tests/test_recipes.py -q
uv run python scripts/try_agent.py "I want to make lasagna"
```
Expected: `312 passed`; then `116 passed`; then (real models, about 10 s) `-> get_recipe`, `-> compute_missing`, `-> reply`, a `timing:` block whose last step before the total is `check  output check  ok`, `meal: Lasagna ...`, `substitutions: cottage cheese for ricotta`, and `to buy: [...]` containing `mozzarella` and `parmesan` (and `ground beef` unless the agent substituted it), with `check your pantry first: ['lasagna noodle']`. No `!! retry` line is expected; if one appears it reads `!! retry: Your reply was not sent. Fix it ...` and the next `-> reply` fixes it.
Manual check:
```
uv run pytest tests/test_agent.py -q -k validator -rA
uv run python -c "from app.tools.recipes import force_named_essential as f; from app.models import Ingredient as I; print(f([I(name='spinach',amount='1',essential=False,category='vegetable'), I(name='chive',amount='1',essential=False,category='vegetable')], 'Spinach omelette'))"
```
The first ends with `5 passed` (the validator tests, each listed as `PASSED`). The second prints spinach with `essential=True` and chive still `essential=False`.

### 2026-10-13 — T2.1b Latency fix (before T2.2)
- Why: Mode A turns took 44-80 s with `deepseek-v4-pro` (target 25 s). Measured first, then fixed, then measured again.
- Built / changed:
  - `app/timing.py` (new): `TimedModel` (a `WrapperModel` that appends a `StepTiming` after every request, streaming included) and `TimedToolset` (a `WrapperToolset` that times every tool call, retries included); `result_summary()` / `response_detail()` make the one-line summaries (T2.3 can reuse them); `format_steps()` prints the breakdown. `app/models.py`: `StepTiming`.
  - `app/agent.py`: tools now live in a module-level `FunctionToolset` (`toolset`) wrapped in `TimedToolset`; `run_turn` wraps the agent model in `TimedModel("agent <name>")`, the recipe/vision models are wrapped per call (`recipe <name>`, `vision <name>`); `Deps.steps` and `TurnResult.steps` carry the timings. `scripts/try_agent.py` prints them.
  - **Reply by reference:** `Recipe.id` (6 hex chars, `new_recipe_id()`), `AgentReply.meal_ids` (what the model fills) and `AgentReply.meals` (`SkipJsonSchema`, hidden from the model, filled by `fill_meals()` in `run_turn` from `Deps.recipes`, now keyed by id; unknown ids are dropped with a warning until T2.2 turns them into a `ModelRetry`). `compute_missing(recipe_id)` / `validate_suggestion(recipe_id)` take the id (a dish name still works as a fallback). `get_recipe` returns a `MealCandidate` (id, name, time, ingredient strings, uses) instead of the `Recipe`.
  - **Validation inside the tool:** `checks.check_candidates()` runs `validate_suggestion` on every candidate; the `suggest_meals` tool returns `SuggestResult(passed, failed)` with the reason per failed dish. `validate_suggestion` stays a tool (Mode B dishes, re-checks after an inventory change). Instructions rules 3, 4 and 9 rewritten for ids.
  - **Steps on demand:** `RecipeDraft` has no `steps`; `SUGGEST_PROMPT` / `RECIPE_PROMPT` say "do not write cooking steps"; `Recipe.steps` defaults to `[]`. New `recipes.get_steps(store, recipe_id, model=None)` (prompt `STEPS_PROMPT`, output `StepsDraft`) generates the steps once and stores them; `KeyError` for an unknown id. Every recipe a tool returns is saved by `store.save_recipe()` (new `recipes` table, `load_recipe(id)`), so the API can call `get_steps` after the run.
  - **Thinking off:** `config.AGENT_THINKING` / `RECIPE_THINKING` (env, default `off`), applied as `model_settings=thinking_settings(...)` (`app/llm.py`) in `run_turn` and in the recipe calls. pydantic-ai sends `reasoning_effort: none`; DeepSeek accepts it for both models (checked by hand: the thinking parts disappear).
  - Tests: 285 pass (was 273). Updated `test_agent.py` (ids, `SuggestResult`, `fill_meals`, timing steps, schema hides `meals`), `test_recipes.py` (ids, no steps, `get_steps` once-then-stored, unknown id, empty steps), `test_checks.py` (`check_candidates`), `test_models.py`, `test_store.py` (recipes table).
- Measurements (real models, demo inventory, `scripts/try_agent.py`; the baseline run of the day was 44 s, earlier runs 50-80 s):

  | Step | Before | After (thinking off) | After (agent thinking on) |
  |---|---|---|---|
  | agent call 1 (plan → suggest_meals) | 3.0 s (337 chars thinking) | 2.3 s | 2.9 s |
  | recipe model inside suggest_meals | 21.4 s (5 full recipes, 3,937 out tokens, 6,435 chars thinking) | 5.7 s (1,453 out tokens) | 5.5 s |
  | agent call 2 (validate_suggestion x4) | 4.3 s | gone (checked inside the tool) | gone |
  | agent call 3 (reply) | 14.8 s (1,641 out tokens: 3 recipes copied) | 2.6 s (86 out tokens: 3 ids) | 3.4 s |
  | **Mode A turn** | **44.2 s** | **11.4 s** | **12.6 s** |
  | "out of eggs, 20 minutes" | 79 s (T2.1) | 14.4 s | 13.4 s |
  | Mode B lasagna | 35-47 s (T2.1) | 9.3 s | 10.0 s |
  | "kids hated the eggplant" | 7 s (T2.1) | 3.1 s | 5.2 s |
  | `get_steps` (first open of a card) | n/a | 2.6 s, then 0 s from the store | |

- Thinking on vs off for `AGENT_MODEL` (same 4 turns, thinking on only for the agent): identical tool choices in all 4 turns (`suggest_meals` → `reply`; `update_inventory` → `suggest_meals` → `reply`; `get_recipe` → `compute_missing` → `reply`; `save_preference` → `reply`), same `meal_ids` discipline, no retries either way. Off is 0.6-2 s faster per agent call. Decision: **off** for both models (`.env.example`). The recipe model's thinking was the single biggest cost (6,435 chars before each answer).
- Decisions / deviations: `get_recipe` is also step-less (Mode B cards get steps from `get_steps` too); ids are random 6-hex (unique across runs, so `GET /recipe/{id}/steps` is unambiguous); a dish name is still accepted by `compute_missing` / `validate_suggestion` as a fallback; `n` stays 5 (cheap now, gives the agent fallbacks when a candidate fails).
- Next tasks must know: T2.2 validates `meal_ids` against `ctx.deps.recipes` and re-checks Mode A meals from the cache; `fill_meals` already exists. T2.3: `turn.steps` has every model/tool call with seconds; `app/timing.py` has `result_summary`. T3.1: `GET /recipe/{id}/steps` → `recipes.get_steps(store, id)`; `AgentReply.meals` is filled when `run_turn` returns. T3.2: cards show name/time/ingredients; steps load on open.
- Open issues: Mode B substitution in prose / `essential` honesty (see Open issues).

**How to verify**
```
uv run pytest -q
uv run python scripts/try_agent.py
```
Expected: `285 passed`. Then (real models, ~25 s for both turns) each turn ends with a `timing:` block, one line per model call and tool call with seconds, e.g. `recipe deepseek-flash` 4-8 s, `suggest_meals ... passed 5: ...`, and a last line like `11.3s  total (4.9s agent model + 6.4s tools)`. Turn 1 (Mode A) is 10-15 s, has no `validate_suggestion` line and no `thinking` in the agent lines; the `reply` call has under ~120 output tokens and its args show `"meal_ids": [...]`. Turn 2 (lasagna) is about 10 s with `get_recipe` → `compute_missing` → `reply`.
Manual check (cmd.exe):
```
set AGENT_THINKING=on
uv run python scripts/try_agent.py "What can I cook tonight?"
set AGENT_THINKING=off
uv run python -c "import asyncio,sys; sys.path.insert(0,'scripts'); from try_recipes import demo_store; from app.tools.recipes import suggest_meals, get_steps; s=demo_store(); m=asyncio.run(suggest_meals(s,n=1))[0]; print(m.steps); print(asyncio.run(get_steps(s,m.id)).steps)"
```
The first run shows `thinking N chars` on the `agent deepseek-v4-pro` lines with the same tool sequence, 1-2 s slower. The last command prints `[]` (no steps in the candidate) and then a list of 3-8 cooking steps.

### 2026-10-13 — T2.1 Agent
- Built: `app/agent.py` (`agent`, `Deps`, `INSTRUCTIONS`, `USAGE_LIMITS`, `OUTPUT_TOOL_NAME`, 8 tool wrappers, `user_prompt`, `run_turn` -> `TurnResult`), `tests/test_agent.py` (14 tests, scripted `FunctionModel`s, no network; 273 total pass), `scripts/try_agent.py` (manual real-model run on the demo inventory of `try_recipes.py`). `app/store.py`: `sqlite3.connect(..., check_same_thread=False)`.
- API: `await run_turn(store, session_id, message="", images=None, *, model=None, recipe_model=None, vision_model=None) -> TurnResult(reply: AgentReply, result: AgentRunResult, latency_s)`. `images` = `[(Path, Location)]`. Loads the session history from the store, runs, saves `all_messages()` back. `model=None` -> `agent_model()`; tests pass `FunctionModel`s. Raises `ValueError` on an empty turn, `UsageLimitExceeded` after 10 tool calls / 16 requests (not caught: the API in T3.1 decides what to show).
- Design:
  - `agent = Agent(None, deps_type=Deps, output_type=ToolOutput(AgentReply, name="reply"), retries=2)`; the model is passed at run time so importing the module needs no key.
  - Dynamic `@agent.instructions`: PRODUCT §5 rules (12 numbered rules, module constant `INSTRUCTIONS`) + today's date + `inventory_summary` + `preferences_summary` + "The user attached N photos (places)" when there are photos. The user turn gets the prefix `[user attached N photos (fridge, pantry)]`.
  - `Deps(store, images, recipes, recipe_model, vision_model)`. `Deps.recipes` is a per-run cache of every `Recipe` returned by `suggest_meals` / `get_recipe`, by dish name.
  - **Deviation:** `compute_missing(dish: str)` and `validate_suggestion(dish: str)` take a dish name and look the recipe up in `Deps.recipes` (case/space-insensitive) instead of taking a whole `Recipe` (fewer tokens, no copy errors). Unknown dish -> `ModelRetry` listing the known dishes. `suggest_meals` takes flat `request`, `max_minutes`, `n`, `exclude` instead of a `Constraints` object (built inside).
  - `recognize_inventory()` takes no arguments: photos from `Deps.images`, then `merge_recognized`, clears `Deps.images`, returns found/uncertain counts and the new inventory. Without photos it returns a message telling the agent to ask for them.
  - `get_inventory` / `update_inventory` return the `inventory_summary` text, not `InventoryItem` lists (compact for the model; the API reads the inventory from the store). `save_preference` returns `Saved: ...` or `Already noted: ...` (same id as an existing preference).
  - All tools and the instructions function are `async`: pydantic-ai runs sync ones in a worker thread, which broke the SQLite connection (thread check). `check_same_thread=False` in the store is the second safety net (FastAPI handlers in T3.1).
  - **Explicit `ToolOutput`:** with the default "auto" output mode pydantic-ai 2.55 also tries to parse a plain-text answer as JSON, and the model got an "Invalid JSON" retry it read as a system error (one real turn failed after 2 retries). With `ToolOutput` the retry says "include your response in a tool call"; after that change, 8 real turns (incl. "thanks!", "ok cool") all ended in a `reply` call with no retry. The output tool is named `reply` (T2.3 trace should skip it: `OUTPUT_TOOL_NAME`).
  - `LOG_LEVEL=DEBUG` logs each tool call (`tool name(args) -> result summary`); every turn logs latency, requests, tool calls and tokens at INFO.
- Real-model runs (2026-10-13, `deepseek-v4-pro` + `deepseek-flash`): Mode A ("under 30 minutes, kids") -> `suggest_meals` then `validate_suggestion` x5 (all ok) -> 3 meals, says a pantry photo would give more options; 50 s. "we're out of eggs, 20 minutes" -> `update_inventory(remove egg)` first, 3 egg-free meals <= 20 min; 79 s. Mode B lasagna -> `get_recipe`, `compute_missing`, recipe in `meals`, substitutions cottage cheese->ricotta and cheddar->mozzarella, to buy `ground beef, parmesan`, check first `lasagna noodle, crushed tomato, tomato paste`; 35-47 s. Pancakes -> empty shopping list, "no shopping needed"; 17 s. "kids hated the eggplant" -> `save_preference` (dedupe reported "Already noted"); 7 s.
- Next tasks must know: T2.2's `@agent.output_validator` gets `AgentReply` and can use `ctx.deps.recipes` to re-check / replace meals by name; the validator should also handle the Mode B recipe in `meals`. T2.3: new messages are in `turn.result.new_messages()`, usage in `turn.result.usage`, skip `OUTPUT_TOOL_NAME` tool calls. T2.4: `run_turn(store, session_id, text, images)`. T3.1: `run_turn` saves history itself; read inventory/scan state from the store after the turn.
- Open issues: Mode A latency, synonym gaps (see Open issues).

**How to verify**
```
uv run pytest -q
uv run pytest tests/test_agent.py -q
uv run python scripts/try_agent.py
```
Expected: `273 passed`; then `14 passed`; then (real models, 1.5-2.5 min) two turns. Turn 1 shows `-> suggest_meals(...)`, several `-> validate_suggestion(...)` lines, then `-> reply(...)`, a one-line message and 3 `meal:` lines, none with eggplant. Turn 2 shows `-> get_recipe`, `-> compute_missing`, `-> reply`, a `meal: ... Lasagna` line, `substitutions: cottage cheese for ricotta ...`, and `to buy: [...] check your pantry first: ['lasagna noodle', ...]`. Dishes differ from run to run. No `!! retry` lines are expected.
Manual check: `uv run python scripts/try_agent.py "The kids hated the eggplant last time" "thanks!"`: turn 1 calls `save_preference` and the message confirms it; turn 2 is a one-line reply with no tool calls and no retry.

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
