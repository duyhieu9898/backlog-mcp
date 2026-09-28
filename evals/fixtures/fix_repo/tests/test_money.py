from rewards.money import format_vnd


def test_thousands_use_dots():
    assert format_vnd(1000) == "1.000 ₫"
