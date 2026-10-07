from __future__ import annotations

import json
from pathlib import Path

from src.portfolio.models import PortfolioInput
from src.portfolio.exposures import gross_exposure_usd, net_exposure_by_ccy, leverage
from src.portfolio.limits import check_limits
from src.scenarios.stress import stress_pnl_usd
from src.copilot.schemas import MacroSignal
from src.copilot.linker import macro_fx_alerts


def load_portfolio(path: str) -> PortfolioInput:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return PortfolioInput.model_validate(data)


def load_latest_signals(path: str, max_n: int = 5) -> list[MacroSignal]:
    p = Path(path)
    if not p.exists():
        return []

    lines = p.read_text(encoding="utf-8").strip().splitlines()
    lines = lines[-max_n:] if lines else []

    out: list[MacroSignal] = []
    for line in lines:
        obj = json.loads(line)
        out.append(MacroSignal.model_validate(obj["signal"]))
    return out


def main() -> None:
    portfolio = load_portfolio("data/portfolio_demo.json")
    signals = load_latest_signals("logs/macro_signals.jsonl", max_n=1)

    gross = gross_exposure_usd(portfolio.positions)
    net_ccy = net_exposure_by_ccy(portfolio.positions)
    lev = leverage(gross, portfolio.equity_usd)

    # drawdown fake for now (on branchera ton equity curve après)
    dd = 0.00

    breaches = check_limits(
        lev=lev,
        dd=dd,
        max_leverage=portfolio.max_leverage,
        max_drawdown=portfolio.max_drawdown,
    )

    pnl_down = stress_pnl_usd(portfolio.positions, shock=-0.02, cost_bps=2.0)
    pnl_up = stress_pnl_usd(portfolio.positions, shock=+0.02, cost_bps=2.0)

    alerts = macro_fx_alerts(signals, net_ccy, threshold_usd=20000.0)

    report = {
        "portfolio_id": portfolio.portfolio_id,
        "equity_usd": portfolio.equity_usd,
        "gross_exposure_usd": gross,
        "net_exposure_by_ccy_usd": net_ccy,
        "leverage": lev,
        "drawdown": dd,
        "breaches": breaches,
        "stress": {
            "FX_-2%_pnl_usd": pnl_down,
            "FX_+2%_pnl_usd": pnl_up,
        },
        "macro_alerts": alerts,
        "n_macro_signals_used": len(signals),
    }

    Path("reports").mkdir(exist_ok=True)
    Path("reports/risk_report_demo.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("✅ Risk report saved -> reports/risk_report_demo.json")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
