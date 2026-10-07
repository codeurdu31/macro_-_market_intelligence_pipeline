from __future__ import annotations
from src.copilot.schemas import MacroSignal


def macro_fx_alerts(
    signals: list[MacroSignal],
    net_expo_by_ccy: dict[str, float],
    threshold_usd: float = 20000.0,
) -> list[str]:
    """
    Alert if a macro signal currency intersects with a big net exposure.
    """
    alerts: list[str] = []

    for s in signals:
        for ccy in s.currencies:
            expo = net_expo_by_ccy.get(ccy.upper(), 0.0)
            if abs(expo) >= threshold_usd:
                direction = "LONG" if expo > 0 else "SHORT"
                alerts.append(
                    f"MACRO_RISK: {ccy} signal touches exposure {direction} {expo:,.0f} USD | "
                    f"event={s.event_type} hawk={s.hawkishness:+.2f} surprise={s.surprise:+.2f}"
                )

    return alerts
