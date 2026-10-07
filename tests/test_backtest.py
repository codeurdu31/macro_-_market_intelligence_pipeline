import numpy as np
import pandas as pd
import pytest

from src.analytics.performance import performance_summary, periodic_returns, rolling_statistics
from src.strategies.backtest import BacktestConfig, run_backtest
from src.strategies.methodology import index_methodology
from src.strategies.signals import StrategyConfig, generate_signals


def inputs(values):
    idx = pd.bdate_range("2024-01-01", periods=len(values), tz="UTC")
    prices = pd.DataFrame({"A": values}, index=idx)
    return prices, pd.Series(0.0, index=idx)


def test_lag_does_not_earn_return_before_execution():
    prices, cash = inputs([100, 200, 400, 400])
    targets = prices * 0 + 1
    result = run_backtest(prices, targets, cash, BacktestConfig(rebalance="daily", cost_bps=0))
    np.testing.assert_allclose(result.history["index"], [100, 100, 200, 200])
    assert result.history.decision_timestamp.iloc[1] == prices.index[0]


def test_drift_and_no_hidden_rebalance():
    prices, cash = inputs([100, 100, 200, 200])
    result = run_backtest(
        prices, prices * 0 + 0.5, cash, BacktestConfig(rebalance="monthly", cost_bps=0)
    )
    assert result.history["index"].iloc[2] == pytest.approx(150)
    assert result.weights.A.iloc[2] == pytest.approx(2 / 3)
    assert result.history.turnover.iloc[2] == 0
    np.testing.assert_allclose(result.weights.sum(axis=1) + result.history.cash_weight, 1)


def test_transaction_cost_self_financing():
    prices, cash = inputs([100, 100, 100, 100])
    result = run_backtest(prices, prices * 0 + 1, cash, BacktestConfig(cost_bps=100))
    assert result.history["index"].iloc[-1] == pytest.approx(100 / 1.01)
    assert result.history.cost.sum() == pytest.approx(100 - 100 / 1.01)
    assert result.history.turnover.sum() == pytest.approx(1 / 1.01)


def test_cash_weekend_and_borrowing():
    idx = pd.to_datetime(["2024-01-04", "2024-01-05", "2024-01-08"], utc=True)
    prices = pd.DataFrame({"A": [100, 100, 100]}, index=idx)
    cash = pd.Series(0.036, index=idx)
    result = run_backtest(prices, prices * 0, cash, BacktestConfig(cost_bps=0))
    assert result.history["index"].iloc[-1] == pytest.approx(100 * 1.0001 * 1.0003)
    leveraged = run_backtest(
        prices, prices * 0 + 1.5, cash, BacktestConfig(cost_bps=0, funding_spread=0.036)
    )
    assert leveraged.history["return"].iloc[-1] == pytest.approx(-0.5 * 0.072 * 3 / 360)


@pytest.mark.parametrize("name", ["momentum", "vol_target"])
def test_future_mutation_cannot_change_past(name):
    rng = np.random.default_rng(1)
    prices, cash = inputs(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 100))))
    config = StrategyConfig(name=name, universe=["A"], lookback=5)
    first = generate_signals(prices, config)
    changed = prices.copy()
    changed.iloc[70:] *= 3
    second = generate_signals(changed, config)
    pd.testing.assert_frame_equal(first.targets.iloc[:70], second.targets.iloc[:70])
    engine = BacktestConfig(rebalance="weekly")
    a = run_backtest(prices, first.targets, cash, engine)
    b = run_backtest(changed, second.targets, cash, engine)
    pd.testing.assert_frame_equal(a.history.iloc[:70], b.history.iloc[:70])


def test_momentum_selection_and_warmup():
    idx = pd.bdate_range("2024-01-01", periods=4, tz="UTC")
    prices = pd.DataFrame({"A": [100, 101, 103, 104], "B": [100, 99, 98, 97]}, index=idx)
    signals = generate_signals(
        prices, StrategyConfig(name="momentum", universe=["A", "B"], lookback=2)
    )
    assert signals.targets.iloc[:2].sum().sum() == 0
    np.testing.assert_allclose(signals.targets.iloc[2:].A, 1)
    np.testing.assert_allclose(signals.targets.B, 0)


def test_vol_target_formula_cap_and_zero_vol():
    prices, _ = inputs([100, 101, 99, 103, 98, 102])
    config = StrategyConfig(name="vol_target", universe=["A"], lookback=3, target_vol=0.1)
    signals = generate_signals(prices, config)
    expected = prices.A.pct_change().iloc[-3:].std(ddof=1) * np.sqrt(252)
    assert signals.targets.A.iloc[-1] == pytest.approx(min(1.5, 0.1 / expected))
    constant = generate_signals(prices * 0 + 100, config)
    assert constant.targets.A.iloc[-1] == 1.5
    assert constant.targets.A.iloc[:3].sum() == 0


def test_validation():
    prices, cash = inputs([100, 100, 100])
    with pytest.raises(ValueError):
        BacktestConfig(execution_lag=0)
    with pytest.raises(ValueError):
        run_backtest(prices, prices * 0 + 2, cash, BacktestConfig())
    with pytest.raises(ValueError):
        run_backtest(prices, prices * 0, cash.iloc[:-1], BacktestConfig())
    prices.iloc[1, 0] = np.nan
    with pytest.raises(ValueError):
        generate_signals(prices, StrategyConfig(name="momentum", universe=["A"], lookback=2))


def test_metrics_known_drawdown_periods_and_undefined_sharpe():
    idx = pd.bdate_range("2024-01-01", periods=4, tz="UTC")
    history = pd.DataFrame(
        {
            "index": [100, 110, 88, 100],
            "return": [0, 0.1, -0.2, 100 / 88 - 1],
            "cash_return": 0,
            "turnover": 0,
            "cost": 0,
        },
        index=idx,
    )
    assert performance_summary(history)["maximum_drawdown"] == pytest.approx(-0.2)
    assert periodic_returns(history, "ME").iloc[0] == pytest.approx(0, abs=1e-12)
    assert periodic_returns(history, "YE").iloc[0] == pytest.approx(0, abs=1e-12)
    assert rolling_statistics(history, 2).volatility.iloc[-1] > 0
    history["return"] = 0
    assert performance_summary(history)["sharpe"] is None


def test_methodology_from_actual_configuration():
    text = index_methodology(
        StrategyConfig(name="vol_target", universe=["A"], target_vol=0.08),
        BacktestConfig(cost_bps=7, execution_lag=2),
    )
    assert "8.00%" in text and "7 bps" in text and "2 observations" in text
