from __future__ import annotations

def surprise_score(actual: float | None, forecast: float | None) -> float | None:
    """
    Simple surprise:
    (actual - forecast) / abs(forecast)
    """
    if actual is None or forecast is None:
        return None
    if forecast == 0:
        return None
    return float((actual - forecast) / abs(forecast))
