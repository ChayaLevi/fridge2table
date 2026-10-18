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
- [~] T3.2 Web page (page built and checked in a headless phone-size browser; the human's check in a browser is open)
- [ ] T3.3 First real-fridge run + internal demo 🧑 (waiting: the human is away from home; P4 started meanwhile, 2026-10-14)
- [x] T4.1 Proactive opening
- [x] T4.2 Substitutions in Mode B
- [x] T4.3 Preferences end to end
- [~] T4.4 Trace UI polish (built; waiting for the human to confirm it reads well on a phone)
- [x] T4.5 Cooking mode switch (added 2026-10-15 at the human's request)
- [ ] T5.1 Vision model comparison
- [x] T5.2 Latency (numbers in `eval/RESULTS.md`)
- [ ] T5.3 Real user run #1 + decision point 🧑
- [ ] P6 Fixes (+ T6.1 if the decision point passed; T6.2 done early, 2026-10-18)
- [ ] P7 Freeze 🧑

## Next up

- **Open: the human confirms T4.4** (the trace line under an agent message, collapsed and expanded, on a phone or in a desktop browser in phone mode). **Next task: T5.1 Vision model comparison** (🧑 needs the eval photos in `eval/fridges/`, still missing). T5.2 is done (2026-10-15). After T5.1: T5.3, the real user run (🧑).
- **Waiting on the human:** T3.3 (a real fridge run and the internal demo; the human is away from home). The human used the page in a desktop browser on 2026-10-14 ("works great", "looks great") and asked for the changes logged below (panel edits, staples, scope, gallery, rescan review, centered recipe with the shopping list, steps with substitutes, amounts, Start over, History, design round); T3.2 stays `[~]` until it is tried on a phone. How to show it to the team lead: see "Demo on another phone" under Decisions.
- **Blocked on the human:** eval photos in `eval/fridges/<household>_<place>/` (4-6 sets, >=2 fridge, >=2 pantry, each with `labels.json`) for T0.5 and the open part of T1.4. The folders `home1_fridge` and `home1_pantry` exist locally but are empty. When they arrive: run `eval/run_vision_eval.py` for tiles 1, 2 and 4, set `VISION_TILES` in `.env.example` to the best one, report the numbers, tick T1.4.
- The DeepSeek key is in `.env` (since 2026-10-12), so real-model steps are not blocked by keys.
- State: 449 tests pass (2026-10-18, after T6.2 Copy list / Download .txt). Scenario suite: 14 scenarios (11 = scope, 12 = opening, added 2026-10-14; 13 = Shopping OK, 14 = bare kitchen and the Shopping OK button, added 2026-10-15), 14/14 on real models. The FastAPI app (`app/api.py`) serves all T3.1 routes, the proactive opening (T4.1) and the chat page (`app/static/index.html`, T3.2).

## Current model settings

Only Chinese models (see `docs/PRODUCT.md` §9). All via the DeepSeek API (`DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL=https://api.deepseek.com`); IDs verified in T0.4 (2026-10-12) against `GET /models` and DeepSeek's pricing page.

- VISION_MODEL: `deepseek-flash` (DeepSeek-V4.1-Flash, the only DeepSeek model that accepts images; temporary, swap to Qwen3.8 Max once that license is approved; decided on our photos in T1.4/T5.1)
- AGENT_MODEL: `deepseek-v4-pro` (text only; kept after T5.2: `deepseek-flash` is 2x faster but broke the "do not swap the defining ingredient" rule, see `eval/RESULTS.md`; it is the fallback if the demo-day API is slow)
- RECIPE_MODEL: `deepseek-flash`
- `deepseek-v4-flash` and `deepseek-v4-flash-vision-exp` are retired aliases: still accepted, served by `deepseek-flash`.
- VISION_TILES: 1 (best value chosen in T1.4)
- AGENT_THINKING / RECIPE_THINKING: `off` (2026-10-13; DeepSeek V4 thinks by default; off = `reasoning_effort: none` via pydantic-ai's `thinking=False`)

## Decisions and deviations from the plan

- **Demo on another phone (2026-10-14, for T3.3; nothing to package):** the app is a website served from the human's computer. `uv run uvicorn app.api:app --host 0.0.0.0 --port 8000` (no `--reload` for a demo), find the computer's address with `ipconfig` (IPv4 of the Wi-Fi adapter), and open `http://<that IP>:8000` on the phone on the same Wi-Fi (allow Python in the Windows firewall prompt for private networks; "Add to Home Screen" makes it look like an app). The computer must stay on (the DeepSeek key is in its `.env`). If the company network isolates devices, use the human's phone hotspot for both the computer and the other phone. A public tunnel (cloudflared, ngrok) was not set up: no login, the key's cost, company policy; only on an explicit decision. Offered, not built: a start script printing the phone address (optionally a QR code, needs the `qrcode` dependency) and README run notes.
- ~~One household, kept (2026-10-14)~~ **Superseded 2026-10-18 (the human's decision): one household per browser**, so a public link gives every visitor their own kitchen. A `household` cookie (32 hex chars, set by `/` or by the first API call) picks the SQLite file `HOUSEHOLD_DIR/<id>.db` (default `data/households/`, git-ignored). No login: a phone and a computer are two households, and clearing the browser starts a new one. `DB_PATH` (`data/app.db`) is now used only by the scripts and evals; the old shared web data stays there unused. Uploads and dish photos stay shared folders (file names are unique ids).

- ~~Model defaults were provisional Gemini/Claude strings~~ (superseded by the DeepSeek switch and T0.4; model values are bare DeepSeek IDs, see "Current model settings").
- Extras beyond the plan (small): `.gitignore`, `pytest.ini` (asyncio_mode=auto), `httpx` dev dependency (needed by FastAPI TestClient), `LOG_LEVEL`/`LOGFIRE_TOKEN` in `.env.example` (CLAUDE.md debugging aids).
- `data/synonyms.json` has 115 entries (112 + 3 added in the T1.1 redo) (flat map, no chains; a test enforces that targets are canonical). Ambiguous keys like bare `pepper` were left out on purpose.
- `InventoryChange` ops: add | remove | set_qty | set_use_soon | rename | **add_staple** | **confirm** (2026-10-14) (added 2026-10-14 at the human's request: staples of the user's own, table `custom_staples`). Fields: `op`, `name`, optional `display_name`, `category`, `location`, `qty_level`, `use_soon`, `new_name`.
- 2026-10-12 (later): PLAN/PRODUCT were updated (pantry coverage). T0.2 re-done: added `ScanState`, `PANTRY_CATEGORIES`, `Ingredient.category`, `MissingReport.check_first`, `AgentReply.check_first`, extended category list. Tests now 6 pass. T0.1/T0.3 unaffected. T0.5 now asks for 4–6 sets (≥2 fridge, ≥2 pantry), folders `<household>_<place>`.
- Order change (user request, 2026-10-12): the human has no API keys/photos yet, so T0.4 is deferred and P1/P2 are built with mocked models. T0.4, the real run of T1.4 and T1.6, and T2.5 wait for keys/photos.
- Repo was not a git repo; `git init` done in T0.1.

## Open issues

- (T5.2, 2026-10-15) The DeepSeek API's speed changes over the day: one `deepseek-v4-pro` agent call took about 6 s at 12:05 and 2-2.5 s at 12:30. All targets hold in both, but check with `uv run python eval/run_latency.py --only mode_a,mode_b` before the demo.
- (T4.5 / T5.2, 2026-10-15) PRODUCT §10 asks that "at least once in the demo, the trace shows the agent fixing a failed suggestion". Since T4.5, Only what I have no longer proposes the classic dish with missing items, so failed candidates are rarer (scenario 3 no longer shows one). They still happen (an unscanned pantry, a too-long Shopping OK list, an output-check retry), but plan a demo step that shows one (e.g. "creamy pasta" with the pantry not scanned), or ask the human whether to bring the classic-first candidate back as a trace-only failure.

- ~~(2026-10-14) Recipe steps ignored the substitutions ("mix the ricotta" with cottage cheese as the substitute)~~ Fixed the same day: the page sends the reply's substitutions to `GET /recipe/{id}/steps?sub=...`.
- ~~(T3.2) Network loss on 2026-10-14~~ Resolved the same day: the app's `ModelAPIError: Connection error` was a real outage, gone later. Note: `curl` on this machine still fails with `CRYPT_E_NO_REVOCATION_CHECK` (Windows schannel cannot reach the certificate revocation server); that is curl only, Python (httpx) connects fine. To test the API connection, use `uv run python -c "import httpx; print(httpx.get('https://api.deepseek.com/models').status_code)"` (401 without a key = reachable), not curl.
- (T3.2) Real Mode A replies said "a pantry photo would give more options" right after a pantry photo was scanned (2 of 2 runs, the pantry photo had only coffee). Agent prose only; rule 5 in `INSTRUCTIONS` could say "only while the pantry is NOT SCANNED" more firmly. Revisit in T3.3 / P6.
- (T2.5) Scenarios 8 and 9 use `tests/fixtures/coffee.jpg` (one coffee photo) because `eval/fridges` is still empty; swap in a real eval set when it exists (`photos:` in `eval/scenarios.yaml`).
- (T2.5) Turn latency varies with the API: the same Mode A turn took 11 s and 21 s on the same day, sequentially. With `--jobs 4` turns take 20-36 s (parallel load), so use `--jobs 1` for latency numbers (T5.2).
- (T2.5) `ModelAPIError: Connection error` happened once in about 45 real turns; `run_turn` does not retry it. Since T3.1 `/chat` returns 503 with "The model service did not answer. Please try again."
- ~~(T2.4) Recipe ids are per run: reusing an old id cost an output-check retry~~ Fixed 2026-10-14 (T4.1): each run preloads the recipes of the session's last reply (`last_reply_recipes`), still re-validated by the output check. Ids from older replies still get the retry.
- ~~(T2.1) Mode A turn takes 50-80 s~~ Fixed 2026-10-13 (T2.1b): Mode A 11-14 s, Mode B 9-10 s. See the T2.1b log entry.
- ~~(T2.1b, for T4.2) Mode B prose contradicted the code-fixed lists, and substitutes appeared only in the message~~ Fixed 2026-10-14 (T4.2): the output check rejects a Mode B message that names items of To buy / Check first; the prompt asks for one sentence with only the substitution pairs and no counts. Still possible: the message names only some of the substitutions (seen once: cheddar for mozzarella listed but not mentioned); not a contradiction.
- ~~(T2.1b) `deepseek-flash` marked ground beef / parmesan optional in lasagna~~ Fixed 2026-10-13 (T2.2): essential defined with examples in `INGREDIENT_RULES` + code rule `force_named_essential`. 3/3 real lasagna runs had all four essentials.
- (T2.2) One real lasagna run substituted chicken for ground beef. T4.2 added "do not swap the ingredient that defines the dish" to rule 4; not seen in the 11 Mode B runs after it (prompt only, not checked by code).
- (T2.1) Synonym gaps seen in real Mode B runs: ~~`ricotta cheese` != `ricotta`~~ (fixed in T2.5), `crushed tomato` / `tomato paste` are separate names (both correct but noisy in `check_first`); `lasagna noodle` vs `pasta` as before.
- ~~(T1.6) `suggest_meals` takes ~28 s~~ Fixed 2026-10-13: 5-7 s without steps and without thinking (`get_recipe` 2-3 s).
- (T1.6) `lasagna noodle` does not normalize to `pasta` (no synonym), so plain pasta in the inventory does not cover lasagna sheets. Arguably right; revisit if Mode B looks wrong in scenarios.

- (T0.4) The human's `.env` still sets `VISION_MODEL=deepseek-v4-flash-vision-exp` / `RECIPE_MODEL=deepseek-v4-flash` (retired aliases, still served by `deepseek-flash`). Change both to `deepseek-flash`.
- (T0.4) `CLAUDE.md`, `docs/PRODUCT.md` §9 and `docs/PLAN.md` still name the old model IDs; the human should update them or confirm the new defaults.
- (2026-10-15, the human's question) **Named dish in Only what I have:** "I want to make a birthday cake" in 🏠 mode answers with a shopping list (powdered sugar). That is the T4.5 spec (a named dish gets its list in both modes), but the human found it surprising. Offered, waiting for a decision: (a) in home mode the agent first looks for a substitute from the inventory (powdered sugar from blended sugar), (b) in home mode it also offers a dish that needs nothing.
- (T0.5/T1.4) No eval photos yet: `eval/fridges/home1_fridge` and `home1_pantry` are empty. T1.4's "Done when" (first table on the real eval set for tiles 1, 2, 4; best `VISION_TILES`; recall vs 70%) is still open.

## Log

### 2026-10-18 — Inventory panel: add at the top, search, a real reset button (the human's request)

- Built: `app/static/index.html` only.
  - The "Add to …" field now sits at the top of each place (and of Staples), under the hint, not under the list. An item added there shows first in its place, newest on top (`state.recentAdds`, matched by the typed name; cleared when the panel opens again, then the stored order is back).
  - A search box under the panel header (`#invSearch`): matches display name or canonical name, case-insensitive. While searching: only matching items, grouped by place (staples too), places with no match hidden, no add fields or reset; "No items match …" when nothing matches. Esc clears the search (a second Esc closes the panel). Opening the panel clears it.
  - "Start over" is a full-width button (`.startbtn`, orange) instead of an underlined link; the two-step confirm is unchanged.
  - Layout fix: the panel body is the only scroller (`flex: 1; min-height: 0`), the search bar has its own bottom edge.
- Checked in headless Edge 390x844 (a separate HOUSEHOLD_DIR in the scratchpad): yogurt added after milk/eggs/butter/cheddar showed first; "che" showed only cheddar; "zzz" showed the empty message; the reset button at the bottom; no page errors. `uv run pytest -q` 449 passed.

**How to verify**
```
uv run pytest -q
uv run uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```
Expected: `449 passed`; then the server starts.
Manual check: open http://localhost:8000, open Inventory, type an item in "Add to fridge…" and press Enter: it shows first in Fridge, right under the field. Type part of a name in the search box: only matching items show. At the bottom, "🗑 Clear the inventory and start over" is a button; tapping it asks for confirmation.

### 2026-10-18 — T6.2 Share shopping list (done early, the human's request)

- Why: the human wants the shopping list to leave the app. Options and effort (copy, WhatsApp, SMS/email, share sheet, .txt, QR, link, Todoist, WeChat) were written up for the team lead in a proposal outside the repo; the human chose copy + download now.
- Built: `app/static/index.html` only. Under the shopping-list block (in the chat and in the recipe window), when there is something to buy or check: **📋 Copy list** (shows "✓ Copied" for 2 s, or "Couldn't copy") and **⬇️ Download .txt** (`shopping-list-<dish>.txt`). Text: `Shopping list: <dish>`, then "To buy:" and "Check your pantry first:", one `- item (amount)` per line; substitutions are left out (nothing to buy). Functions `shopText`, `shopActions`, `copyText`, `downloadText`.
- Deviation from the plan: T6.2 asked for Copy list only and was a P6 stretch; done now, plus the download.
- Next task must know: `navigator.clipboard` exists only on HTTPS and localhost. Over the home network's `http://<IP>:8000` the copy uses the old `execCommand("copy")` on a hidden text field. Both paths were checked.
- Not covered: in Shopping OK with several cards there is no combined block, so no buttons under the chat message; each card's recipe window has its own list and buttons.
- Checked in headless Edge 390x844 with a rendered Mode B reply (ricotta to buy, pasta to check): on `localhost` the clipboard got the list; on `http://192.168.0.100:8765` (not a secure context) the fallback copied the same text; the label went "✓ Copied" and back; the download saved `shopping-list-lasagna.txt` with the same text. No page errors. No JS tests (the page has none); `uv run pytest -q` 449 passed.

**How to verify**
```
uv run pytest -q
```
Expected: `449 passed`.
```
uv run uvicorn app.api:app --host 0.0.0.0 --port 8000
```
Manual check: open `http://localhost:8000` (and on the phone `http://<computer IP>:8000`), ask "I want to make lasagna". Under "To buy" / "Check your pantry first" tap **📋 Copy list**: the button reads "✓ Copied"; paste in a chat or notes app and the list appears, one item per line. Tap **⬇️ Download .txt**: a file `shopping-list-<dish>.txt` with the same text is saved. Open the recipe: the same two buttons sit under its list.

### 2026-10-18 — One household per browser (the human's request, for a public link)

- Why: the human wants to send a public link (Render) where each visitor has their own inventory.
- Built: `app/api.py`: `household_id()` reads or sets the `household` cookie (httponly, samesite=lax, 10 years; a malformed value gets a new id, so no path tricks), `get_store()` opens one `Store` per household (`config.HOUSEHOLD_DIR/<id>.db`, cached, under a lock), lifespan closes them all; `/` sets the cookie so the page's first parallel requests share one household. `app/config.py`: `HOUSEHOLD_DIR`. `.env.example`, `.gitignore`. Tests: `tests/test_households.py` (4). The page, the agent and the tools are unchanged.
- Admin routes (`/admin/seed`, `/admin/reset`) now act on the caller's household only.
- Deploy notes (not done here; the human pushes): Render web service, build `pip install uv && uv sync --frozen`, start `uv run uvicorn app.api:app --host 0.0.0.0 --port $PORT`, env vars from `.env` plus `PYTHON_VERSION=3.12.7`. On the free plan the disk is wiped on every deploy and restart, so all households are lost; and every visitor spends the DeepSeek key.
- Tests: 449 pass.

**How to verify**
```
uv run pytest -q
```
Expected: `449 passed`.
```
uv run uvicorn app.api:app --host 0.0.0.0 --port 8000
```
Manual check: open `http://localhost:8000` in Chrome and add an item in the panel; open the same address in an Incognito window (or another browser): its panel is empty. Back in the first window, the item is still there. `data/households/` has one `.db` file per browser.

### 2026-10-15 — Page: dish photos on the meal cards and a colourful recipe window (the human's request)
- Why: the human wanted a more colourful card with a real photo of the dish ("I want a real photo", not the drawn emoji mock-up), and a recipe window that is less white. Not in `docs/PLAN.md`; asked for directly.
- Built:
  - `app/tools/photos.py` (new): `recipe_photo(recipe)` searches Pixabay (`PIXABAY_API_KEY`; Wikimedia Commons without a key), keeps hits whose first tags name the kind of dish (`rank_photos`), has `VISION_MODEL` look at the best 2 candidates per search (`PHOTO_CHECK_PROMPT`: name the dish in the photo, then accept or not), searches only the kind of dish ("frittata") if the full query found nothing, downloads the accepted image to `data/photos/<id>.jpg` (Pixabay asks for downloads, not hotlinks). A miss is remembered as `<id>.none`; a network or model failure is not. Two calls at once share one fetch.
  - `app/models.py` / `app/tools/recipes.py`: `Recipe.photo_query` (2-3 words ending with the kind of dish, written by RECIPE_MODEL in the same call; old recipes fall back to the name up to "with").
  - `app/api.py`: `GET /recipe/{id}/photo` (the JPEG, 404 when no photo fits, 503 when the photo service or the vision model is down). `app/config.py`: `PIXABAY_API_KEY`, `PHOTO_DIR`. `.env.example`, `.gitignore` (`data/photos/`).
  - `app/static/index.html`: card = photo on top (fades in; a thin colour band when there is none), bigger title, chips in four colours, a green "Open recipe ›" button; the dish emoji tile is gone. Recipe window = the photo as its header with the title on it (a colour block without a photo), a floating Close, pills (⏱ time, 👥 serves, ✓ N of M at home), ingredients on a green panel with name in bold, amount in black, and a coloured tag (✓ have / use your X / 🛒 to buy on an orange row / check pantry / optional / not at home), steps on a cream panel with coloured numbered circles and the recipe's ingredients in bold. Amounts in the shopping block are black too. No emoji per ingredient (the human's choice).
  - Tests: `tests/test_photos.py` (20, no network: `httpx.MockTransport` + a FunctionModel vision), 2 in `tests/test_api.py`, 1 in `tests/test_recipes.py`. 445 pass.
- Decisions: tags alone are not enough: on real data a potato tortilla tagged "pizza, lasagna, pasta" and spinach dumplings for a chicken skillet got through, so the vision check was added; it is told a stand-in is fine but another kind of dish is not. A wrong photo is worse than none. This is a model judgment, not a code check, which is fine for decoration (CLAUDE.md rule 1 covers ingredients and preferences).
- Checked on real services: 15 dish names, each photo looked at by hand, all fitting; one dish (tacos, an early version) got none. First load of a photo is 5-25 s on the company network (Pixabay's image host is slow, plus 2-7 s per check), the card shows meanwhile; then it is served from disk. Headless Edge 390x844, demo seed: the opening card and a "birthday cake" card show photos; the recipe window shows the photo edge to edge with the title, "7 of 11 at home", powdered sugar as "check pantry", 7 numbered steps with ingredients in bold, amount colour rgb(31,36,33). No page errors. (A first try had the photo inset: the welcome card's `.hero` class clashed; renamed to `.cover`.)
- Next task must know: each new dish costs 1-4 vision calls the first time its card is shown. Without network the cards simply have no photo.
- Open issues: see "Named dish in Only what I have" under Open issues.

**How to verify**
```
uv run pytest -q
uv run pytest tests/test_photos.py -q
uv run uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```
Expected: `445 passed`; then `20 passed`; then the server starts (needs `PIXABAY_API_KEY` in `.env`).
Manual check: open http://localhost:8000, ask "What can I cook tonight?". Within a few seconds each card shows a photo of its dish. Tap "Open recipe": the photo is the header with the name on it, coloured pills, ingredient rows with coloured tags and black amounts, numbered coloured steps.

### 2026-10-15 — T5.2 Latency
- Built:
  - `eval/run_latency.py` (new): real models, sequential, a fresh in-memory store per run (demo seed). Cases: photo → inventory (1 and 4 photos, stand-in `tests/fixtures/coffee.jpg`), opening, Mode A (Only what I have, Shopping OK), Mode B (lasagna), recipe steps. It splits `TurnResult.steps` into agent model / recipe-vision model / other, counts agent calls and output-check retries, prints a markdown table with the PRODUCT §10 targets, and saves JSON in `eval/results/`. `--write` replaces only the block between `<!-- latency:begin -->` and `<!-- latency:end -->` in `eval/RESULTS.md`. `tests/test_latency.py` (4 tests, no network).
  - `eval/RESULTS.md` (new): the table and the notes below.
  - **Mode B in 2 agent calls:** the `get_recipe` tool (`app/agent.py`) now returns the missing report with the recipe (`MealCandidate.to_buy` / `check_first`, computed by `checks.compute_missing`), and rule 4 of the instructions uses it, so the agent no longer calls `compute_missing` (that tool stays for re-checks). Trace (`app/trace.py`): `get_recipe` reads "recipe for Lasagna, 2 missing, 1 not confirmed" (`_missing_words`, shared with compute_missing). The page's `isModeB` also accepts `get_recipe`. Scenarios 4, 5, 10 expect `[get_recipe]`; 4 also expects no `compute_missing`.
- Numbers (5 runs each, 12:30): photo 1 / 4 photos 8.7 / 10.4 s (max 14.5), opening 8.5 s, Mode A 10.9 s (Shopping OK 10.5), Mode B 7.0 s, steps 2.8 s. All under the targets (30 s photos, 25 s turns). At 12:05 the API was twice as slow (agent call ~6 s): Mode A 19.6 s, Mode B 22.6 s with a max of 29.4 s over target (3 agent calls then + one retry). That Mode B case is what the 2-call change fixes.
- Decisions:
  - **AGENT_MODEL stays `deepseek-v4-pro`.** `deepseek-flash` (Mode A 11.0 s, Mode B 9.5 s in the slow hour; suite 28/28) suggested chicken for the beef in bolognese and lasagna, and said "Four creamy pasta options" with 3 shown. The code cannot catch either. Flash is the fallback for a slow demo day.
  - **No streaming** of the message text: the final agent call's first token comes 1.2-2.3 s in and the call ends at 2-3.5 s, so streaming would gain about 1 s, and the cards still need the whole reply. Explained in `eval/RESULTS.md`, as the plan allows ("or the gap is explained").
  - `suggest_meals` keeps n=5.
- Checked: `uv run pytest -q` 425 passed; scenarios 14/14 (pro, after the change); 4, 5, 10 3/3 each, no defining-ingredient swaps.
- Next task must know: `get_recipe` returns `to_buy` / `check_first`; `compute_missing` is still a tool but Mode B does not need it. Re-run `eval/run_latency.py --write` after model or prompt changes. The photo cases use one small stand-in photo; T5.1 should re-measure them with real photos.
- Open issues: API speed swings; failed-suggestion moment in the demo (see Open issues).

**How to verify**
```
uv run pytest -q
uv run python eval/run_latency.py --repeat 2 --only mode_a,mode_b
uv run python eval/run_scenarios.py --only 4
```
Expected: `425 passed`; then a table with Mode A and Mode B lines, each with 2 agent calls and a check mark in the Target column (medians around 7-11 s when the API is fast, up to about twice that when it is slow); then `1/1 passed` with `tools: get_recipe > output check` (no compute_missing).
Manual check: open `eval/RESULTS.md`: the latency table, then the notes (slow vs fast hour, pro vs flash, no streaming). Then run the app (`uv run uvicorn app.api:app --reload --host 0.0.0.0 --port 8000`), seed it in `/docs` with `POST /admin/seed`, ask "I want to make lasagna" and open the trace line under the reply: it reads "2 steps · recipe for Lasagna, N missing, ... → checked by code" (one step more if an output check failed and the agent fixed its reply).

### 2026-10-15 — T4.5 Cooking mode switch (the human's request)
- Why: the human found "recipes from what we have or not" muddled. Before, Mode A could still end with a shopping list (the recipe model was told to make the first dish the classic version, and rule 3 let the agent show a failed candidate as a Mode B answer), so the user never knew what kind of answer to expect. The human chose a switch in the page over the bot asking every time or two bots.
- Built:
  - `app/models.py`: `CookMode = Literal["home", "shop"]`, `MAX_TO_BUY = 3`; `Recipe.requested` (True for a get_recipe dish the user named); `MealCandidate.to_buy` / `check_first` (shop mode); `AgentReply.offer_shop` (set by code, hidden from the model's schema).
  - `app/tools/checks.py`: `check_candidates(..., cook_mode)`: home = `validate_suggestion` as before; shop = no avoided ingredient and at most 3 items to buy or confirm. `check_reply(..., cook_mode)`: a **suggested** meal (not `requested`) in home mode must need nothing to buy (substituted items aside), in shop mode at most 3; a **named** dish gets its lists in either mode; `shopping_list` / `check_first` are now **always** recomputed by code (before: only when the model gave a list), so a forgotten list is filled in instead of a retry.
  - `app/tools/recipes.py`: `SUGGEST_PROMPT` has `{mode_rules}` from `SUGGEST_MODE_RULES`: home = essentials only from the inventory and staples, the closest makeable dishes for a named style, and "return fewer dishes, or none" rather than invent one; shop = up to 3 missing essentials, marked honestly. `get_recipe` sets `requested=True`.
  - `app/agent.py`: `Deps.cook_mode`, a cooking mode line in the instructions (`COOK_MODE_TEXT`), rule 3 rewritten (failed candidates are never shown; in Shopping OK the lists come from the candidates' `to_buy`), rule 4 says Mode B holds in both modes. `run_turn(..., cook_mode="home")`. Messages sent in shop mode start with `[cooking mode: Shopping OK]` (`SHOP_NOTE`, in `user_prompt`), so the model sees the switch change in the history. `offer_shop` = home mode, suggest_meals was called, fewer than 2 suggested meals shown (not for the opening or an off-topic reply).
  - `app/api.py`: `POST /chat` takes the form field `cook_mode` (`home` default, `shop`; anything else is 422).
  - `app/static/index.html`: a two-way switch above the quick replies, "🏠 Only what I have" / "🛒 Shopping OK" (shown once there is an inventory; remembered per browser in `localStorage` `ftt.cookMode`; sent with every message). A reply with several meals and a shopping list shows "🛒 To buy: ... · check pantry: ..." or "✓ Nothing to buy" on each card instead of one combined block; the recipe window shows only that meal's lists (`replyForMeal`). When the reply has `offer_shop`, a "🛒 Show ideas with a short shopping list" button under it flips the switch and sends the same question again.
  - Tests: `tests/test_checks.py` (11 new: both modes, substitutes, named dish, candidate split), `tests/test_agent.py` (3 new + user_prompt), `tests/test_recipes.py` (2 new), `tests/test_api.py` (1 new), `tests/test_models.py`, `tests/test_scenarios.py` updated. `eval/run_scenarios.py`: per-turn `cook_mode`; expect keys `meals_fit_shop`, `shopping_list_not_empty`, `offer_shop`.
- Decisions / deviations:
  - **Scenario 3 changed:** it expected a failed check in the trace, which came from the old "classic version first" rule. In Only what I have that dish is no longer proposed, so it now expects valid meals and an empty shopping list. Scenario 13 is the same request in Shopping OK (cream on the list).
  - Preferences are checked for suggested meals in both modes; a dish the user named is not checked against preferences (as before: the user asked for it).
  - The opening always runs in home mode.
  - Found on real models and fixed: (1) a bare kitchen in home mode got invented "dinners" ("Lemon Vinegar Pan Dressing Tossed with Oregano") → the "fewer dishes, or none" rule; (2) after the switch to Shopping OK in the same chat, the agent repeated its last answer without calling suggest_meals → the `[cooking mode: Shopping OK]` note.
- Checked: `uv run pytest -q` 420 passed; `uv run python eval/run_scenarios.py` 14/14; scenarios 13 and 14 again 2/2 each. Headless Edge 390x844 with real models on a separate DB: the switch shows "Only what I have" checked; Shopping OK with pasta/bacon/mushroom/no cream → 3 cards "✓ Nothing to buy", "🛒 To buy: cream", "🛒 To buy: cream", no combined block; the recipe window shows "To buy: cream · 250 ml" and "cream: 250 ml · to buy"; after a reload the switch is still on Shopping OK; lemon + ketchup only, Only what I have → no meals and the "🛒 Show ideas with a short shopping list" button; tapping it flips the switch, resends "What can I cook tonight?" and returns 3 cards with their to-buy lines. No page errors.
- Next task must know: `checks.check_reply` and `check_candidates` take `cook_mode` (default home). A recipe from `get_recipe` is `requested`; anything else is a suggestion and must fit the mode. `scripts/chat.py` has no mode flag (always home).
- Open issues: in shop mode the agent often leaves `shopping_list` empty and code fills it ("lists fixed by code" in the trace), and once named "cream" in the message (one retry). Harmless; tune rule 3 if it costs time in T5.2.

**How to verify**
```
uv run pytest -q
uv run python eval/run_scenarios.py --only 3,13,14
uv run uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```
Expected: `420 passed`; then `3/3 passed`; then `Uvicorn running on http://0.0.0.0:8000`.
Manual check (F12 then Ctrl+Shift+M for a phone view): in http://localhost:8000/docs run `POST /admin/seed`, open http://localhost:8000/: above the quick replies a switch "🏠 Only what I have" / "🛒 Shopping OK". Tap Shopping OK and ask "We love creamy pasta, like fettuccine alfredo. What can I make tonight?": each card says what to buy (or "✓ Nothing to buy"). Then Inventory → Start over, add only "lemon" in the panel, switch back to Only what I have, ask "What can I cook tonight?": no cards and a "🛒 Show ideas with a short shopping list" button; tap it: the switch moves to Shopping OK and ideas with what to buy appear.

### 2026-10-14 — Page: design round (the human chose items 1-5 of the proposal)
- The human asked what would make the page nicer to look at; of the proposal they picked: (1) a calmer inventory panel, (2) livelier meal cards, (3) quick replies above the text box, (4) a welcome screen for an empty inventory, (5) a softer chat. Place headers keep their words with the icon ("🧊 Fridge", "❄️ Freezer", "🥫 Pantry"). Page only (`app/static/index.html`); no server or agent change.
- Built / changed:
  1. Inventory rows: emoji (by a word of the name, else by category: `itemEmoji`), name, ⏰ when use soon, a colour dot + word for the quantity (green plenty, yellow some, orange low). Tapping a row shows its actions (one row at a time, `state.openItem`): quantity as a 3-way switch, "⏰ Use soon" toggle, "✎ Rename", "Delete". Rows waiting for a decision (orange uncertain, grey not seen) keep ✓ and × on the line. Staples: emoji, name, ×. Sorting: decision rows first, then the stored order (sorting use-soon first made a row jump away while its actions were open). The panel and the review keep their scroll position when they redraw (emptying a scroller reset it to the top on every edit).
  2. Meal cards: an emoji tile by dish words (`dishEmoji`: pasta 🍝, omelette/egg 🍳, stir-fry 🥘, ...; a soft colour from the name), title, "⏱ 30 min · uses 8 things you have", an orange "⏰ uses your spinach: needs using" line, at most 4 chips then "+N", "Open recipe ›"; shadow instead of a border.
  3. Quick replies above the text box (`renderQuick`): empty inventory → "📷 Scan my fridge", "🥫 Scan my pantry"; otherwise "What can I cook tonight?" and "Something quick" (sent at once), "I want to make…" (fills the box), and "🥫 Scan my pantry" while the pantry is not scanned (else "📷 Scan my fridge"). Hidden while typing or with photos waiting; disabled while a turn runs.
  4. Empty inventory: a welcome card at the top of the chat ("Let's see what's in your kitchen", "📷 Take a photo of your fridge", "🖼️ or choose photos from your gallery"); the fixed welcome message is not added then (it said the same). The card goes away once there are items.
  5. Chat: agent messages with a 🍳 avatar and a soft shadow instead of a frame, more space between messages, three bouncing dots while the agent works.
- Checked in headless Edge 390x844 (before/after screenshots of the empty, opening, cards and inventory views; real models for the turns): empty → welcome card, no duplicate message, scan chips; seeded → no card, 4 chips; chips hide while typing; "What can I cook tonight?" chip sends the turn; eggplant 🍆 (a first rule gave it 🥚: "egg" matched inside "eggplant", fixed to whole words); open onion → actions, scroll position kept (500 → 500), quantity → low, use soon on, still open, rename → "red onion"; garlic stays in place after "Use soon"; 21 flagged rows after a rescan, each with ✓ and ×. No page errors.

**How to verify**
```
uv run uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```
Expected: `Uvicorn running on http://0.0.0.0:8000`.
Manual check (F12 then Ctrl+Shift+M for a phone view): in http://localhost:8000/docs run `POST /admin/reset`, open http://localhost:8000/: a welcome card with "📷 Take a photo of your fridge" and two scan chips above the text box. Run `POST /admin/seed`, press "New chat": the card is gone, the chips read "What can I cook tonight?", "Something quick", ... Tap "What can I cook tonight?": cards with a big emoji, "⏱ ... min · uses N things you have". Open Inventory: compact rows with emoji and a colour dot; tap "garlic": a quantity switch, "⏰ Use soon", "✎ Rename", "Delete".

### 2026-10-14 — Page: History of past chats, in the browser (the human's request)
- The human asked whether past chats are kept and can be seen. They were kept (the agent's history per session on the server, the shown transcript per session in `localStorage`) but there was no way back to one after "New chat". The human chose a browser-only History (the transcripts with cards and lists are already in the browser; a server list would need a new endpoint and rebuilding the display from pydantic-ai messages).
- Built / changed (`app/static/index.html` only):
  - `localStorage` `ftt.chats`: `[{id, started, updated, title}]`, updated by `saveTranscript()` (so every message). The title is the first thing the user wrote (or "📷 2 photo(s) (fridge, pantry)"); a chat with only the greeting is not listed. At most 30 chats; older transcripts are deleted from the browser (the server keeps its history). Chats saved before the index existed are found from their `ftt.transcript.<id>` keys and listed as "earlier". All storage access stays in try/catch.
  - Header button 🕘 → "Your chats" window (the centered `.sheet`): newest first, title, "Today 12:24 PM" / "Yesterday ..." / "Oct 12 ...", "· this chat" on the current one. Tapping a chat reopens it (its messages come back from the browser; the agent continues with the session's history from the server). Ignored while a turn is running.
  - Narrow phones: header buttons do not wrap (`nowrap`, smaller padding under 400 px), and under 380 px the title becomes 🍳 so the four header items fit on one line.
- Checked in headless Edge with real models (demo seed, 360x740): an old transcript put in `localStorage` beforehand appears as "earlier"; "How long do eggs keep in the fridge?", New chat, "The kids hated the eggplant last time." → History lists the 3 chats (the current one marked); reopening the eggs chat restores its 3 messages and the same session id; "And milk?" → "Opened milk lasts about 5–7 days past its printed date kept cold ..." (the agent kept the context); that chat moves to the top. Header fits on one line at 360, 390 and 1280 px. No page errors.
- Known limit: the History lives in one browser; another phone or a cleared browser shows no past chats (the server still has them).

**How to verify**
```
uv run uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```
Expected: `Uvicorn running on http://0.0.0.0:8000`.
Manual check: open http://localhost:8000/, send `How long do eggs keep in the fridge?`, press "New chat", send `Thanks!`. Tap 🕘: both chats are listed, newest first, the current one marked "this chat". Tap the eggs chat: its messages come back; send `And milk?`: the answer is about how long milk keeps.

### 2026-10-14 — Steps with the substitutes, amounts in the shopping list, "Start over" (the human's requests)
- Built / changed:
  - `app/tools/recipes.py`: `get_steps(store, recipe_id, substitutions=None)`. The substitutes for ingredients the recipe has replace them in the prompt's ingredient list, plus a "Substitutes: cottage cheese instead of ricotta" line; `STEPS_PROMPT` gained "write the steps for the substitute and never mention the ingredient it replaces". Steps with substitutes are stored under their own key (`<id>~ricotta>cottage cheese`), so the plain and each substituted version are generated once each; the returned recipe keeps its id and its original ingredients (the page shows "use your cottage cheese instead" next to ricotta). Substitutes for ingredients the recipe lacks are ignored (same key as plain).
  - `app/api.py`: `GET /recipe/{id}/steps?sub=ricotta:cottage cheese` (repeatable; malformed values ignored). New `POST /inventory/reset`: deletes every item and every scan date (`Store.clear_inventory`); preferences, staple choices (added or removed) and chats stay. `/admin/reset` still deletes everything.
  - `app/static/index.html`: the recipe window passes the reply's substitutions when it asks for steps. Shopping lists (under the card and in the recipe) show the recipe's amount after each item: "ground beef · 500 g", "cottage cheese instead of ricotta · 450 g", "lasagna noodle · 12 sheets" (`amountFor` takes it from the reply's meals; nothing shown when the recipe has no amount). At the end of the inventory panel, "Start over: clear the inventory" → an in-page confirmation ("Clear all 21 items and the scan dates, then add new photos? Your preferences and staples stay." Cancel / Clear inventory) → `POST /inventory/reset`, the panel closes, a new chat starts and the welcome asks for fridge and pantry photos.
  - Tests: 404 pass (+4): steps with substitutes (prompt has "- cottage cheese: 450 g" and no "- ricotta", cached per version, the plain version separate and stored under the recipe id), substitutes the recipe lacks are ignored, the API's `sub` parameter, the inventory reset keeps preferences, staples and chats.
- Checked in headless Edge 390x844 with real models (demo seed): "The kids hated the eggplant last time.", then "I want to make lasagna": the chat block reads "USE INSTEAD cottage cheese instead of ricotta · 450 g | TO BUY ground beef · 500 g, mozzarella · 300 g, shredded, parmesan · 60 g, grated | CHECK YOUR PANTRY FIRST lasagna noodle · 12 sheets"; opening the card requests `/steps?sub=ricotta%3Acottage+cheese` and the steps mention cottage cheese, not ricotta. Panel → Start over → Cancel (nothing changes, 21 items) → Start over → Clear inventory: badge 0, panel closed, a new chat with the welcome; the server has 0 items and no scans; the eggplant preference is still stored. No page errors.

**How to verify**
```
uv run pytest -q
uv run uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```
Expected: `404 passed`; then `Uvicorn running on http://0.0.0.0:8000`.
Manual check: run `POST /admin/reset` and `POST /admin/seed` in http://localhost:8000/docs, open http://localhost:8000/ and send `I want to make lasagna`. The shopping block shows amounts ("ground beef · 500 g"); open the card: the steps say cottage cheese, not ricotta. Then open Inventory, scroll to the bottom, tap "Start over: clear the inventory", then "Clear inventory": the badge shows 0 and a new chat asks for photos of the fridge and the pantry.

### 2026-10-14 — Page: recipe window centered, shopping list inside it (the human's request)
- The human asked: why is there no shopping list in the recipe; open the recipe in the middle of the screen, not from the bottom (it looked cut off); can a long recipe scroll?
- Findings: the shopping list was only in the chat (the block under the card), never in the recipe window; inside the recipe, an ingredient that was not in the kitchen had no mark at all, and staples (salt, oil) had no "✓" either, so they looked missing. The window did scroll (its body had `overflow-y: auto`) but nothing showed that there was more.
- Built / changed (`app/static/index.html` only):
  - `.sheet` is now a centered window (recipe, and the review after a scan): `min(560px, 100vw - 24px)` wide, at most `min(85dvh, 800px)` high, rounded, a header line; only its body scrolls, with shadows at the top and bottom edges when there is more to scroll (`background-attachment: local`), `overscroll-behavior: contain`.
  - Recipe window: in Mode B the same shopping block as under the card (Use instead, To buy, Check your pantry first) at the top; every ingredient line ends with its status: "✓ you have it" (any inventory item, staples included), "use your cottage cheese instead", "to buy" (orange), "check your pantry", or "not in your kitchen" / "optional, not in your kitchen". Cards now carry their reply (`renderCard(meal, data)` → `openRecipe(meal, data)`); `ingredientStatus()` compares canonical names.
  - The scroll position is reset after the window is shown (set while hidden, it was ignored, so a reopened recipe started where it was left).
- Checked in headless Edge with real models (demo seed, "I want to make lasagna"): on 390x844 the window is centered (center 195,422 = screen center), 717 px high; Use instead / To buy (ground beef, mozzarella, parmesan) / Check your pantry first (lasagna noodle) at the top; 14 ingredient lines with the right status each (ricotta "use your cottage cheese instead", salt and black pepper "✓ you have it", basil "optional, not in your kitchen"); content 1233 px in 661 px, scrolling reaches the last step. On 1280x800: centered, 560 px wide. On 390x500: scrolled to 253, closed and reopened → 0. No page errors.
- Open issue added: the steps still say "ricotta" when cottage cheese is the substitute.

**How to verify**
```
uv run uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```
Expected: `Uvicorn running on http://0.0.0.0:8000`.
Manual check: run `POST /admin/reset` and `POST /admin/seed` in http://localhost:8000/docs, open http://localhost:8000/, send `I want to make lasagna` and tap the card. The recipe opens in the middle of the screen with the shopping list at the top; each ingredient says "✓ you have it", "to buy", "use your cottage cheese instead" or "check your pantry". Scroll inside the window down to the last step; close it and open it again: it starts at the top.

### 2026-10-14 — T4.4 Trace UI polish
- Built / changed:
  - `app/trace.py`: `step_label(tool, args, content, failed, detail)` gives each step plain words, and `trace_sentence(trace)` joins them: "3 steps · updated the inventory (removed egg) → 3 ideas → checked by code". Labels: `recognize_inventory` "read 2 photos: 23 items, 2 unsure, 4 not seen"; `update_inventory` "updated the inventory (removed egg, added chicken)"; `suggest_meals` "5 ideas, 1 failed check (no cream or parmesan)"; `get_recipe` "recipe for Lasagna"; `compute_missing` "5 missing, 1 not confirmed" (counts before substitutes, so it never says "to buy" with a number that differs from the To buy list); `validate_suggestion` "checked: ok" / "failed check (no cream)"; `save_preference` "remembered: no eggplant" / "already remembered"; output check "checked by code" / "lists fixed by code" / "answer sent back (old meal id)" / "off topic"; a tool retry "suggest meals retried" / "invalid tool call, retried". `short_reason()` turns check reasons into a few words ("missing: cream, parmesan" → "no cream or parmesan", "violates preferences: eggplant (...)" → "avoids eggplant", "unknown meal id(s) ..." → "old meal id", "message names items ..." → "message listed the shopping items").
  - `app/models.py`: `ToolTraceItem.label`. `app/api.py`: `ChatResponse.trace_summary` (computed field, the sentence).
  - `app/static/index.html` `renderTrace()`: collapsed = "N steps · 8.4 s · " + the labels joined by →, failed steps orange and bold; expanded = one line per step (label · seconds) with the technical line (`tool(args) → result`) under it in small grey monospace. Replies saved in the browser before this change have no labels: the tool name stands in.
  - Tests: 400 pass (+12): `short_reason` (10 cases), `step_label` (save/already, recognition counts, no photos, off topic, a failed validation, nothing missing), the sentence of a mocked Mode A run with a failed candidate and a sent-back answer ("4 steps · updated the inventory (removed cottage cheese, added chicken) → 2 ideas, 1 failed check (no cream or egg...) → answer sent back (old meal id) → checked by code") and of a Mode B run; existing build_trace tests now include labels.
  - Bug found on the way: `short_reason` split on ";" but one problem can contain "; " ("unknown meal id(s) x; use only ids ..."); unknown fragments are now used only when nothing before them was recognized.
- Checked in headless Edge 390x844 with real models (demo seed): "We're out of eggs. Something quick for dinner?" → "3 steps · 10.9 s · updated the inventory (removed egg) → 3 ideas → checked by code"; "Something creamy with pasta tonight?" → "2 steps · 8.4 s · 3 ideas, 1 failed check (no cream, parmesan) → checked by code" with the failed part orange (before the "or" fix); "I want to make lasagna" → "3 steps · 8.1 s · recipe for Lasagna → ... → checked by code"; the page's line equals `trace_summary` from the server; no page errors.
- No agent prompt change, so the scenarios were not rerun.

**How to verify**
```
uv run pytest -q
uv run pytest tests/test_trace.py -q
uv run uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```
Expected: `400 passed`; then `22 passed`; then `Uvicorn running on http://0.0.0.0:8000`.
Manual check: run `POST /admin/reset` and `POST /admin/seed` in http://localhost:8000/docs, open http://localhost:8000/ (phone, or F12 then Ctrl+Shift+M), send `Something creamy with pasta tonight?`. Under the reply a grey line reads like "2 steps · 8 s · 5 ideas, 1 failed check (no cream) → checked by code", the failed part in orange. Tap it: one line per step with its seconds, and the technical detail in small grey text under each.

### 2026-10-14 — T4.3 Preferences end to end
- Most of it already worked from earlier tasks: `save_preference` (T1.7), preferences in the instructions and in `suggest_meals`' prompt (T2.1, T1.6), the code checks (`validate_suggestion`, output check), rule 7's "confirm in one sentence what you will remember".
- Measured first (real models, 2026-10-14): scenario 6: 3/3, message "Got it, no eggplant from now on." every time, 3.0-3.2 s. Scenario 7: 3/3, no eggplant although it is USE SOON.
- Built / changed: `eval/scenarios.yaml` scenario 7 now starts with `opening: true` (since T4.1, "New chat" in the page runs the opening, and the opening prefers USE SOON items: the eggplant is one, but the household avoids it). Expect: a valid meal without eggplant. Then the dinner question as before. 3/3: the opening chose the spinach ("Your spinach needs using: how about a quick mushroom and spinach omelette with cheddar?"), and no eggplant candidate was even generated (no failed check in the trace: the preference reaches the recipe model's prompt; the code check is the safety net).
- The "Done when", in headless Edge 390x844 with real models (demo seed): "The kids hated the eggplant last time." → "Got it, no eggplant from now on." (trace `save_preference`, `output check`) → New chat → the opening offers a spinach omelette → "What should we have for dinner tonight?" → 3 meals (Spinach and Cheddar Omelette, Creamy Tomato and Spinach Pasta, Chicken, Mushroom and Bell Pepper Skillet), none with eggplant among its ingredients (checked in the `/chat` JSON, not only on screen); no page errors.
- No code change in `app/`. Tests: 388 pass (unchanged).
- Open (not in the plan, for the human to decide): saved preferences are invisible in the page and cannot be removed there; the only way out is `/admin/reset`.

**How to verify**
```
uv run python eval/run_scenarios.py --only 7 --repeat 3
```
Expected (real models, about 1 min): three `[PASS] #7 Cross-session preference ...` blocks, each with `ok turn 1: ... tools: suggest_meals > output check` (the opening) and `ok turn 2: ... tools: suggest_meals > output check`, and `| | **total** | **3/3** | |`.
Manual check: start the app (`uv run uvicorn app.api:app --reload --host 0.0.0.0 --port 8000`), run `POST /admin/reset` and `POST /admin/seed` in http://localhost:8000/docs, open http://localhost:8000/ and send `The kids hated the eggplant last time.`: the reply is "Got it, no eggplant from now on." Press "New chat": the greeting names the spinach, not the eggplant. Send `What should we have for dinner tonight?`: tap each card; no recipe lists eggplant.

### 2026-10-14 — T4.2 Substitutions in Mode B
- Baseline (5 real runs of scenario 4 before any change): 5/5 passed the scenario, but in 4/5 the message contradicted the code-fixed lists ("you'd need to buy ground beef, ricotta, ..." while ricotta was substituted and not under To buy), once a substitute was only in the prose ("for the meat, you could use the chicken"), and twice the model put ricotta on its own shopping list (code fixed it). The lists were right; the words were not checked.
- Built / changed:
  - `app/tools/checks.py`: `items_named_in(message, names, dish_names)` (whole words, plural and hyphen allowed, dish names removed first so "Beef lasagna" does not count as "beef"). `check_reply`, Mode B: if the message names any item of the code-fixed To buy or Check first lists, it is a problem → `ModelRetry` ("Write one sentence that names no ingredient except the substitution pairs, and no counts"). Deterministic, so no contradiction between the message and the lists can reach the user.
  - `app/agent.py` rule 4: before replying, go through each missing essential and look for a substitute that plays the same role (cottage cheese for ricotta, greek yogurt for sour cream, butter for oil, one hard cheese for another); never swap the ingredient that defines the dish (no chicken in a beef bolognese, no other noodles for lasagna sheets); every substitute goes in `substitutions`, never only in the message; the message is one sentence naming only the substitution pairs, no counts ("You can make it with your cottage cheese instead of ricotta; the shopping list is below." / "You have everything for it." / "You need a few things for it; the list is below.").
  - `eval/run_scenarios.py`: `substitution_for` skips an item no meal uses (one real `get_recipe` returned a lasagna with no ricotta at all, a bechamel version; nothing to substitute, so not an agent failure).
  - Tests: 388 pass (+10): `items_named_in` (7 cases), `check_reply` Mode B message naming the list vs a short message with a substitution, and an agent run where the first reply lists the shopping items, is sent back, and the second passes. `tests/test_scenarios.py`: `substitution_for` skips items the recipe lacks.
- Real runs (2026-10-14), scenario 4:

  | Version | Pass | Output-check retries | Mean latency | Message agrees with the lists |
  |---|---|---|---|---|
  | baseline | 5/5 | 0 (lists fixed silently 2x) | 8.9 s | 1/5 |
  | check + "no listing, say how many to buy" | 4/5 (1 = recipe without ricotta) | 4/5 | 11.4 s | 5/5 after the retry; 1 count wrong ("3 things", 2 on the list) |
  | check + "one sentence, only substitution pairs, no counts" | 5/5 | 0/5 | 8.7 s | 5/5 |

  Then the full suite `--jobs 4`: 12/12; Mode B messages in #5 / #10: "You have everything you need for pancakes.", "You need a few things for it; the list is below."
- Decisions: the message check is code (rule 1 of CLAUDE.md: what must be correct is computed by code); counts were dropped from the message instead of being checked, because they were a second way to contradict the list.

**How to verify**
```
uv run pytest -q
uv run python eval/run_scenarios.py --only 4 --repeat 3 -v
```
Expected: `388 passed`; then (real models, about 30 s) three `[PASS] #4 ...` blocks, each with `tools: get_recipe > compute_missing > output check` (one output check, no retry) and a `msg:` like `'You can make it with your cottage cheese instead of ricotta; the shopping list is below.'`, `subs: cottage cheese for ricotta`, a `to buy:` list without ricotta, and `| | **total** | **3/3** | |`.
Manual check: start the app (`uv run uvicorn app.api:app --reload --host 0.0.0.0 --port 8000`), run `POST /admin/reset` and `POST /admin/seed` in http://localhost:8000/docs, open http://localhost:8000/ and send `I want to make lasagna`. The message is one sentence about cottage cheese instead of ricotta; the block under the card shows "Use instead: cottage cheese instead of ricotta", "To buy" without ricotta, and "Check your pantry first" with the lasagna noodles.

### 2026-10-14 — Rescan: items not seen are flagged, and a review sheet after every scan (the human's request)
- Why: the human asked what happens to the old inventory when a new photo is sent. Recognition only adds and updates (it never removes: a photo misses things), so finished items stayed forever. The human chose: flag the items of a re-photographed place that were not seen, and open a window to confirm and edit after every scan, not only the side panel.
- Built / changed:
  - `app/models.py`: `InventoryItem.not_seen: bool = False`; `InventoryChange.op` gained `confirm`.
  - `app/tools/inventory.py`: `merge_recognized(store, items, places=())`: stored non-staple items of the photographed `places` that were not recognized get `not_seen=True` (never removed; manual items too, it is only a question); a recognized item gets `not_seen=False`. `update_inventory`: `confirm` (stored items only) clears `uncertain` and `not_seen`; any edit (`touch`) clears `not_seen`. Summary flag `NOT SEEN IN LAST PHOTO`, sorted after uncertain items. Still true: recognition never removes anything.
  - `app/agent.py`: the `recognize_inventory` wrapper passes the tagged places and lists "Not seen in these photos, kept and marked for the user to check (N): ..." in its result. Rule 6: say so in one sentence ("tick or remove them in the list"), no question per item, because the app shows the list.
  - `app/static/index.html`: a review sheet ("Check what I found · Fridge") opens by itself after a turn whose trace has a successful `recognize_inventory` and that sent photos. It lists the items of the photographed places in three groups: "Not sure what this is" (uncertain), "Not seen this time" (✓ still there, × finished), "In the list". Rows are the panel's rows (✎ rename, ✓ confirm, quantity, use soon, ×) and every edit redraws both the sheet and the panel. Buttons: "Later" (close, flags stay) and "All correct" (`confirm` for every flagged item shown, then close; "Done" when nothing is flagged). In the panel, not-seen items are grey and italic with "· not seen" and a ✓; the hint line explains orange vs grey. The panel's ✓ now sends `confirm` instead of a rename to the same name.
  - Also: `OPENING_PROMPT` and the scope paragraph had been written as one long source line each (in this environment a bash heredoc turns `\\` into `\`, which Python then read as a line continuation); `OPENING_PROMPT` re-wrapped with the same value (checked against the committed one). Lesson: write edit scripts with the Write tool, not a heredoc, when they contain backslashes.
  - Tests: 378 pass (+8): inventory (rescan flags only that place and never staples, no places → no flags, seen again clears even for manual items without overriding their quantity, `confirm` clears both flags and leaves virtual staples alone, any edit clears `not_seen`, summary flag and order), agent (the tool result lists the not-seen items and keeps their use-soon flag; rule 6 text).
- Checked: headless Edge 390x844 with real models: demo seed, a coffee photo tagged Fridge from the gallery → the agent: "I found 1 item in your fridge photo. I didn't see most of the fridge items this time (milk, eggs, spinach and the rest): tick or remove them in the list." and the sheet opened by itself after 7.6-9.6 s with "Not seen this time (21)" and "In the list (1)"; × milk and ✓ butter moved them (19 / 2); "All correct" closed it and the panel had no grey rows left; no page errors. Full scenario suite `--jobs 4`: 12/12.
- Known limit: a photo of one shelf flags everything else in that place as not seen (21 items in the test). "All correct" clears them in one tap; a smarter rule (e.g. flag only when the new photos found many of the old items) can come after the real-fridge run if it is annoying.

**How to verify**
```
uv run pytest -q
uv run uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```
Expected: `378 passed`; then `Uvicorn running on http://0.0.0.0:8000`.
Manual check: in http://localhost:8000/docs run `POST /admin/reset` and `POST /admin/seed`. Open http://localhost:8000/, tap 🖼️, pick any food photo (the tag says Fridge), Send. After about 10 s the agent says some items were not seen, and the "Check what I found · Fridge" window opens by itself: what the photo showed under "In the list", the old fridge items under "Not seen this time". Tap × on one (it disappears), ✓ on another (it moves to "In the list"), then "All correct": the window closes, and in Inventory no item is grey.

### 2026-10-14 — T4.1 Proactive opening
- Built / changed:
  - `app/agent.py`: `run_opening(store, session_id)`. No items beyond the staples → `WELCOME_MESSAGE` (photos of fridge and pantry, tag each), no model call, nothing stored. Otherwise the agent runs on `OPENING_PROMPT` (a note from the app: greet in one sentence, call `suggest_meals` once with n=3 and a "built around the USE SOON items" request, show exactly one passed meal, name the use-soon item; with no use-soon items one quick idea). The meal goes through the same output check as any turn. In the stored history the prompt becomes a `SystemPromptPart` (`_hide_prompt`), so the session has no user turn the user did not write, but the next turn still knows what was offered. `run_turn` and `run_opening` share `_run`. `TurnResult.result` is `None` when no model ran.
  - `app/agent.py`: `last_reply_recipes(store, history)`: every run preloads `Deps.recipes` with the recipes named in the session's last reply (from the store), so "yes, that one" can reuse the id without the "unknown meal id" retry. Such a meal is still re-validated (a test removes the eggs in the panel between turns: the reused omelette fails the check). Retry wording now says "this turn or your last reply". Done now because the opening made the old open issue frequent (2 of 3 real follow-up turns, +2 s each).
  - `app/api.py`: `GET /opening?session_id=` calls `run_opening` (dependency `get_opening_runner`); `usage` is null when no model ran. A model failure (`ModelAPIError`, `UnexpectedModelBehavior`, `UsageLimitExceeded`) returns the static greeting (`OPENING_MESSAGE`), never an error: the page must not open on an error.
  - `app/static/index.html`: the opening shows the "Thinking…" bubble and blocks Send / photos / New chat until it arrives (two runs on one session would overwrite each other's history). `showTyping()` shared with turns.
  - `eval/run_scenarios.py`: a turn `{opening: true}` runs `run_opening`. `eval/scenarios.yaml`: scenario 12 (demo inventory without eggplant, so spinach is the only use-soon item, as in `data/demo_seed.json`): opening → `suggest_meals`, `output check`, exactly 1 valid meal, "spinach" in the message; then "Sounds good. How long does it take?" → answered with minutes, no `get_recipe`.
  - Tests: 370 pass (+7): agent (welcome without a model and nothing stored; opening offers a validated meal, history has a system note and no user prompt, a next turn works on top; prompt content; the next turn reuses the last reply's id without a retry; a reused meal is re-checked against the current inventory), API (opening with the agent, welcome on an empty inventory, static fallback on a model error). `tests/test_scenarios.py` expects 12 scenarios.
- Real runs (2026-10-14): scenario 12: 3/3 (opening 7.4-8.0 s, e.g. "Welcome! Your spinach needs using soon — how about a quick Spinach, Mushroom and Cheddar Omelette?"; once a candidate failed on "pantry not scanned: bread" and another passed one was shown). The follow-up turn hit the reused-id retry 2/3 times (3.3-3.7 s); after `last_reply_recipes`: 3/3 with no retry (1.7-1.9 s). Full suite `--jobs 4`: 12/12. Headless Edge: empty inventory → the welcome; after `/admin/seed`, New chat → "Thinking…" with Send disabled, then the greeting and one card in 8.5 s; no page errors.
- Decisions / deviations: the hidden prompt is kept as a system note instead of being dropped, so a "yes, let's make it" turn has the context. Opening latency (~8 s) is one `suggest_meals` call (n=3) plus two agent requests.
- Next task must know: T4.2: scenario 4 is the check. T4.3: scenario 7 (and 6). The opening is also where a stored preference shows (T4.3 "New chat" check).

**How to verify**
```
uv run pytest -q
uv run python eval/run_scenarios.py --only 12
```
Expected: `370 passed`; then (real models, about 10 s) `[PASS] #12 Proactive opening ...` with `ok turn 1: ... tools: suggest_meals > output check` and `ok turn 2: ... tools: output check`, and `| | **total** | **1/1** | |`.
Manual check: start the app (`uv run uvicorn app.api:app --reload --host 0.0.0.0 --port 8000`), open http://localhost:8000/docs and run `POST /admin/reset`, then open http://localhost:8000/ and press "New chat": the welcome asks for fridge and pantry photos (instantly). Run `POST /admin/seed` in /docs, press "New chat" again: "Thinking…" for about 8 s, then a greeting that names the spinach and one meal card. Reply `Sounds good, how long does it take?`: an answer in minutes within a few seconds.

### 2026-10-14 — Page: gallery button (the human's request)
- The human asked whether a photo can be taken from inside the app. It already could: 📷 is an `<input capture="environment">`, which opens the phone camera and attaches the photo. But on Android `capture` offers the camera only, with no way to pick an existing photo. Added 🖼️ next to 📷: a second file input without `capture` (photo library, several at once). The panel's per-place camera buttons still open the camera. A live camera inside the page (getUserMedia) was not used: it needs HTTPS, and the app runs over plain http on the home network.
- Also: thumbnail × no longer clipped, the title no longer wraps at 360 px.
- Checked in headless Edge at 360×740: the gallery button opens a multi-file chooser, 2 photos attach with tags, text box 172 px wide, no page errors.

**How to verify**
```
uv run uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```
Expected: `Uvicorn running on http://0.0.0.0:8000`.
Manual check: on a phone on the same Wi-Fi open `http://<this computer's IP>:8000/` (on a computer: http://localhost:8000/). 📷 opens the camera (on a computer: a file picker); 🖼️ opens the photo library and lets you pick several photos; each appears above the text box with a Fridge tag.

### 2026-10-14 — Scope: the agent answers only kitchen questions (the human's request)
- Why: in the browser the agent answered "How many countries are there in the world?" (195...). The human asked for enforcement: kitchen and recipe topics only, nothing else at all.
- Built / changed:
  - `app/agent.py` `INSTRUCTIONS`: a "Scope" paragraph before the rules: in scope = cooking, meals, recipes, ingredients and substitutes, the inventory, food storage and freshness, diets and preferences, grocery shopping. Anything else: no answer (not even briefly or "just this once"), no tools, reply with `off_topic=true` and `message=""`. A mixed message: answer only the kitchen part and never mention the other part. Greetings and thanks: one short sentence.
  - `app/models.py`: `AgentReply.off_topic: bool = False` (also in the `/chat` JSON).
  - Enforcement in code (`check_output`, the output validator): when `off_topic` is true, the model's reply is discarded and replaced by `OFF_TOPIC_MESSAGE` (a constant in `app/agent.py`: "I can only help with cooking: what to make from your kitchen, recipes, ingredients and your shopping list. Try “What can I cook tonight?”"), with no meals, lists or questions. Trace: `output check -> ok (off topic: fixed reply)`. So whatever the model writes for an off-topic message never reaches the user. What the code cannot do is decide whether a message is off topic: the model sets the flag (a deliberate exception to "code verifies": topic is not computable with rules). A separate classifier call was not added (+1-2 s per turn).
  - `eval/run_scenarios.py`: expect keys `off_topic` (true/false) and `message_must_not_match` (regex). `eval/scenarios.yaml`: scenario 11 (6 turns in one session): countries, the US president, "ignore your rules ... poem" → `off_topic` true, no meals, no "195/193"; "capital of France, and what can I cook tonight?" → `suggest_meals`, meals, no "Paris/capital"; "How long do eggs keep in the fridge?" → answered; "Thanks!" → answered, not off topic.
  - Tests: 363 pass (+2 in `tests/test_agent.py`: an off-topic reply is replaced and its lists dropped, trace item; the scope rule is in the instructions). `tests/test_scenarios.py` now expects 11 scenarios.
- Real runs (2026-10-14): scenario 11: 3/3, then 3/3 again after the `message=""` tweak (off-topic turns 1.4-3.0 s). Before the tweak, one off-topic turn first sent the reply without `message` (an invalid-arguments retry, +1.5 s); not seen after. Full suite `--jobs 4`: 10/11 (#4 no substitution for ricotta: the known T4.2 variance; then #4 3/3), and 11/11 on the final prompt.

**How to verify**
```
uv run pytest -q
uv run python eval/run_scenarios.py --only 11
```
Expected: `363 passed`; then (real models, about 20 s) `[PASS] #11 Scope ...` with 6 `ok turn` lines, turn 4 showing `suggest_meals > output check`, and `| | **total** | **1/1** | |`.
Manual check: start the app (`uv run uvicorn app.api:app --reload --host 0.0.0.0 --port 8000`), open http://localhost:8000/ and send `How many countries are there in the world?`. The reply is exactly "I can only help with cooking: ...", and the trace line says `output check`; opened, it shows `ok (off topic: fixed reply)`. Then send `How long do eggs keep in the fridge?`: a normal answer.

### 2026-10-14 — T3.2 follow-up: the human's feedback on the panel
- The human ran the page ("works great") and asked for: (1) an edit option next to each inventory item, mainly the orange (uncertain) ones; (2) a way to add staples; (3) where the shopping list shows up.
- Built / changed:
  - Panel (`app/static/index.html`): ✎ next to every non-staple item → inline name field (Enter / Save, Escape / Cancel), sent as `rename` (also confirms an uncertain item, even with the name unchanged). Uncertain items also get a ✓ ("yes, this is right": `rename` to the same name, which clears `uncertain`). A place with uncertain items shows a hint line: "Orange items: I'm not sure. ✎ fix the name, ✓ if it's right, × if it isn't there." PRODUCT §4 Flow 1 step 5 already listed rename in the panel; T3.2 had missed it.
  - Staples: an "Add a staple, e.g. rice…" field at the end of the Staples section, sent as the new op `add_staple`.
  - `app/models.py`: `InventoryChange.op` gained `add_staple`. `app/store.py`: table `custom_staples` (`load_custom_staples`, `set_custom_staple`; cleared by `reset_all`). `app/tools/inventory.py`: `all_staples(store)` = defaults + the user's; `get_inventory`, `update_inventory` and `merge_recognized` use it, so a user staple is a staple everywhere (the inventory summary in the prompts, `compute_missing`, `validate_suggestion`). `add_staple` of a default name restores it if removed; of a stored item's name replaces that item with the staple; removing a user staple deletes it. The agent's `update_inventory` docstring does not mention `add_staple` (prompt unchanged, scenarios not rerun).
  - Bug fixed on the way: `Element.append()` printed `null` for missing buttons (seen in the screenshots, not by the test); rows now filter them out.
  - Tests: 361 pass (+8). `tests/test_inventory.py` (+7: user staple shown and persisted, no duplicates, restore a removed default, replaces a stored item, remove deletes it, counts as available in `compute_missing`, reset clears it), `tests/test_api.py` (+1: PATCH `add_staple` + rename of an uncertain item).
  - Checked in headless Edge at 390×844 (scratchpad script, a temp DB with two uncertain items from `merge_recognized`): hint shown, uncertain items first; ✎ rename "white container" → "leftover rice" (no longer uncertain, `source=manual`); ✓ on "sour cream" (hint gone); rename milk → oat milk; add staple "Basmati rice" (Staples 15 → 16, section stays open) then delete it (16 → 15); no "null", no page errors.
- Answer to (3), no code change: the shopping list is Mode B. It appears when the user names a dish ("I want to make lasagna", "Can I make a spinach omelette?"): To buy, Check your pantry first (while the pantry is not scanned), and substitutions from the inventory. Mode A ("what can I cook?") suggests only dishes that can be made now, so it has no list, except when the request names a dish the inventory cannot make (scenario 3: "creamy pasta" without cream). A list to keep or copy across messages is the stretch T6.2.

**How to verify**
```
uv run pytest -q
uv run uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```
Expected: `361 passed`; then `Uvicorn running on http://0.0.0.0:8000`.
Manual check: open http://localhost:8000/ and tap Inventory. Tap ✎ next to an item, type a new name, press Enter: the name changes (an orange item turns white). On an orange item, ✓ turns it white without renaming. Open "Staples", type `rice` in "Add a staple…", tap Add: rice appears in the list and the count goes up by one. Close the panel and send `Can I make fried rice?`: rice is not under "To buy".

### 2026-10-13/14 — T3.2 Web page
- Built / changed:
  - `app/static/index.html` (one file, plain JS, no build, no external resources): mobile-first page for PRODUCT §8.
    - Header: title, "New chat" (new session id, then `/opening`), "Inventory" with a count badge (non-staple items).
    - Chat: user and agent bubbles, a "Thinking…" / "Looking at your photos…" bubble while the agent runs (Send and photo buttons disabled), errors from the API (`detail`) as an orange system bubble. Agent messages show questions, up to 3 meal cards (name, time, uses-from-inventory chips; "use soon" chips orange), the shopping block (Use instead, To buy, Check your pantry first in a muted style; a Mode B reply with nothing missing says "Nothing to buy"), and the trace in a collapsed `<details>` line ("2 steps · 1 failed check · 10.5 s — suggest_meals → output check"; expanded: one line per call, failed ones orange; T4.4 polishes the sentence).
    - Photos: `<input type="file" accept="image/*" multiple capture="environment">`, up to 4; thumbnails with a place tag that cycles Fridge → Freezer → Pantry on tap and an × to remove. Default: the first is Fridge, each next copies the previous tag. A panel camera button pre-tags the picked photos with that place. Sent as `images` + `locations` in order.
    - Meal card tap → bottom sheet: time, servings, ingredients ("✓ you have it" for inventory items, "(optional)"), steps from `GET /recipe/{id}/steps` with a spinner (cached on the card after the first load).
    - Inventory drawer: one section per place with "scanned today / yesterday / N days ago" or "not scanned yet" (freezer: "skipped" when declined) and a camera button; items sorted uncertain first (orange, "?"), then use soon; quantity button cycles plenty → some → low → plenty; "use soon" toggle; × delete; an "Add to <place>…" input per place (qty "some", category default `other`). Staples in a collapsed section (delete only: their quantity is not stored, so it is not a button). Every edit calls `PATCH /inventory` and redraws from the response; every `/chat` response redraws the panel too.
    - Session id in `localStorage` (`ftt.session`), the visible transcript per session in `localStorage` too (last 60 entries, photos as tags only), all wrapped in try/catch, so a reload shows the same chat; "New chat" starts an empty one. Enter sends on a computer; on a touch screen Enter adds a line.
- Checks run:
  - `node --check` on the page script.
  - Headless Edge (Playwright, run from the scratchpad, not a project dependency) at 390×844, touch, against `uvicorn`:
    - Real models (2026-10-13): opening, panel (21 items, pantry "not scanned yet"), a pantry-tagged photo (12.2 s, pantry then "scanned today"), "What can I cook tonight? Under 30 minutes." (12.7 s, 3 cards, trace `2 steps · 10.5 s — suggest_meals → output check`), recipe sheet steps in 3.6 s (7 steps). The rest was blocked by a network outage that day.
    - Real models again (2026-10-14, after the network came back): the whole flow passes with no page errors: photo tagged Pantry 7.5 s → pantry "scanned today" → 3 cards in 10.1 s (trace `2 steps · 9.1 s — suggest_meals → output check`) → steps in 3.1 s → delete egg in the panel → "Can I make a spinach omelette?" 8.0 s: Spinach Omelette card + To buy: egg (trace `get_recipe → compute_missing → output check`) → reload keeps 4 replies → New chat shows only the greeting. The pantry-prose issue did not show up this time.
    - Scripted models (2026-10-14, the real app with FunctionModels for agent, recipe and vision via `dependency_overrides`): the whole flow passes with no page errors: photo → panel "scanned today" → 2 cards (one candidate failed, shown in the trace) → recipe sheet → delete eggs and lower spinach in the panel → "Can I make a spinach omelette?" → To buy: egg (the first try of that turn showed that the edit reached the agent: the output check rejected the omelette with "needs egg, not in inventory") → reload keeps 4 replies → New chat shows only the greeting.
- Decisions / deviations:
  - The transcript is kept in the browser (`localStorage`), not fetched from the server: there is no history endpoint, and it is only for display (the agent's history stays in the store).
  - No streaming of the message text (PRODUCT §8 says "if possible"; `run_turn` returns the whole reply). Left for T5.2.
  - No dark theme; one light palette.
- Next task must know: T4.1 only changes what `/opening` returns (same shape). T4.4 changes `renderTrace()` in the page. For an offline UI check, override `get_turn_runner` / `get_recipe_model` with scripted models (as in `tests/test_api.py`).
- Open issues: pantry-photo prose after a pantry scan (see Open issues).

**How to verify**
```
uv run pytest -q
uv run uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```
Expected: `353 passed`; then `Uvicorn running on http://0.0.0.0:8000`.
Manual check (needs a working network connection for the models): open http://localhost:8000/docs and run `POST /admin/reset` then `POST /admin/seed`. Open http://localhost:8000/ in Chrome or Edge; for a phone view press F12, then Ctrl+Shift+M (or open `http://<this computer's IP>:8000/` on a phone on the same Wi-Fi). Then:
1. The greeting appears; "Inventory 21" opens the panel: Fridge "scanned today" with spinach marked "use soon", Pantry "not scanned yet".
2. Tap 📷, pick 1-2 food photos, tap a tag until it says Pantry, Send: after about 10-20 s the agent says what it found and the panel shows Pantry "scanned today".
3. Type `What can I cook tonight?` and Send: 1-3 cards; tap the small grey line under them to open the trace.
4. Tap a card: the recipe opens from the bottom, the steps appear after a few seconds.
5. In the panel, delete `egg` (×). Type `Can I make an omelette?`: the answer lists egg under "To buy".
6. Reload the page: the chat is still there. "New chat": only the greeting.

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
