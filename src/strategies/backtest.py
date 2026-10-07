"""Close-to-close accounting with drift, delayed execution and explicit cash funding."""

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from src.data_sources.market_data import validate_panel


class BacktestConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    rebalance: Literal["daily", "weekly", "monthly"] = "monthly"
    execution_lag: int = Field(default=1, ge=1, le=20)
    cost_bps: float = Field(default=5.0, ge=0, le=100)
    leverage_cap: float = Field(default=1.5, gt=0, le=5)
    funding_spread: float = Field(default=0.0, ge=0, le=1)
    initial_index: float = Field(default=100.0, gt=0)


@dataclass(frozen=True)
class BacktestResult:
    history: pd.DataFrame
    weights: pd.DataFrame
    trades: pd.DataFrame


def decision_dates(index: pd.DatetimeIndex, frequency: str) -> np.ndarray:
    """First observed session in each period; schedule needs no future observations."""
    if frequency == "daily":
        return np.ones(len(index), dtype=bool)
    periods = (
        index.tz_convert("UTC")
        .tz_localize(None)
        .to_period("W-SUN" if frequency == "weekly" else "M")
    )
    return np.asarray([True, *list(periods[1:] != periods[:-1])])


def cash_returns(index: pd.DatetimeIndex, annual_rates: pd.Series) -> pd.Series:
    """Rates at t must be known at t; accrue next interval using ACT/360, including weekends."""
    if not annual_rates.index.equals(index) or not np.isfinite(annual_rates).all():
        raise ValueError("Cash rates must be finite and exactly aligned, with no future filling")
    days = index.to_series().diff().dt.total_seconds().div(86400).fillna(0)
    return annual_rates.shift(1).fillna(0) * days / 360


def run_backtest(
    prices: pd.DataFrame,
    targets: pd.DataFrame,
    annual_cash_rates: pd.Series,
    config: BacktestConfig,
    benchmark: pd.Series | None = None,
) -> BacktestResult:
    prices = validate_panel(prices)
    if len(prices) < 3 or not prices.index.normalize().is_unique:
        raise ValueError("Backtest requires at least three daily observations")
    if not targets.index.equals(prices.index) or not targets.columns.equals(prices.columns):
        raise ValueError("Targets must match prices exactly")
    w = targets.to_numpy(float)
    if (
        not np.isfinite(w).all()
        or (w < 0).any()
        or (w.sum(axis=1) > config.leverage_cap + 1e-10).any()
    ):
        raise ValueError("Finite long-only targets within leverage cap required")
    if benchmark is None:
        benchmark = prices.iloc[:, 0]
    if (
        not benchmark.index.equals(prices.index)
        or not np.isfinite(benchmark).all()
        or (benchmark <= 0).any()
    ):
        raise ValueError("Benchmark must be positive, finite and aligned")
    rates = cash_returns(prices.index, annual_cash_rates)
    day_fractions = prices.index.to_series().diff().dt.total_seconds().fillna(0) / 86400 / 360
    decisions = decision_dates(prices.index, config.rebalance)
    nav = config.initial_index
    risky = np.zeros(prices.shape[1])
    cash = nav
    returns = prices.pct_change(fill_method=None).fillna(0).to_numpy()
    rows, weights, trades = [], [], []
    for i, timestamp in enumerate(prices.index):
        old_nav = nav
        risky *= 1 + returns[i]
        funding = config.funding_spread * day_fractions.iloc[i] if cash < 0 else 0.0
        cash *= 1 + rates.iloc[i] + funding
        before = float(risky.sum() + cash)
        if before <= 0:
            raise ValueError("Index insolvent before rebalance")
        cost, turnover = 0.0, 0.0
        decision = i - config.execution_lag
        trade = np.zeros_like(risky)
        if decision >= 0 and decisions[decision]:
            target = w[decision]
            # Solve N_after + fee * |target*N_after - current_holdings| = N_before.
            low, high = 0.0, before
            for _ in range(60):
                mid = (low + high) / 2
                fee = np.abs(target * mid - risky).sum() * config.cost_bps / 10000
                if mid + fee > before:
                    high = mid
                else:
                    low = mid
            after = (low + high) / 2
            trade = target * after - risky
            turnover = float(np.abs(trade).sum() / before)
            cost = float(np.abs(trade).sum() * config.cost_bps / 10000)
            risky = target * after
            cash = before - cost - risky.sum()
        nav = float(risky.sum() + cash)
        if nav <= 0:
            raise ValueError("Index insolvent after costs")
        rows.append(
            {
                "index": nav,
                "return": nav / old_nav - 1,
                "cash_return": rates.iloc[i],
                "cash_weight": cash / nav,
                "turnover": turnover,
                "cost": cost,
                "decision_timestamp": prices.index[decision]
                if decision >= 0 and decisions[decision]
                else pd.NaT,
            }
        )
        weights.append(risky / nav)
        trades.append(trade)
    history = pd.DataFrame(rows, index=prices.index)
    history["benchmark"] = benchmark / benchmark.iloc[0] * config.initial_index
    history["benchmark_return"] = benchmark.pct_change(fill_method=None).fillna(0)
    return BacktestResult(
        history,
        pd.DataFrame(weights, index=prices.index, columns=prices.columns),
        pd.DataFrame(trades, index=prices.index, columns=prices.columns),
    )
