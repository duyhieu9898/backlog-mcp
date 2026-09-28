from rewards.referral import Order, referral_reward


def test_gift_nft_earns_no_referral_reward():
    assert referral_reward(Order(price=500_000, is_gift=True)) == 0


def test_paid_order_still_earns_ten_percent():
    assert referral_reward(Order(price=500_000)) == 50_000
