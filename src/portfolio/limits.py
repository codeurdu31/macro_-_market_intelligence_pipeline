from __future__ import annotations


def check_limits(
    lev: float,
    dd: float,
    max_leverage: float,
    max_drawdown: float,
) -> list[str]:
    breaches: list[str] = []

    if lev > max_leverage:
        breaches.append(f"LEVERAGE_BREACH lev={lev:.2f} > max={max_leverage:.2f}")

    if dd > max_drawdown:
        breaches.append(f"DRAWDOWN_BREACH dd={dd:.2%} > max={max_drawdown:.2%}")

    return breaches
