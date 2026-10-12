import json

import pytest

from app.config import STAPLES_PATH, SYNONYMS_PATH
from app.tools.normalize import _index, normalize, same_ingredient

CASES = [
    # plurals
    ("tomatoes", "tomato"),
    ("potatoes", "potato"),
    ("berries", "berry"),
    ("strawberries", "strawberry"),
    ("leaves", "leaf"),
    ("bay leaves", "bay leaf"),
    ("loaves", "loaf"),
    ("peaches", "peach"),
    ("radishes", "radish"),
    ("boxes", "box"),
    ("carrots", "carrot"),
    ("olives", "olive"),
    ("cheeses", "cheese"),
    ("sausages", "sausage"),
    ("cookies", "cookie"),
    ("pies", "pie"),
    ("chilies", "chili"),
    ("chillies", "chili"),
    ("quiches", "quiche"),
    ("kiwis", "kiwi"),
    ("zucchinis", "zucchini"),
    ("avocados", "avocado"),
    ("lentils", "lentil"),
    ("chickpeas", "chickpea"),
    ("brussels sprouts", "brussels sprout"),
    # already singular
    ("watercress", "watercress"),
    ("lemongrass", "lemongrass"),
    ("tomato", "tomato"),
    ("egg", "egg"),
    ("pea", "pea"),
    # exceptions that must not be singularized
    ("asparagus", "asparagus"),
    ("hummus", "hummus"),
    ("couscous", "couscous"),
    ("molasses", "molasses"),
    ("Swiss Chard", "swiss chard"),
    ("citrus", "citrus"),
    # descriptor words
    ("fresh spinach", "spinach"),
    ("Organic Milk", "milk"),
    ("large eggs", "egg"),
    ("Extra-Large Eggs", "egg"),
    ("small onions", "onion"),
    ("chopped onions", "onion"),
    ("sliced mushrooms", "mushroom"),
    ("diced tomatoes", "tomato"),
    ("minced garlic", "garlic"),
    ("boneless skinless chicken breast", "chicken"),
    ("frozen peas", "pea"),
    ("grated parmesan cheese", "parmesan"),
    # a known name wins over descriptor stripping
    ("minced beef", "ground beef"),
    ("frozen yogurt", "frozen yogurt"),
    ("fresh coriander", "cilantro"),
    # case, spacing, punctuation, accents
    ("  Greek   Yogurt ", "greek yogurt"),
    ("GREEK YOGHURT", "greek yogurt"),
    ("milk (2%)", "milk"),
    ("jalapeños", "jalapeno"),
    ("Crème Fraîche", "creme fraiche"),
    ("baker's yeast", "bakers yeast"),
    ("stir-fry sauce", "stir fry sauce"),
    ("stir fry sauce", "stir fry sauce"),
    # "X, Y" ingredient-list form
    ("tomatoes, canned", "canned tomato"),
    ("chicken, boneless, skinless", "chicken"),
    # quantities
    ("2 eggs", "egg"),
    ("a dozen eggs", "egg"),
    ("500 g of flour", "all-purpose flour"),
    ("500g flour", "all-purpose flour"),
    ("1/2 cup milk", "milk"),
    ("½ cup milk", "milk"),
    ("1.5 kg potatoes", "potato"),
    ("milk 1l", "milk"),
    ("3 cloves garlic", "garlic"),
    ("a clove of garlic", "garlic"),
    ("a can of chickpeas", "chickpea"),
    ("2 tins of tomatoes", "tomato"),
    ("a pinch of salt", "salt"),
    ("a handful of fresh spinach", "spinach"),
    ("half an onion", "onion"),
    ("some milk", "milk"),
    # unit words are kept when they are not quantities
    ("cloves", "clove"),
    ("2 cloves", "clove"),
    ("white container", "white container"),
    # synonyms
    ("scallion", "green onion"),
    ("Spring Onion", "green onion"),
    ("spring onions", "green onion"),
    ("scallions", "green onion"),
    ("chicken thighs", "chicken"),
    ("chicken drumstick", "chicken"),
    ("cilantro", "cilantro"),
    ("capsicum", "bell pepper"),
    ("red bell peppers", "red bell pepper"),  # not a synonym: stays specific
    ("heavy cream", "cream"),
    ("double cream", "cream"),
    ("whipping cream", "cream"),
    ("ground beef", "ground beef"),
    ("courgettes", "zucchini"),
    ("aubergine", "eggplant"),
    ("half & half", "half-and-half"),
    ("half and half", "half-and-half"),
    # hyphen- and plural-insensitive matching of known names
    ("all purpose flour", "all-purpose flour"),
    ("all-purpose flour", "all-purpose flour"),
    ("chili flakes", "chili flakes"),
    ("chili flake", "chili flakes"),
    ("chilli flakes", "chili flakes"),
    ("red pepper flakes", "chili flakes"),
    ("free range eggs", "egg"),
    # edge cases
    ("", ""),
    ("   ", ""),
    ("2", ""),
    ("fresh", "fresh"),
]


@pytest.mark.parametrize("raw,expected", CASES)
def test_normalize(raw, expected):
    assert normalize(raw) == expected


def _data():
    synonyms = json.loads(SYNONYMS_PATH.read_text(encoding="utf-8"))
    staples = json.loads(STAPLES_PATH.read_text(encoding="utf-8"))
    return synonyms, staples


def test_index_builds_without_conflicts():
    assert _index()  # raises ValueError if two variants collide on different canonical names


def test_canonical_names_are_fixed_points():
    synonyms, staples = _data()
    for name in {*synonyms.values(), *staples}:
        assert normalize(name) == name


def test_every_synonym_key_resolves():
    synonyms, _ = _data()
    for variant, canonical in synonyms.items():
        assert normalize(variant) == canonical, variant


def test_normalize_is_idempotent():
    synonyms, staples = _data()
    for raw in [r for r, _ in CASES] + list(synonyms) + staples:
        once = normalize(raw)
        assert normalize(once) == once, raw


def test_same_ingredient():
    assert same_ingredient("Tomatoes", "tomato")
    assert same_ingredient("spring onion", "scallions")
    assert same_ingredient("chicken breast", "chicken thigh")
    assert same_ingredient("2 large eggs", "egg")
    assert same_ingredient("chilli flakes", "chili flakes")
    assert same_ingredient("plain flour", "all-purpose flour")
    assert not same_ingredient("milk", "cream")
    assert not same_ingredient("ground beef", "beef")
    assert not same_ingredient("cloves", "garlic")
    assert not same_ingredient("", "")
    assert not same_ingredient("2", "")
