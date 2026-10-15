"""T5.2: the latency script's pure parts (no network): step breakdown, summary, table, RESULTS.md block."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

import run_latency as rl  # noqa: E402
from app.models import StepTiming  # noqa: E402


def step(kind, name, seconds, detail="", tin=None, tout=None):
    return StepTiming(kind=kind, name=name, seconds=seconds, detail=detail, input_tokens=tin, output_tokens=tout)


STEPS = [
    step("model", "agent deepseek-v4-pro", 2.0, "-> suggest_meals", 3000, 40),
    step("model", "recipe deepseek-flash", 5.0, "-> final_result", 1200, 1300),
    step("tool", "suggest_meals", 6.5),
    step("model", "agent deepseek-v4-pro", 2.5, "-> reply", 4000, 90),
    step("check", "output check", 0.0, "output check failed: 4 meals; show at most 3"),
    step("model", "agent deepseek-v4-pro", 1.5, "-> reply", 4100, 80),
    step("check", "output check", 0.0, "ok"),
]


def test_breakdown_splits_agent_and_tool_models():
    b = rl.breakdown(12.0, STEPS)
    assert (b.total, b.agent, b.tools_llm, b.agent_calls, b.last_agent, b.retries) == (12.0, 6.0, 5.0, 3, 1.5, 1)
    assert (b.input_tokens, b.output_tokens) == (12300, 1510)
    assert b.other == 1.0


def test_breakdown_of_no_steps_and_other_never_negative():
    b = rl.breakdown(3.0, [step("model", "vision deepseek-flash", 5.0)])  # parallel vision calls
    assert b.agent_calls == 0 and b.last_agent == 0.0 and b.tools_llm == 5.0 and b.other == 0.0


def test_summarize_and_table():
    runs = [rl.breakdown(t, STEPS) for t in (10.0, 12.0, 30.0)]
    s = rl.summarize(runs)
    assert (s["n"], s["median"], s["max"], s["retries"]) == (3, 12.0, 30.0, 3)
    md = rl.table({"mode_a": s, "steps": s}, {"mode_a": "Mode A"})
    lines = md.splitlines()
    assert lines[0].startswith("| Case | Runs | Median | Max | Target |")
    assert lines[2].startswith("| Mode A | 3 | 12.0 s | 30.0 s | < 25 s ✗ |")
    assert lines[3].startswith("| steps | 3 | 12.0 s | 30.0 s | - |")  # no target, label falls back to the key


def test_write_results_replaces_only_the_latency_block(tmp_path):
    path = tmp_path / "RESULTS.md"
    rl.write_results("old table", path)
    assert path.read_text(encoding="utf-8") == f"# Evaluation results\n\n{rl.BEGIN}\nold table\n{rl.END}\n"
    path.write_text(path.read_text(encoding="utf-8") + "\n### Notes\nkeep me\n", encoding="utf-8")
    rl.write_results("new table", path)
    text = path.read_text(encoding="utf-8")
    assert "new table" in text and "old table" not in text and text.endswith("### Notes\nkeep me\n")
