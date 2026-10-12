import json

from app.config import STAPLES_PATH, SYNONYMS_PATH


def test_staples_load():
    staples = json.loads(STAPLES_PATH.read_text(encoding="utf-8"))
    assert len(staples) == 15
    assert all(isinstance(s, str) and s == s.lower().strip() for s in staples)
    assert len(set(staples)) == len(staples)
    assert {"salt", "soy sauce", "water"} <= set(staples)


def test_synonyms_load():
    syn = json.loads(SYNONYMS_PATH.read_text(encoding="utf-8"))
    assert len(syn) >= 60
    for k, v in syn.items():
        assert isinstance(k, str) and isinstance(v, str)
        assert k == k.lower().strip() and v == v.lower().strip()
    assert syn["scallion"] == "green onion"
    assert syn["spring onion"] == "green onion"
    assert syn["chicken thigh"] == "chicken"
    assert syn["fresh coriander"] == "cilantro"
    assert syn["capsicum"] == "bell pepper"
    assert syn["double cream"] == "cream"
    assert syn["minced beef"] == "ground beef"
    assert syn["courgette"] == "zucchini"
    assert syn["aubergine"] == "eggplant"


def test_synonym_targets_are_canonical():
    # a target must not itself be remapped to something else (no chains)
    syn = json.loads(SYNONYMS_PATH.read_text(encoding="utf-8"))
    for k, v in syn.items():
        assert syn.get(v, v) == v, f"{k} -> {v} -> {syn[v]}"
