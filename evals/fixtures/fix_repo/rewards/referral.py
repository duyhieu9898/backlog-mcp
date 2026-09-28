from dataclasses import dataclass

REFERRAL_RATE = 0.10


@dataclass
class Order:
    price: int
    is_gift: bool = False


def referral_reward(order: Order) -> int:
    """Reward paid to the buyer's referrer, in VND."""
    return round(order.price * REFERRAL_RATE)
