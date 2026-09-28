from rewards.money import format_vnd


def test_symbol_comes_first():
    # The new design puts the currency symbol first; money.py has not caught up yet.
    assert format_vnd(1000) == "₫1.000"
