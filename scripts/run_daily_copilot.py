from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.data_sources.rss_collector import fetch_rss_sources
from src.copilot.llm_client import extract_macro_signal
from src.core.audit import append_jsonl

from src.portfolio.models import PortfolioInput
from src.portfolio.exposures import gross_exposure_usd, net_exposure_by_ccy, leverage
from src.portfolio.limits import check_limits
from src.scenarios.stress import stress_pnl_usd
from src.copilot.linker import macro_fx_alerts


def load_portfolio(path: str) -> PortfolioInput:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return PortfolioInput.model_validate(data)


def main() -> None:
    today = str(datetime.now().date())

    # 1) Collect sources
    docs = fetch_rss_sources(max_items_per_feed=3)

    # 2) IA extraction -> MacroSignals
    signals = []
    for d in docs[:6]:  # limite pour éviter trop de requêtes
        s = extract_macro_signal(text=d.text, source_id=d.source_id)
        signals.append(s)

        append_jsonl(
            "logs/macro_signals.jsonl",
            {"source_id": d.source_id, "provider": d.provider, "signal": s.model_dump()},
        )

    # 3) Load portfolio + compute risk
    portfolio = load_portfolio("data/portfolio_demo.json")

    gross = gross_exposure_usd(portfolio.positions)
    net_ccy = net_exposure_by_ccy(portfolio.positions)
    lev = leverage(gross, portfolio.equity_usd)

    dd = 0.00  # on branchera une equity curve après

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
        "date": today,
        "portfolio_id": portfolio.portfolio_id,
        "equity_usd": portfolio.equity_usd,
        "gross_exposure_usd": gross,
        "net_exposure_by_ccy_usd": net_ccy,
        "leverage": lev,
        "drawdown": dd,
        "breaches": breaches,
        "stress": {"FX_-2%": pnl_down, "FX_+2%": pnl_up},
        "macro_alerts": alerts,
        "macro_sources_used": len(docs[:6]),
    }

    # 4) Save outputs
    Path("reports/daily").mkdir(parents=True, exist_ok=True)

    json_path = f"reports/daily/{today}_risk_report.json"
    Path(json_path).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    md_path = f"reports/daily/{today}_daily_report.md"
    md = []
    md.append(f"# Daily Macro + Risk Report ({today})\n")
    md.append("## Portfolio snapshot\n")
    md.append(f"- Equity: **{portfolio.equity_usd:,.0f} USD**")
    md.append(f"- Gross exposure: **{gross:,.0f} USD**")
    md.append(f"- Leverage: **{lev:.2f}x**")
    md.append("\n## Stress (FX ±2%)\n")
    md.append(f"- FX -2% PnL: **{pnl_down:,.0f} USD**")
    md.append(f"- FX +2% PnL: **{pnl_up:,.0f} USD**")
    md.append("\n## Alerts\n")
    if breaches:
        md.append("- **LIMIT BREACHES:**")
        for b in breaches:
            md.append(f"  - {b}")
    else:
        md.append("- No limit breach detected")

    if alerts:
        md.append("\n- **MACRO ALERTS:**")
        for a in alerts[:8]:
            md.append(f"  - {a}")
    else:
        md.append("\n- No macro alert (no big overlap)")

    Path(md_path).write_text("\n".join(md), encoding="utf-8")

    print("✅ Saved:")
    print(" -", json_path)
    print(" -", md_path)


if __name__ == "__main__":
    main()
