"""Observable FX context and transparent, indicative USD-equivalent risk."""

from datetime import datetime

import pandas as pd

from src.portfolio.exposures import gross_exposure_usd, leverage, net_exposure_by_ccy
from src.portfolio.models import PortfolioInput


def market_context(market: pd.DataFrame, pair: str, at: datetime) -> dict:
    available = market.loc[market.index <= at]
    if available.empty:
        return {"status": "unavailable"}
    prices = available[pair]
    return {
        "status": "stale"
        if (pd.Timestamp(at) - available.index[-1]).total_seconds() > 4 * 86400
        else "ok",
        "reference_date": available.reference_date.iloc[-1],
        "available_at": available.index[-1].isoformat(),
        "level": float(prices.iloc[-1]),
        "return_1d": float(prices.iloc[-1] / prices.iloc[-2] - 1) if len(prices) >= 2 else None,
        "return_5d": float(prices.iloc[-1] / prices.iloc[-6] - 1) if len(prices) >= 6 else None,
        "realised_vol_20d": float(prices.pct_change().tail(20).std() * 252**0.5)
        if len(prices) >= 21
        else None,
    }


def reaction(market: pd.DataFrame, pair: str, published: datetime) -> dict:
    before = market_context(market, pair, published)
    # Daily references have no precise trading timestamp: exclude the release date.
    after = market.loc[market.reference_date > published.date().isoformat(), pair]
    result = {"before": before, "post_1_reference_return": None, "post_5_reference_return": None}
    if before["status"] != "ok":
        return result
    for n in [1, 5]:
        if len(after) >= n:
            result[f"post_{n}_reference_return"] = float(after.iloc[n - 1] / before["level"] - 1)
            result[f"post_{n}_available_at"] = after.index[n - 1].isoformat()
    return result


def portfolio_risk(portfolio: PortfolioInput) -> dict:
    net = net_exposure_by_ccy(portfolio.positions)
    gross = gross_exposure_usd(portfolio.positions)
    lev = leverage(gross, portfolio.equity_usd)
    scenarios = []
    for currency in sorted(net):
        for size in [-0.02, 0.02]:
            # USD numeraire: a USD rally means all foreign currencies fall.
            moves = (
                {ccy: -size if ccy != "USD" else 0 for ccy in net}
                if currency == "USD"
                else {currency: size}
            )
            pnl = sum(
                (1 if p.direction == "long" else -1)
                * p.notional_usd
                * ((1 + moves.get(p.pair[:3], 0)) / (1 + moves.get(p.pair[3:], 0)) - 1)
                for p in portfolio.positions
            )
            scenarios.append(
                {
                    "currency": currency,
                    "shock": size,
                    "pnl_usd_approx": pnl,
                    "equity_fraction": pnl / portfolio.equity_usd,
                }
            )
    return {
        "gross_usd": gross,
        "net_usd_equivalent": net,
        "leverage": lev,
        "leverage_limit": portfolio.max_leverage,
        "leverage_breach": lev > portfolio.max_leverage,
        "drawdown": None,
        "scenarios": scenarios,
        "note": "USD-equivalent notionals; indicative static shocks, no carry/costs. Drawdown needs NAV history.",
    }
