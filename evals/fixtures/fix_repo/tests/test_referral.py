from rewards.referral import Order, referral_reward


def test_reward_is_ten_percent_of_price():
    assert referral_reward(Order(price=200_000)) == 20_000
