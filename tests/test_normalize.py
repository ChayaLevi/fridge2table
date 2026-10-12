import pytest

from app.tools.normalize import normalize, same_ingredient


@pytest.mark.parametrize("raw,expected", [
    # plurals
    ("tomatoes", "tomato"),
    ("potatoes", "potato"),
    ("berries", "berry"),
    ("strawberries", "strawberry"),
    ("leaves", "leaf"),
    ("bay leaves", "bay leaf"),
    ("peaches", "peach"),
    ("radishes", "radish"),
    ("carrots", "carrot"),
    ("olives", "olive"),
    ("cheeses", "cheese"),
    ("sausages", "sausage"),
    ("cookies", "cookie"),
    ("pies", "pie"),
    ("lentils", "lentil"),
    ("chickpeas", "chickpea"),
    ("brussels sprouts", "brussels sprout"),
    # already singular / ending in ss, us, is
    ("watercress", "watercress"),
    ("lemongrass", "lemongrass"),
    ("tomato", "tomato"),
    # exceptions
    ("asparagus", "asparagus"),
    ("hummus", "hummus"),
    ("couscous", "couscous"),
    ("molasses", "molasses"),
    ("Swiss Chard", "swiss chard"),
    # adjectives
    ("fresh spinach", "spinach"),
    ("Organic Milk", "milk"),
    ("large eggs", "egg"),
    ("chopped onions", "onion"),
    ("boneless skinless chicken breast", "chicken"),
    ("diced tomatoes", "tomato"),
    # case, spaces, quantities, parentheticals
    ("  Greek   Yogurt ", "greek yogurt"),
    ("2 eggs", "egg"),
    ("500 g of flour", "all-purpose flour"),
    ("milk (2%)", "milk"),
    # synonyms
    ("scallion", "green onion"),
    ("Spring Onion", "green onion"),
    ("scallions", "green onion"),
    ("chicken thighs", "chicken"),
    ("chicken drumstick", "chicken"),
    ("fresh coriander", "cilantro"),
    ("capsicum", "bell pepper"),
    ("heavy cream", "cream"),
    ("double cream", "cream"),
    ("minced beef", "ground beef"),
    ("courgettes", "zucchini"),
    ("aubergine", "eggplant"),
    # edge cases
    ("", ""),
    ("fresh", "fresh"),
])
def test_normalize(raw, expected):
    assert normalize(raw) == expected


def test_normalize_is_idempotent():
    for raw in ["Scallions", "chicken breasts", "tomatoes", "Heavy Cream", "bay leaves", "minced beef"]:
        once = normalize(raw)
        assert normalize(once) == once


def test_same_ingredient():
    assert same_ingredient("Tomatoes", "tomato")
    assert same_ingredient("spring onion", "scallions")
    assert same_ingredient("chicken breast", "chicken thigh")
    assert not same_ingredient("milk", "cream")
    assert not same_ingredient("", "")
