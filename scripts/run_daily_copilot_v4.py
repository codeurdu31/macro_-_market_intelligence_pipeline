from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.data_sources.calendar_manual import load_manual_calendar, filter_window
from src.data_sources.event_window import event_stage

from src.data_sources.rss_collector import fetch_rss_sources
from src.copilot.llm_client import extract_macro_signal
from src.core.audit import append_jsonl

from src.portfolio.models import PortfolioInput
from src.portfolio.exposures import gross_exposure_usd, net_exposure_by_ccy, leverage
from src.portfolio.limits import check_limits
from src.scenarios.stress import stress_pnl_usd
from src.copilot.linker import macro_fx_alerts

from src.reporting.plots import plot_net_exposure, plot_stress_pnl
from src.copilot.risk_ranker import top_calendar_risks


def load_portfolio(path: str) -> PortfolioInput:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return PortfolioInput.model_validate(data)


def main() -> None:
    today = str(datetime.now().date())

    # 1) Load portfolio + compute risk (local)
    portfolio = load_portfolio("data/portfolio_demo.json")
    gross = gross_exposure_usd(portfolio.positions)
    net_ccy = net_exposure_by_ccy(portfolio.positions)
    lev = leverage(gross, portfolio.equity_usd)
    dd = 0.00

    breaches = check_limits(lev, dd, portfolio.max_leverage, portfolio.max_drawdown)
    pnl_down = stress_pnl_usd(portfolio.positions, shock=-0.02, cost_bps=2.0)
    pnl_up = stress_pnl_usd(portfolio.positions, shock=+0.02, cost_bps=2.0)

    # 2) Manual calendar window (next 72h)
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(hours=72)
    cal_all = load_manual_calendar("data/calendar_manual.json")
    cal_next = filter_window(cal_all, now, horizon)

    # 3) RSS macro sources + IA signals (limited)
    docs = fetch_rss_sources(max_items_per_feed=2)

    signals = []
    for d in docs[:4]:
        s = extract_macro_signal(text=d.text, source_id=d.source_id)
        signals.append(s)
        append_jsonl("logs/macro_signals.jsonl", {"source_id": d.source_id, "signal": s.model_dump()})

    # 4) Alerts
    macro_alerts = macro_fx_alerts(signals, net_ccy, threshold_usd=20000.0)

    calendar_alerts = []
    for e in cal_next:
        st = event_stage(e.datetime_utc)
        expo = float(net_ccy.get(e.ccy.upper(), 0.0))
        if abs(expo) >= 20000 and st in ("PRE", "LIVE"):
            side = "LONG" if expo > 0 else "SHORT"
            calendar_alerts.append(
                f"CALENDAR_RISK: {e.ccy} {e.name} ({st}) touches exposure {side} {expo:,.0f} USD @ {e.datetime_utc}"
            )

    top_risks = top_calendar_risks(cal_next, net_ccy, top_k=5)

    # 5) Save plots
    Path("reports/daily").mkdir(parents=True, exist_ok=True)
    plot_net_exposure(net_ccy, f"reports/daily/{today}_net_exposure.png")
    plot_stress_pnl(pnl_down, pnl_up, f"reports/daily/{today}_stress_pnl.png")

    # 6) Markdown report (decision-ready)
    md = []
    md.append(f"# Daily Macro + Risk Report ({today})\n")

    md.append("## Top 5 Calendar Risks (next 72h)\n")
    if not top_risks:
        md.append("- None\n")
    else:
        for r in top_risks:
            md.append(
                f"- [{r['ccy']}] {r['name']} | imp={r['importance']} | expo={r['net_exposure_usd']:,.0f} | score={r['score']} | {r['datetime_utc']}"
            )

    md.append("\n## Calendar (next 72h)\n")
    if not cal_next:
        md.append("- No manual events in the next 72h\n")
    else:
        for e in cal_next[:15]:
            md.append(f"- [{e.ccy}] {e.name} | imp={e.importance} | stage={event_stage(e.datetime_utc)} | {e.datetime_utc}")

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

    if calendar_alerts:
        md.append("\n### Calendar Alerts\n")
        for a in calendar_alerts:
            md.append(f"- ⚠️ {a}")
    else:
        md.append("\n### Calendar Alerts\n- ✅ None")

    if macro_alerts:
        md.append("\n### News/CB Alerts\n")
        for a in macro_alerts[:8]:
            md.append(f"- ⚠️ {a}")
    else:
        md.append("\n### News/CB Alerts\n- ✅ None")

    md.append("\n## Plots\n")
    md.append(f"- `reports/daily/{today}_net_exposure.png`")
    md.append(f"- `reports/daily/{today}_stress_pnl.png`")

    out_md = f"reports/daily/{today}_daily_report_v4.md"
    Path(out_md).write_text("\n".join(md), encoding="utf-8")

    print("✅ Saved:", out_md)


if __name__ == "__main__":
    main()
