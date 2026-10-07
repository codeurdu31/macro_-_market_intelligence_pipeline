"""Daily return statistics; undefined ratios remain null, never infinity."""

import numpy as np
import pandas as pd


def performance_summary(history: pd.DataFrame) -> dict[str, float | None]:
    r = history["return"].iloc[1:]
    excess = r - history["cash_return"].iloc[1:]
    years = (history.index[-1] - history.index[0]).total_seconds() / (86400 * 365.25)
    std = excess.std(ddof=1)
    nav = history["index"]
    return {
        "cumulative_return": float(nav.iloc[-1] / nav.iloc[0] - 1),
        "cagr": float((nav.iloc[-1] / nav.iloc[0]) ** (1 / years) - 1) if years > 0 else None,
        "annualised_volatility": float(r.std(ddof=1) * np.sqrt(252)),
        "sharpe": float(excess.mean() / std * np.sqrt(252)) if std > 1e-12 else None,
        "maximum_drawdown": float((nav / nav.cummax() - 1).min()),
        "annualised_turnover": float(history["turnover"].sum() / years) if years > 0 else None,
        "total_turnover": float(history["turnover"].sum()),
        "total_cost_index_points": float(history["cost"].sum()),
    }


def periodic_returns(history: pd.DataFrame, frequency: str) -> pd.Series:
    if frequency not in {"ME", "YE"}:
        raise ValueError("Use ME or YE")
    return (1 + history["return"]).resample(frequency).prod() - 1


def rolling_statistics(history: pd.DataFrame, window: int = 63) -> pd.DataFrame:
    if window < 2:
        raise ValueError("window must be >= 2")
    r = history["return"].copy()
    r.iloc[0] = np.nan
    excess = r - history["cash_return"]
    deviation = excess.rolling(window).std(ddof=1)
    return pd.DataFrame(
        {
            "volatility": r.rolling(window).std(ddof=1) * np.sqrt(252),
            "sharpe": excess.rolling(window).mean()
            / deviation.where(deviation > 1e-12)
            * np.sqrt(252),
        }
    )
