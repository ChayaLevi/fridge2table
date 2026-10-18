"""T2.3: the trace (one short line per tool call) and the per-turn usage, from mocked runs (no network)."""

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, RetryPromptPart, ToolCallPart, ToolReturnPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from app.agent import run_turn
from app.models import (
    FailedCandidate, MealCandidate, MissingReport, Recipe, StepTiming, SuggestResult, ToolTraceItem, ValidationResult,
)
from app.store import Store
from app.trace import (
    args_summary, build_trace, format_trace, result_summary, short, short_reason, step_label, trace_sentence,
)
from tests.test_agent import LASAGNA_MODEL, RECIPE_MODEL, ids_by_name, reply, store  # noqa: F401 (fixture)


# --- summaries -------------------------------------------------------------------------------------

def test_short_collapses_whitespace_and_truncates():
    assert short("a\n  b") == "a b"
    assert short("x" * 200) == "x" * 97 + "..."


def test_args_summaries_are_short_and_readable():
    lasagna = Recipe(id="abc123", name="Lasagna", ingredients=[], time_minutes=60)
    recipes = {lasagna.id: lasagna}
    assert args_summary("update_inventory", {"changes": [{"op": "remove", "name": "egg"}, {"op": "add", "name": "chicken"}]},
                        {}) == "remove egg, add chicken"
    assert args_summary("suggest_meals", {"request": "quick", "max_minutes": 30, "exclude": ["Soup"]}, {}) \
        == "'quick' max 30 min exclude Soup"
    assert args_summary("suggest_meals", {}, {}) == ""
    assert args_summary("get_recipe", {"dish": "lasagna"}, {}) == "lasagna"
    assert args_summary("compute_missing", {"recipe_id": "abc123"}, recipes) == "Lasagna"  # id -> dish name
    assert args_summary("validate_suggestion", {"recipe_id": "zzz"}, recipes) == "zzz"
    assert args_summary("save_preference", {"text": "no pork", "avoid": ["pork", "bacon"]}, {}) == "'no pork' avoid pork, bacon"
    assert args_summary("reply", {"meal_ids": ["abc123"], "shopping_list": ["ricotta"]}, recipes) == "Lasagna; to buy 1"
    assert args_summary("reply", {"message": "hi"}, {}) == "no meals"


def test_result_summaries():
    changes = {"changes": [{"op": "remove", "name": "egg"}, {"op": "add", "name": "a"}, {"op": "add", "name": "b"}]}
    assert result_summary("update_inventory", changes, "Applied: ...") == ("removed 1, added 2", False)

    suggest = SuggestResult(
        passed=[MealCandidate(id=f"p{i}", name=f"P{i}", time_minutes=10, ingredients=[]) for i in range(4)],
        failed=[FailedCandidate(id="f", name="Carbonara", reason="missing: cream")],
    )
    assert result_summary("suggest_meals", {}, suggest) == (
        "5 candidates: 4 passed, 1 failed (Carbonara: missing: cream)", True)
    assert result_summary("suggest_meals", {}, SuggestResult(passed=suggest.passed, failed=[])) == ("4 candidates", False)

    bad = ValidationResult(ok=False, missing_essential=["cream"], violated_preferences=[], reason="missing: cream")
    assert result_summary("validate_suggestion", {}, bad) == ("FAILED: missing: cream", True)
    good = ValidationResult(ok=True, missing_essential=[], violated_preferences=[])
    assert result_summary("validate_suggestion", {}, good) == ("ok", False)

    report = MissingReport(missing_essential=["ricotta"], check_first=["pasta"], missing_optional=[])
    assert result_summary("compute_missing", {}, report) == ("to buy: ricotta; check first: pasta", False)
    candidate = MealCandidate(id="x", name="Lasagna", time_minutes=60, ingredients=["pasta: 1", "egg: 2"])
    assert result_summary("get_recipe", {}, candidate) == ("Lasagna, 2 ingredients, 60 min; nothing missing", False)
    lacking = candidate.model_copy(update={"to_buy": ["ricotta"], "check_first": ["pasta"]})
    assert result_summary("get_recipe", {}, lacking) == (
        "Lasagna, 2 ingredients, 60 min; to buy: ricotta; check first: pasta", False)
    assert result_summary("save_preference", {}, "Saved: no pork (avoid: pork)") == ("Saved: no pork (avoid: pork)", False)
    recognized = "Recognized 12 items in 2 photo(s) of: fridge.\nUncertain (2): a, b\nInventory now:\n..."
    assert result_summary("recognize_inventory", {}, recognized) == (
        "Recognized 12 items in 2 photo(s) of: fridge. uncertain (2)", False)
    assert result_summary("get_inventory", {}, "fridge ...") == ("current inventory", False)


def test_result_summary_accepts_dicts_from_stored_history():
    report = {"missing_essential": ["cream"], "check_first": [], "missing_optional": []}
    assert result_summary("compute_missing", {}, report) == ("to buy: cream", False)


# --- build_trace on hand-made messages ---------------------------------------------------------------

def test_build_trace_pairs_calls_with_returns_retries_and_steps():
    messages = [
        ModelRequest(parts=[UserPromptPart("dinner?")]),
        ModelResponse(parts=[
            ToolCallPart("validate_suggestion", {"recipe_id": "nope"}, tool_call_id="c1"),
            ToolCallPart("compute_missing", {"recipe_id": 7}, tool_call_id="c2"),
        ]),
        ModelRequest(parts=[
            RetryPromptPart("Unknown recipe 'nope'", tool_name="validate_suggestion", tool_call_id="c1"),
            RetryPromptPart([{"type": "string_type", "loc": ("recipe_id",), "msg": "bad", "input": 7}],
                            tool_name="compute_missing", tool_call_id="c2"),
        ]),
        ModelResponse(parts=[ToolCallPart("reply", {"message": "m"}, tool_call_id="c3")]),
        ModelRequest(parts=[ToolReturnPart("reply", "Final result processed.", tool_call_id="c3")]),
    ]
    steps = [
        StepTiming(kind="model", name="agent", seconds=1.0),
        StepTiming(kind="tool", name="validate_suggestion", seconds=0.25, detail="retry: ...", call_id="c1"),
        StepTiming(kind="check", name="output check", seconds=0.01, detail="ok (fixed check_first [] -> ['pasta'])",
                   call_id="c3"),
    ]
    trace = build_trace(messages, steps)
    assert trace == [
        ToolTraceItem(tool="validate_suggestion", args_summary="nope", result_summary="retry: Unknown recipe 'nope'",
                      failed=True, seconds=0.25, label="validate suggestion retried"),
        ToolTraceItem(tool="compute_missing", args_summary="7", result_summary="retry: invalid arguments",
                      failed=True, seconds=None, label="invalid tool call, retried"),  # the tool never ran
        ToolTraceItem(tool="output check", args_summary="no meals",
                      result_summary="ok (fixed check_first [] -> ['pasta'])", failed=False, seconds=0.01,
                      label="lists fixed by code"),
    ]


def test_build_trace_skips_calls_without_an_outcome_and_works_without_steps():
    messages = [
        ModelResponse(parts=[ToolCallPart("get_inventory", {}, tool_call_id="a"), ToolCallPart("reply", {}, tool_call_id="b")]),
        ModelRequest(parts=[ToolReturnPart("reply", "Final result processed.", tool_call_id="b")]),
    ]
    assert build_trace(messages) == [ToolTraceItem(tool="output check", args_summary="no meals", result_summary="ok",
                                                   label="checked by code")]


# --- the trace of a mocked run (Done when) ----------------------------------------------------------

async def test_trace_of_a_mode_a_run_with_a_failed_output_check(store):
    """update -> suggest (one candidate fails) -> reply with an invented id (retry) -> valid reply."""
    ids: dict[str, str] = {}
    calls = []

    def fn(messages, info):
        calls.append(1)
        ids.update(ids_by_name(messages[-1].parts))
        out = info.output_tools[0].name
        if len(calls) == 1:
            return ModelResponse(parts=[ToolCallPart("update_inventory", {"changes": [
                {"op": "remove", "name": "cottage cheese"}, {"op": "add", "name": "chicken"}]})])
        if len(calls) == 2:
            return ModelResponse(parts=[ToolCallPart("suggest_meals", {"request": "quick", "max_minutes": 30})])
        if len(calls) == 3:
            return ModelResponse(parts=[ToolCallPart(out, reply(meal_ids=["zzz999"]))])
        return ModelResponse(parts=[ToolCallPart(out, reply(meal_ids=[ids["Spinach omelette"]]))])

    turn = await run_turn(store, "s1", "dinner, quick", model=FunctionModel(fn), recipe_model=RECIPE_MODEL)

    assert [(t.tool, t.args_summary, t.failed) for t in turn.trace] == [
        ("update_inventory", "remove cottage cheese, add chicken", False),
        ("suggest_meals", "'quick' max 30 min", True),
        ("output check", "zzz999", True),
        ("output check", "Spinach omelette", False),
    ]
    results = [t.result_summary for t in turn.trace]
    assert results[0] == "removed 1, added 1"
    assert results[1] == ("2 candidates: 1 passed, 1 failed (Carbonara: missing: cream; pantry not scanned: pasta "
                          "not confir...")
    assert results[2].startswith("output check failed: unknown meal id(s) zzz999")
    assert results[3] == "ok"
    assert all(len(r) <= 100 for r in results)
    assert all(t.seconds is not None and t.seconds >= 0 for t in turn.trace)  # from TurnResult.steps
    # usage of the turn
    assert turn.usage.requests == 4 and turn.usage.input_tokens > 0 and turn.usage.output_tokens > 0
    assert turn.usage.latency_s >= 0
    text = format_trace(turn.trace)
    assert text.splitlines()[0].startswith("  - update_inventory(remove cottage cheese, add chicken) -> removed 1")
    assert text.splitlines()[2].startswith("  ! output check(zzz999) -> output check failed")
    # T4.4: the collapsed line, in plain words
    assert trace_sentence(turn.trace) == (
        "4 steps · updated the inventory (removed cottage cheese, added chicken) → 2 ideas, 1 failed check "
        "(no cream, pasta not confirmed) → answer sent back (old meal id) → checked by code")


async def test_trace_of_a_mode_b_run(store):
    ids: dict[str, str] = {}

    def fn(messages, info):
        ids.update(ids_by_name(messages[-1].parts))
        n = sum(1 for m in messages if isinstance(m, ModelRequest))
        if n == 1:
            return ModelResponse(parts=[ToolCallPart("get_recipe", {"dish": "lasagna"})])
        if n == 2:
            return ModelResponse(parts=[ToolCallPart("compute_missing", {"recipe_id": ids["Lasagna"]})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, reply(
            meal_ids=[ids["Lasagna"]], substitutions=[{"missing": "ricotta", "use_instead": "cottage cheese"}],
            shopping_list=["ground beef"], check_first=["pasta"]))])

    turn = await run_turn(store, "s1", "I want to make lasagna", model=FunctionModel(fn), recipe_model=LASAGNA_MODEL)
    assert [(t.tool, t.args_summary, t.result_summary) for t in turn.trace] == [
        ("get_recipe", "lasagna", "Lasagna, 4 ingredients, 60 min; to buy: ricotta, ground beef; check first: pasta"),
        ("compute_missing", "Lasagna", "to buy: ricotta, ground beef; check first: pasta"),
        ("output check", "Lasagna; to buy 1", "ok"),
    ]
    assert not any(t.failed for t in turn.trace)
    assert trace_sentence(turn.trace) == (
        "3 steps · recipe for Lasagna, 2 missing, 1 not confirmed → 2 missing, 1 not confirmed → checked by code")


async def test_trace_of_a_turn_without_tools(store):
    def fn(messages, info):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, reply(message="You're welcome!"))])

    turn = await run_turn(store, "s1", "thanks!", model=FunctionModel(fn))
    assert [(t.tool, t.result_summary) for t in turn.trace] == [("output check", "ok")]
    assert turn.usage.tool_calls == 0 and turn.usage.requests == 1


def test_trace_from_stored_history_has_no_seconds():
    """The trace can be rebuilt from a stored session (dict contents, no steps)."""
    s = Store(":memory:")
    messages = [
        ModelResponse(parts=[ToolCallPart("compute_missing", {"recipe_id": "x"}, tool_call_id="a")]),
        ModelRequest(parts=[ToolReturnPart("compute_missing", MissingReport(
            missing_essential=["cream"], check_first=[], missing_optional=[]), tool_call_id="a")]),
    ]
    s.save_session_messages("s", messages)
    [item] = build_trace(s.load_session_messages("s"))
    assert item.result_summary == "to buy: cream" and item.seconds is None


# --- plain-language labels (T4.4) -------------------------------------------------------------------

@pytest.mark.parametrize("reason, expected", [
    ("missing: cream", "no cream"),
    ("missing: cream, egg; pantry not scanned: pasta not confirmed", "no cream or egg, pasta not confirmed"),
    ("missing: cream, parmesan, egg", "no cream, parmesan or egg"),
    ("violates preferences: eggplant (kids dislike eggplant)", "avoids eggplant"),
    ("output check failed: Kung pao chicken needs peanut, not in inventory. Replace it", "no peanut"),
    ("output check failed: Egg pasta needs pasta, not confirmed (pantry not scanned)", "pasta not confirmed"),
    ("output check failed: unknown meal id(s) zzz; use only ids", "old meal id"),
    ("output check failed: substitute 'mascarpone' (for ricotta) is not in the inventory", "mascarpone not in the inventory"),
    ("output check failed: message names items of the shopping lists (ground beef): the app", "message listed the shopping items"),
    ("output check failed: 4 meals; show at most 3", "too many meals"),
    ("not enough egg (have 4, need 5)", "not enough egg"),
    ("missing: cheddar; not enough egg (have 4, need 5)", "no cheddar, not enough egg"),
    ("output check failed: Frittata not enough egg (have 4, need 5). The user chose", "not enough egg"),
    ("output check failed: substitute 'cottage cheese' (for ricotta): not enough cottage cheese (have 200 g, need 400 g); put",
     "not enough cottage cheese"),
])
def test_short_reason(reason, expected):
    assert short_reason(reason) == expected


def test_step_labels():
    assert step_label("save_preference", {"avoid": ["eggplant"]}, "Saved: kids dislike eggplant", False) == \
        "remembered: no eggplant"
    assert step_label("save_preference", {"avoid": []}, "Already noted: no pork", False) == "already remembered"
    scan = ("Recognized 23 items in 2 photo(s) of: fridge.\nUncertain (2): a, b\n"
            "Not seen in these photos, kept and marked for the user to check (4): x")
    assert step_label("recognize_inventory", {}, scan, False) == "read 2 photos: 23 items, 2 unsure, 4 not seen"
    assert step_label("recognize_inventory", {}, "No photos are attached to this message.", False) == "no photos to read"
    assert step_label("reply", {}, None, False, "ok (off topic: fixed reply)") == "off topic"
    assert step_label("validate_suggestion", {}, ValidationResult(ok=False, missing_essential=["cream"],
                      violated_preferences=[], reason="missing: cream"), True) == "failed check (no cream)"
    assert step_label("compute_missing", {}, MissingReport(missing_essential=[], check_first=[], missing_optional=[]),
                      False) == "nothing missing"
    lasagna = MealCandidate(id="x", name="Lasagna", time_minutes=60, ingredients=[], to_buy=["ricotta", "beef"],
                            check_first=["pasta"])
    assert step_label("get_recipe", {}, lasagna, False) == "recipe for Lasagna, 2 missing, 1 not confirmed"
    assert step_label("get_recipe", {}, lasagna.model_copy(update={"to_buy": [], "check_first": []}),
                      False) == "recipe for Lasagna, nothing missing"


def test_trace_sentence_of_no_steps_is_empty():
    assert trace_sentence([]) == ""


def test_set_amount_in_the_trace():
    changes = {"changes": [{"op": "set_amount", "name": "egg", "amount": 6, "unit": "pcs"},
                           {"op": "set_amount", "name": "milk", "amount": 1.5, "unit": "l"},
                           {"op": "set_amount", "name": "cheese", "amount": None}]}
    assert args_summary("update_inventory", changes, {}) == "set_amount egg 6 pcs, set_amount milk 1.5 l, set_amount cheese cleared"
    assert result_summary("update_inventory", changes, "Applied: ...") == ("amount set 3", False)


def test_mark_bought_in_the_trace():
    from app.trace import step_label
    args = {"items": [{"name": "egg"}], "everything": True}
    content = "Bought: ground beef, pasta (now plenty).\nInventory now:\n..."
    assert args_summary("mark_bought", args, {}) == "egg, everything on the list"
    assert result_summary("mark_bought", args, content) == ("Bought: ground beef, pasta (now plenty).", False)
    assert step_label("mark_bought", args, content, False) == "marked bought (ground beef, pasta)"


def test_mark_made_in_the_trace():
    from app.models import Recipe
    from app.trace import step_label
    om = Recipe(id="om1", name="Omelette", ingredients=[], time_minutes=10)
    content = "Made Omelette. Deducted: eggs 12 → 9 pcs, spinach some → low.\nInventory now:\n..."
    assert args_summary("mark_made", {"recipe_id": "om1"}, {"om1": om}) == "Omelette"
    assert result_summary("mark_made", {}, content) == ("eggs 12 → 9 pcs, spinach some → low", False)
    assert step_label("mark_made", {}, content, False) == "took the ingredients out (eggs 12 → 9 pcs, spinach some → low)"
