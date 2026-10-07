from __future__ import annotations
from collections import defaultdict
from src.portfolio.models import FxPosition


def _split_pair(pair: str) -> tuple[str, str]:
    pair = pair.strip().upper()
    if len(pair) != 6:
        raise ValueError(f"Invalid FX pair format: {pair}")
    return pair[:3], pair[3:]


def gross_exposure_usd(positions: list[FxPosition]) -> float:
    return float(sum(p.notional_usd for p in positions))


def net_exposure_by_ccy(positions: list[FxPosition]) -> dict[str, float]:
    """
    Simplified exposure accounting (in USD notionals):
    - Long EURUSD => +EUR, -USD
    - Short EURUSD => -EUR, +USD
    """
    expo = defaultdict(float)

    for p in positions:
        base, quote = _split_pair(p.pair)
        sign = 1.0 if p.direction == "long" else -1.0

        expo[base] += sign * p.notional_usd
        expo[quote] -= sign * p.notional_usd

    return dict(expo)


def leverage(gross_usd: float, equity_usd: float) -> float:
    return float(gross_usd / equity_usd)
