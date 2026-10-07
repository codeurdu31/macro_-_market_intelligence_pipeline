from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.data_sources.te_calendar import fetch_te_calendar_all_by_date
from src.data_sources.event_window import event_stage
from src.scenarios.surprise import surprise_score

from src.data_sources.rss_collector import fetch_rss_sources
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

    # 1) Real macro calendar via Trading Economics
    d0 = datetime.now(timezone.utc).date()
    d1 = d0 + timedelta(days=1)
    cal_events = fetch_te_calendar_all_by_date(d0, d1, importance=2)

    # keep only events inside next 24h window
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(hours=24)
    next24 = []
    for e in cal_events:
        dt = datetime.fromisoformat(e.datetime_utc.replace("Z", "+00:00"))
        if now <= dt <= horizon:
            next24.append(e)

    # 2) RSS macro sources + IA signals (limité)
    docs = fetch_rss_sources(max_items_per_feed=2)

    signals = []
    for d in docs[:4]:
        s = extract_macro_signal(text=d.text, source_id=d.source_id)
        signals.append(s)
        append_jsonl("logs/macro_signals.jsonl", {"source_id": d.source_id, "signal": s.model_dump()})

    # 3) Risk (local)
    portfolio = load_portfolio("data/portfolio_demo.json")

    gross = gross_exposure_usd(portfolio.positions)
    net_ccy = net_exposure_by_ccy(portfolio.positions)
    lev = leverage(gross, portfolio.equity_usd)
    dd = 0.00

    breaches = check_limits(lev, dd, portfolio.max_leverage, portfolio.max_drawdown)

    pnl_down = stress_pnl_usd(portfolio.positions, shock=-0.02, cost_bps=2.0)
    pnl_up = stress_pnl_usd(portfolio.positions, shock=+0.02, cost_bps=2.0)

    # 4) Alerts
    macro_alerts = macro_fx_alerts(signals, net_ccy, threshold_usd=20000.0)

    calendar_alerts = []
    for e in next24:
        stage = event_stage(e.datetime_utc)
        expo = net_ccy.get(e.ccy, 0.0)
        if abs(expo) >= 20000 and stage in ("PRE", "LIVE"):
            side = "LONG" if expo > 0 else "SHORT"
            calendar_alerts.append(
                f"CALENDAR_RISK: {e.ccy} {e.name} ({stage}) touches exposure {side} {expo:,.0f} USD"
            )

    # 5) Plots
    Path("reports/daily").mkdir(parents=True, exist_ok=True)
    plot_net_exposure(net_ccy, f"reports/daily/{today}_net_exposure.png")
    plot_stress_pnl(pnl_down, pnl_up, f"reports/daily/{today}_stress_pnl.png")

    # 6) Markdown report
    md = []
    md.append(f"# Daily Macro + Risk Report ({today})\n")

    md.append("## Next 24h Macro Calendar (Trading Economics)\n")
    if not next24:
        md.append("- No medium/high events in the next 24h\n")
    else:
        for e in next24[:12]:
            stage = event_stage(e.datetime_utc)
            s = surprise_score(e.actual, e.forecast)
            s_txt = f"{s:+.2%}" if s is not None else "N/A"
            md.append(f"- [{e.ccy}] {e.name} | imp={e.importance} | stage={stage} | surprise={s_txt} | {e.datetime_utc}")

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
        md.append("\n## Calendar Alerts (Exposure overlap)\n")
        for a in calendar_alerts:
            md.append(f"- ⚠️ {a}")
    else:
        md.append("\n## Calendar Alerts\n- ✅ No calendar overlap alert")

    if macro_alerts:
        md.append("\n## Macro Alerts (News/CB)\n")
        for a in macro_alerts[:8]:
            md.append(f"- ⚠️ {a}")
    else:
        md.append("\n## Macro Alerts (News/CB)\n- ✅ No macro alert")

    out_md = f"reports/daily/{today}_daily_report_v3.md"
    Path(out_md).write_text("\n".join(md), encoding="utf-8")

    print("✅ Saved:", out_md)


if __name__ == "__main__":
    main()
