import pytest

from app.amounts import default_unit, format_amount, parse_amount, same_kind, split_amount, to_base


@pytest.mark.parametrize("text, want", [
    ("300 g", (300, "g")),
    ("1.5 kg", (1.5, "kg")),
    ("2", (2, "pcs")),
    ("500ml", (500, "ml")),
    ("2 l", (2, "l")),
    ("2 L", (2, "l")),
    ("500 mL", (500, "ml")),
    ("1,5 kg", (1.5, "kg")),
    ("1,000 g", (1000, "g")),
    ("1/2 l", (0.5, "l")),
    ("1 1/2 kg", (1.5, "kg")),
    (".5 l", (0.5, "l")),
    ("200 grams", (200, "g")),
    ("1 kilo", (1, "kg")),
    ("2 liters", (2, "l")),
    ("1 litre", (1, "l")),
    ("3 pieces", (3, "pcs")),
    ("4 pcs", (4, "pcs")),
    ("1 pack", (1, "pack")),
    ("2 packets", (2, "pack")),
    ("a pack", (1, "pack")),
    ("about 300 g", (300, "g")),
    ("~200 ml", (200, "ml")),
    ("300 g (2 cups)", (300, "g")),
    ("400 g, drained", (400, "g")),
    ("  250  g  ", (250, "g")),
    ("5 large", (5, "pcs")),
    ("2 medium, diced", (2, "pcs")),
])
def test_parse_amount(text, want):
    assert parse_amount(text) == want


@pytest.mark.parametrize("text", [
    "a handful", "to taste", "", "a pinch", "2 tbsp", "1 tsp", "2 cloves", "1 lb", "16 oz", "2 cups",
    "2 lemons", "0", "0 g", "some", "half", "1/0 l",
])
def test_parse_amount_none(text):
    assert parse_amount(text) is None


def test_to_base():
    assert to_base(1.5, "kg") == (1500, "g")
    assert to_base(2, "l") == (2000, "ml")
    assert to_base(300, "g") == (300, "g")
    assert to_base(250, "ml") == (250, "ml")
    assert to_base(6, "pcs") == (6, "pcs")
    assert to_base(2, "pack") == (2, "pack")


def test_same_kind():
    assert same_kind("g", "kg") and same_kind("l", "ml") and same_kind("pcs", "pcs")
    assert not same_kind("g", "ml") and not same_kind("pack", "pcs") and not same_kind("kg", "l")


@pytest.mark.parametrize("amount, unit, want", [
    (1500, "g", "1.5 kg"),
    (0.5, "l", "500 ml"),
    (2, "l", "2 l"),
    (500, "g", "500 g"),
    (1000, "ml", "1 l"),
    (0.25, "kg", "250 g"),
    (6, "pcs", "6 pcs"),
    (1, "pack", "1 pack"),
    (3, "pack", "3 packs"),
    (1 / 3, "l", "333.33 ml"),
    (2.0, "kg", "2 kg"),
    (None, None, ""),
    (2, None, ""),
])
def test_format_amount(amount, unit, want):
    assert format_amount(amount, unit) == want


@pytest.mark.parametrize("category, name, want", [
    ("egg", "egg", "pcs"), ("fruit", "apple", "pcs"), ("vegetable", "carrot", "pcs"),
    ("meat", "chicken", "g"), ("fish", "salmon", "g"), ("dairy", "cheddar", "g"), ("grain", "rice", "g"),
    ("pasta", "pasta", "g"), ("baking", "sugar", "g"),
    ("drink", "orange juice", "l"), ("dairy", "milk", "l"), ("sauce", "soy sauce", "ml"),
    ("other", "thing", "pcs"), ("spice", "salt", "pcs"),
])
def test_default_unit(category, name, want):
    assert default_unit(category, name) == want


@pytest.mark.parametrize("text, want", [
    ("milk 2 l", ("milk", 2, "l")),
    ("milk 2l", ("milk", 2, "l")),
    ("6 eggs", ("eggs", 6, None)),
    ("eggs 6", ("eggs", 6, None)),
    ("2 liters of milk", ("milk", 2, "l")),
    ("500g flour", ("flour", 500, "g")),
    ("greek yogurt 500 g", ("greek yogurt", 500, "g")),
    ("a pack of butter", ("butter", 1, "pack")),
    ("chicken 1.5 kg", ("chicken", 1.5, "kg")),
])
def test_split_amount(text, want):
    assert split_amount(text) == want


@pytest.mark.parametrize("text", ["milk", "7up", "6eggs", "ham 3 slices", "", "00 flour", "vitamin b12"])
def test_split_amount_none(text):
    assert split_amount(text) is None
