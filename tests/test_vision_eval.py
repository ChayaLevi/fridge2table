import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "run_vision_eval", Path(__file__).resolve().parent.parent / "eval" / "run_vision_eval.py")
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)


def test_score_set_matches_names_alts_and_synonyms():
    labels = [{"name": "milk", "alt": ["whole milk"]}, {"name": "green onion"}, {"name": "egg"}, {"name": "tofu"}]
    predicted = [("whole milk", False), ("scallion", False), ("egg", False), ("ketchup", False), ("white container", True)]
    r = ev.score_set(labels, predicted)
    assert r["found"] == ["milk", "green onion", "egg"]
    assert r["missed"] == ["tofu"]
    assert r["hallucinated"] == ["ketchup"]  # the uncertain container does not count


def test_aggregate_and_table():
    rows = [
        {"set": "a_fridge", "location": "fridge", "photos": 2, "labels": 4, "found": ["x", "y", "z"],
         "missed": ["w"], "hallucinated": ["q", "r"], "latencies_s": [2.0, 4.0]},
        {"set": "a_pantry", "location": "pantry", "photos": 1, "labels": 4, "found": ["x"],
         "missed": ["a", "b", "c"], "hallucinated": [], "latencies_s": [3.0]},
    ]
    agg = ev.aggregate(rows)
    assert agg["recall"] == 0.5 and agg["halluc_per_photo"] == 2 / 3 and agg["latency_s"] == 3.0
    text = ev.table(rows)
    assert "| a_fridge | fridge | 2 | 75% (3/4) | 1.0 | 3.0 s |" in text
    assert "**all pantry**" in text and "**overall**" in text and "**all freezer**" not in text
