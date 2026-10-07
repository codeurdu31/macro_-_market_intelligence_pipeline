from __future__ import annotations
from src.portfolio.models import FxPosition


def stress_pnl_usd(
    positions: list[FxPosition],
    shock: float,
    cost_bps: float = 2.0,
) -> float:
    """
    Simple stress:
    pnl = sum(direction * notional_usd * shock) - costs

    cost_bps applies on gross exposure.
    """
    gross = sum(p.notional_usd for p in positions)
    costs = gross * (cost_bps / 10000.0)

    pnl = 0.0
    for p in positions:
        sign = 1.0 if p.direction == "long" else -1.0
        pnl += sign * p.notional_usd * shock

    return float(pnl - costs)
