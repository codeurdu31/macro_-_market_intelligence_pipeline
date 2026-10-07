"""Manual, offline-first entry point: python -m scripts.run_qis_lab."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from src.analytics.events import AssetInfo, event_reaction, load_events_csv, similar_event_history
from src.analytics.performance import performance_summary, periodic_returns, rolling_statistics
from src.data_sources.demo_data import write_demo_inputs
from src.data_sources.market_data import load_market_csv
from src.portfolio.exposures import gross_exposure_usd, leverage, net_exposure_by_ccy
from src.portfolio.models import PortfolioInput
from src.scenarios.stress import stress_pnl_usd
from src.reporting.markets import desk_report, plot_backtest
from src.strategies.backtest import BacktestConfig, run_backtest
from src.strategies.methodology import index_methodology
from src.strategies.signals import StrategyConfig, generate_signals

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/markets_demo.json")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/qis_lab")
    parser.add_argument(
        "--input-dir",
        type=Path,
        help="CSV directory: market, cash, events; otherwise synthetic demo",
    )
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    as_of = pd.Timestamp(cfg["as_of"])
    if as_of.tzinfo is None:
        raise ValueError("as_of must include timezone")
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    synthetic = args.input_dir is None
    data_label = "SYNTHETIC DEMONSTRATION" if synthetic else "IMPORTED CSV — verify source metadata"
    paths = (
        write_demo_inputs(out / "inputs", cfg["seed"], cfg["observations"], as_of)
        if synthetic
        else {name: args.input_dir / f"{name}.csv" for name in ["market", "cash", "events"]}
    )
    market = load_market_csv(paths["market"], positive=False).loc[:as_of]
    cash = load_market_csv(paths["cash"], positive=False).loc[:as_of, "annual_rate"]
    strategy = StrategyConfig.model_validate(cfg["strategy"])
    engine = BacktestConfig.model_validate(cfg["backtest"])
    if strategy.leverage_cap > engine.leverage_cap:
        raise ValueError("Strategy leverage cap exceeds engine cap")
    if not synthetic and "assets" not in cfg:
        raise ValueError(
            "Imported data requires assets metadata (kind, source, currency) in config"
        )
    default_assets = {
        name: {
            "kind": "yield_percent"
            if name.startswith("US") and name.endswith("Y")
            else "vol_index"
            if name == "VIX"
            else "price",
            "source": "SYNTHETIC",
            "currency": "EUR" if name == "SX5E_EUR" else "JPY" if name == "USDJPY" else "USD",
        }
        for name in market.columns
    }
    assets = {
        name: AssetInfo.model_validate(spec)
        for name, spec in cfg.get("assets", default_assets).items()
    }
    if any(assets[name].kind != "price" for name in [*strategy.universe, cfg["benchmark"]]):
        raise ValueError("Yield levels / VIX are not investable backtest price series")
    if len({assets[name].currency for name in [*strategy.universe, cfg["benchmark"]]}) != 1:
        raise ValueError("Strategy and benchmark must use a common reporting currency")
    results = {}
    for name in ("momentum", "vol_target"):
        scfg = StrategyConfig.model_validate({**strategy.model_dump(), "name": name})
        selected = market[scfg.universe]
        signals = generate_signals(selected, scfg)
        bt = run_backtest(selected, signals.targets, cash, engine, market[cfg["benchmark"]])
        stats = rolling_statistics(bt.history)
        for filename, table in {
            "history": bt.history,
            "weights": bt.weights,
            "trades": bt.trades,
            "signals": signals.values,
            "targets": signals.targets,
            "rolling": stats,
            "monthly": periodic_returns(bt.history, "ME"),
            "yearly": periodic_returns(bt.history, "YE"),
        }.items():
            table.to_csv(out / f"{name}_{filename}.csv")
        results[name] = performance_summary(bt.history)
        reference = bt.history.copy()
        reference["index"] = reference["benchmark"]
        reference["return"] = reference["benchmark_return"]
        reference[["turnover", "cost"]] = 0.0
        results[f"{name}_benchmark"] = performance_summary(reference)
        (out / f"{name}_methodology.md").write_text(
            index_methodology(scfg, engine), encoding="utf-8"
        )
        plot_backtest(
            bt,
            stats,
            out / f"{name}.png",
            label=f"{data_label} / {name}",
            target_vol=scfg.target_vol if name == "vol_target" else None,
        )
    events = load_events_csv(paths["events"])
    intraday_path = paths["market"].parent / "intraday.csv"
    intraday = load_market_csv(intraday_path, positive=False) if intraday_path.exists() else None
    reactions = pd.DataFrame(
        [
            {
                **event_reaction(
                    market[asset],
                    event,
                    assets[asset],
                    as_of,
                    intraday=intraday[asset]
                    if intraday is not None and asset in intraday
                    else None,
                ),
                "asset": asset,
            }
            for event in events
            for asset in market.columns
        ]
    )
    if not reactions.empty:
        reactions.to_csv(out / "event_reactions.csv", index=False)
        (out / "desk_report.md").write_text(desk_report(reactions, as_of), encoding="utf-8")
        similar_event_history(reactions, "US CPI", as_of).to_csv(out / "cpi_history.csv")
    else:
        (out / "desk_report.md").write_text(
            "# Trading desk\n\nNo events supplied; event coverage unavailable.\n", encoding="utf-8"
        )
    portfolio = PortfolioInput.model_validate_json((ROOT / "data/portfolio_demo.json").read_text())
    gross = gross_exposure_usd(portfolio.positions)
    results["legacy_fx_risk"] = {
        "gross_usd": gross,
        "net_usd_equivalent": net_exposure_by_ccy(portfolio.positions),
        "leverage": leverage(gross, portfolio.equity_usd),
        "legacy_common_pair_shock_down": stress_pnl_usd(portfolio.positions, -0.02),
        "drawdown": None,
        "note": "Existing simplified FX model; drawdown unavailable",
    }
    if intraday is not None:
        paths["intraday"] = intraday_path
    results["provenance"] = {
        "synthetic": True if synthetic else None,
        "data_mode": "generated_synthetic" if synthetic else "imported_csv",
        "as_of": as_of.isoformat(),
        "config": cfg,
        "assets": {name: asset.model_dump() for name, asset in assets.items()},
        "inputs_sha256": {
            name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()
        },
    }
    (out / "summary.json").write_text(
        json.dumps(results, indent=2, allow_nan=False), encoding="utf-8"
    )
    (out / "README.md").write_text(
        "# Markets Lab run\n\n"
        + (
            "SYNTHETIC DEMONSTRATION — NOT HISTORICAL PERFORMANCE.\n"
            if synthetic
            else "IMPORTED CSV DATA — see source metadata and hashes.\n"
        )
        + "\n[Desk report](desk_report.md) · [Statistics and provenance](summary.json)\n"
        + "\n![Volatility target](vol_target.png)\n![Momentum](momentum.png)\n",
        encoding="utf-8",
    )
    print(f"Saved {'SYNTHETIC demo' if synthetic else 'CSV analysis'}: {out.resolve()}")


if __name__ == "__main__":
    main()
