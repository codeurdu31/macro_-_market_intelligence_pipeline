from __future__ import annotations

import json
from pathlib import Path

from src.copilot.devils_advocate import generate_devils_advocate_report
from src.portfolio.models import PortfolioInput
from src.portfolio.exposures import net_exposure_by_ccy
from src.scenarios.stress import stress_pnl_usd


def load_portfolio(path: str) -> PortfolioInput:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return PortfolioInput.model_validate(data)


def main() -> None:
    portfolio = load_portfolio("data/portfolio_demo.json")

    exposures = net_exposure_by_ccy(portfolio.positions)
    top_positions = sorted(
        (
            {
                "pair": p.pair,
                "direction": p.direction,
                "notional_usd": float(p.notional_usd),
            }
            for p in portfolio.positions
        ),
        key=lambda x: abs(x["notional_usd"]),
        reverse=True,
    )[:5]

    scenarios = [
        {"name": "FX -2%", "pnl_usd": float(stress_pnl_usd(portfolio.positions, shock=-0.02, cost_bps=2.0))},
        {"name": "FX +2%", "pnl_usd": float(stress_pnl_usd(portfolio.positions, shock=+0.02, cost_bps=2.0))},
    ]

    # Edit this thesis with your current macro view
    macro_thesis = "USD strength continues on higher-for-longer rates; growth slows but avoids recession."

    report = generate_devils_advocate_report(
        exposures=exposures,
        top_positions=top_positions,
        scenarios=scenarios,
        macro_thesis=macro_thesis,
    )

    Path("reports").mkdir(exist_ok=True)
    out_path = "reports/devils_advocate_demo.json"
    Path(out_path).write_text(
        json.dumps(report.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("✅ Devil's advocate report saved ->", out_path)
    print(json.dumps(report.model_dump(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
