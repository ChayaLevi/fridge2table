# Fridge2Table — Claude Code context

Read this file first, then `docs/PRODUCT.md` (what we build and why) and `docs/PLAN.md` (the ordered task list). Work through `docs/PLAN.md` task by task.

## What this is

A demo of a **kitchen agent**: the user photographs their fridge/pantry, the agent builds an inventory, and then, in a chat, suggests meals from what is there (Mode A) or tells the user what is missing for a dish they want (Mode B). The agent remembers preferences, opens proactively, and checks its own suggestions with deterministic code.

- Solo developer, two-week demo: **Oct 12 – Oct 23, 2026**. Live demo on Fri Oct 23.
- The demo is judged by one rule: a real person ran it on their own fridge and said they would use it again.
- Product language: **English only**. General (not Chinese-specific) cuisine.
- This is the thin first slice of a larger project. Do not build for the later phases (see "Out of scope" in `docs/PRODUCT.md`), but keep tools clean enough to port later.

## Stack (decided — do not change without asking)

- Python 3.12, `uv` for env and dependencies.
- **Pydantic AI** (v2.x) for the agent loop, tools, structured output and output validation. Before writing agent code, check the installed version's docs for the exact API (model string format, `RunContext`, `output_validator`, `ModelRetry`, message history, dynamic instructions). Do not rely on memory for this API.
- FastAPI + uvicorn. One static HTML page (`app/static/index.html`) with plain JS, no frontend framework, no build step.
- Storage: SQLite via the standard `sqlite3` module (or a single JSON file if simpler). Single household, no auth.
- **Only Chinese models are allowed.** Models via API, configured by env vars (see `.env.example`):
  - `VISION_MODEL` — recognition of items in photos. Default: `deepseek-v4-flash-vision-exp` (temporary; it will be swapped for Qwen3.8 Max once that license is approved).
  - `AGENT_MODEL` — the agent loop. Default: `deepseek-v4-pro` (switch to `deepseek-v4-flash` only if turns are too slow).
  - `RECIPE_MODEL` — recipe generation inside `suggest_meals` / `get_recipe`. Default: `deepseek-v4-flash` (simple structured generation; speed matters more).
  - The DeepSeek API is OpenAI-compatible (base URL `https://api.deepseek.com`). Connect through Pydantic AI's DeepSeek or OpenAI-compatible provider; check the installed version's docs for which one exists and how to set the base URL. Images go as OpenAI-style multimodal content blocks in the user message, and only the vision model accepts them.
  - Both must be swappable by changing the env var only. Verify exact model IDs against the providers' current docs before use.
- No Ascend, no openJiuwen, no LangChain/LangGraph, no vector DB, no Docker in this demo.

## Core design rules (non-negotiable)

1. **The agent decides, the code verifies.** The LLM chooses which tools to call and in what order. Anything that must be correct — what is missing, whether a meal uses only available ingredients, whether a meal violates a stored preference — is computed by deterministic Python, never by the LLM.
2. **Nothing invalid reaches the user.** Every meal in the agent's final reply is re-checked by an `output_validator`; a failing meal raises `ModelRetry` with the reason, so the agent must fix it.
3. **Tools are plain functions.** Each tool in `app/tools/` is a pure-ish Python function with Pydantic input/output models and its own unit tests. The Pydantic AI `@agent.tool` wrappers in `app/agent.py` are thin. This is what lets us port to another framework later.
4. **Canonical ingredient names.** All comparisons happen on canonical names produced by `normalize()` (lowercase, singular, synonyms resolved). Never compare raw strings.
5. **Coarse quantity levels (plenty | some | low) always; an optional exact amount (g, kg, ml, l, pcs, pack) entered only by the user.** Recognition never guesses exact amounts. Code checks compare amounts only when both the inventory amount (user-entered) and the recipe amount are known in compatible units; otherwise they are presence-based.
6. **The user stays in control.** The agent never buys, orders or deletes anything without the user saying so. Inventory edits in the side panel bypass the agent and always win.
7. **Transparency.** Every agent reply carries a trace of the tool calls made in that turn (tool name, short args summary, short result summary). The UI shows it in a collapsible line.

## Repo layout (target)

```
CLAUDE.md
docs/PRODUCT.md  docs/PLAN.md
app/
  config.py        # env vars, model names, paths
  models.py        # all Pydantic schemas (InventoryItem, Recipe, Preference, AgentReply, ...)
  amounts.py       # exact amounts: parse_amount, to_base, format_amount, default_unit (T6.3)
  store.py         # persistence: inventory, preferences, chat sessions
  llm.py           # model factories + the two non-agent LLM calls (vision, recipe generation)
  tools/
    normalize.py   # normalize(), synonyms
    recognize.py   # recognize_inventory()
    inventory.py   # get/update inventory, staples
    recipes.py     # suggest_meals(), get_recipe()
    checks.py      # compute_missing(), validate_suggestion()
    preferences.py # save/get preferences
  agent.py         # Pydantic AI agent, tool wrappers, instructions, output validator, trace capture
  api.py           # FastAPI routes
  static/index.html
data/
  staples.json  synonyms.json
eval/
  fridges/<fridge_id>/*.jpg + labels.json
  run_vision_eval.py
  scenarios.yaml  run_scenarios.py
tests/
.env.example
```

## Commands

- Install: `uv sync`
- Run app: `uv run uvicorn app.api:app --reload --host 0.0.0.0 --port 8000` (open on a phone on the same network)
- Unit tests: `uv run pytest -q`
- Vision eval: `uv run python eval/run_vision_eval.py --model $VISION_MODEL`
- Agent scenarios: `uv run python eval/run_scenarios.py`

## Session protocol (one chat per task)

Each task in `docs/PLAN.md` usually gets its own fresh chat. You have no memory of earlier chats, so the files are the only shared state.

At the **start** of a chat:
1. Read `docs/PROGRESS.md` (what is done, decisions, deviations, open issues). Then read the task you were given in `docs/PLAN.md`, and the parts of `docs/PRODUCT.md` it refers to.
2. Read the existing code the task touches before writing new code. Do not re-create modules that already exist.
3. Check the previous task's "Done when" still holds (`uv run pytest -q`). If not, say so before starting.

At the **end** of a chat (before you say you are done):
1. Make sure this task's "Done when" holds and the tests pass.
2. Update `docs/PROGRESS.md`: tick the task, then add a dated entry with what was built (files), decisions or deviations from the plan, anything the next task must know, and open issues.
3. Commit with the task ID in the message.
4. Give the human a **"How to verify"** block: the exact commands to run themselves (copy-paste ready), what output they should expect, and one manual check (something to try by hand, in the terminal or the browser) that shows the task works. Also add this block to the task's log entry in `docs/PROGRESS.md`.
5. Tell the human the next task ID and anything they must provide for it (🧑).

## Debugging aids (build them as part of the tasks, keep them working)

- `LOG_LEVEL=DEBUG` prints every LLM call (model, prompt size, latency, tokens) and every tool call with its args and result.
- If `LOGFIRE_TOKEN` is set, enable Pydantic AI's Logfire instrumentation, so every agent run can be inspected step by step. It must be optional: the app runs without it.
- `scripts/chat.py --debug` prints the full message list of each agent run.
- FastAPI's `/docs` page must work, so every endpoint can be called by hand.

## How to work

- Follow `docs/PLAN.md` in order. Each task has a "Done when" — do not move on until it holds, and run the tests.
- Write unit tests for every function in `app/tools/` (no network: mock LLM calls with fixtures).
- Keep LLM prompts in the module that uses them, as module-level constants, so they are easy to find and tune.
- When a task needs something only the human can provide (API keys, fridge photos and their labels, a real user session), stop and say exactly what is needed.
- Prefer the simplest thing that meets "Done when". This is a two-week demo, not a product.
- Do not add features that are not in `docs/PLAN.md`. If something seems missing, ask.
- Commit after each completed task with a message naming the task ID (e.g. `T2.1: normalize + synonyms`).
