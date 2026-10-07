from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.data_sources.rss_collector import fetch_rss_sources
from src.data_sources.calendar_manual import load_manual_calendar, filter_window
from src.scenarios.surprise import surprise_score

from src.copilot.llm_client import extract_macro_signal
from src.core.audit import append_jsonl

from src.portfolio.models import PortfolioInput
from src.portfolio.exposures import gross_exposure_usd, net_exposure_by_ccy, leverage
from src.portfolio.limits import check_limits
from src.scenarios.stress import stress_pnl_usd
from src.copilot.linker import macro_fx_alerts

from src.reporting.plots import plot_net_exposure, plot_stress_pnl


def load_portfolio(path: str) -> PortfolioInput:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return PortfolioInput.model_validate(data)


def main() -> None:
    today = str(datetime.now().date())

    # 1) Calendar
    cal = load_manual_calendar("data/calendar_manual.json")
    now = datetime.now(timezone.utc)
    next24 = filter_window(cal, now, now + timedelta(hours=24))

    # 2) RSS macro sources
    docs = fetch_rss_sources(max_items_per_feed=2)

    # 3) IA -> signals (limité)
    signals = []
    for d in docs[:4]:
        s = extract_macro_signal(text=d.text, source_id=d.source_id)
        signals.append(s)
        append_jsonl("logs/macro_signals.jsonl", {"source_id": d.source_id, "signal": s.model_dump()})

    # 4) Risk computations (local)
    portfolio = load_portfolio("data/portfolio_demo.json")

    gross = gross_exposure_usd(portfolio.positions)
    net_ccy = net_exposure_by_ccy(portfolio.positions)
    lev = leverage(gross, portfolio.equity_usd)
    dd = 0.00

    breaches = check_limits(lev, dd, portfolio.max_leverage, portfolio.max_drawdown)

    pnl_down = stress_pnl_usd(portfolio.positions, shock=-0.02, cost_bps=2.0)
    pnl_up = stress_pnl_usd(portfolio.positions, shock=+0.02, cost_bps=2.0)

    alerts = macro_fx_alerts(signals, net_ccy, threshold_usd=20000.0)

    # 5) Save plots
    Path("reports/daily").mkdir(parents=True, exist_ok=True)
    plot_net_exposure(net_ccy, f"reports/daily/{today}_net_exposure.png")
    plot_stress_pnl(pnl_down, pnl_up, f"reports/daily/{today}_stress_pnl.png")

    # 6) Build Markdown report
    md = []
    md.append(f"# Daily Macro + Risk Report ({today})\n")

    md.append("## Next 24h Macro Calendar\n")
    if not next24:
        md.append("- No high-impact events in the next 24h (based on demo file)\n")
    else:
        for e in next24:
            s = surprise_score(e.actual, e.forecast)
            s_txt = f"{s:+.2%}" if s is not None else "N/A"
            md.append(f"- [{e.ccy}] {e.name} | importance={e.importance} | surprise={s_txt} | {e.datetime_utc}")

    md.append("\n## Portfolio Snapshot\n")
    md.append(f"- Equity: **{portfolio.equity_usd:,.0f} USD**")
    md.append(f"- Gross exposure: **{gross:,.0f} USD**")
    md.append(f"- Leverage: **{lev:.2f}x**")

    md.append("\n## Stress (FX ±2%)\n")
    md.append(f"- FX -2% PnL: **{pnl_down:,.0f} USD**")
    md.append(f"- FX +2% PnL: **{pnl_up:,.0f} USD**")

    md.append("\n## Alerts\n")
    if breaches:
        for b in breaches:
            md.append(f"- 🚨 {b}")
    else:
        md.append("- ✅ No limit breach")

    if alerts:
        md.append("\n## Macro Alerts (Exposure overlap)\n")
        for a in alerts[:8]:
            md.append(f"- ⚠️ {a}")
    else:
        md.append("\n## Macro Alerts\n- ✅ No overlap alerts")

    md.append("\n## Plots\n")
    md.append(f"- Net exposure plot: `{today}_net_exposure.png`")
    md.append(f"- Stress PnL plot: `{today}_stress_pnl.png`")

    md_path = f"reports/daily/{today}_daily_report.md"
    Path(md_path).write_text("\n".join(md), encoding="utf-8")

    print("✅ Done")
    print("Saved:", md_path)


if __name__ == "__main__":
    main()
