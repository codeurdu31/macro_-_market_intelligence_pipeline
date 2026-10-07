"""Methodology generated from the same objects used by the engine."""

from src.strategies.backtest import BacktestConfig
from src.strategies.signals import StrategyConfig


def index_methodology(strategy: StrategyConfig, engine: BacktestConfig) -> str:
    signal = (
        f"Trailing {strategy.lookback}-session return; select up to {strategy.top_n} positive-return assets."
        if strategy.name == "momentum"
        else f"{strategy.lookback}-session sample volatility of daily equal-weight basket returns, annualised sqrt(252)."
    )
    weighting = (
        "Equal weight among selected assets; cash if none qualify. Ties follow universe order."
        if strategy.name == "momentum"
        else f"Equal risky weights, scaled by {strategy.target_vol:.2%} / max(realised vol, {strategy.vol_floor:.2%})."
    )
    return f"""# Index Methodology — {strategy.name}

## Universe
{", ".join(strategy.universe)}. Input levels must share a reporting currency and aligned sessions.
Use total-return or adjusted series for investment results; price indices omit dividends.

## Signal
{signal} Warm-up remains in cash. Signals use observations available at the decision close.

## Weighting
{weighting}

## Rebalancing
{engine.rebalance}; decisions on the first observed session of each period.
Execute at the close {engine.execution_lag} observations later. Exposure earns returns only after execution.
Holdings drift between executions; no free daily rebalancing.

## Volatility control
Target {strategy.target_vol:.2%} for vol_target only; leverage capped at {strategy.leverage_cap:.2f}x.
The target is an ex-ante scaling rule, not a guarantee of realised volatility.

## Constraints
Long-only risky assets. Engine target cap {engine.leverage_cap:.2f}x; drift may exceed the cap between rebalances.
Cash = 1 - risky exposure; negative cash is borrowing. No FX hedging or survivorship correction is inferred.

## Transaction costs
{engine.cost_bps:g} bps per unit of absolute risky notional traded (buys plus sells, not divided by two).
Fees include initial investment and are deducted at the execution close; no terminal liquidation.

## Index calculation
Base {engine.initial_index:g}. Self-financing holdings plus cash, net of fees.
Cash accrues at the prior observation's known annual rate on ACT/360 calendar days.
Borrowing pays that rate plus {engine.funding_spread:.2%}. Input rates are decimals, not percentages.
Daily risk statistics use 252 sessions/year; CAGR uses actual elapsed days / 365.25.
Sharpe uses returns in excess of the cash accrual; undefined ratios are null.
Benchmark is frictionless buy-and-hold over the same dates; warm-up is included in both comparisons.
"""
