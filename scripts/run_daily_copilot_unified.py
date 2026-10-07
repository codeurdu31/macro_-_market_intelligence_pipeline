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

from src.reporting.plots import plot_net_exposure, plot_stress_pnl


def load_portfolio(path: str) -> PortfolioInput:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return PortfolioInput.model_validate(data)


def _macro_factor(hawkishness: float, surprise: float) -> float:
    # bounded 0..1
    return min(1.0, 0.5 * abs(hawkishness) + 0.5 * abs(surprise))


def main() -> None:
    today = str(datetime.now().date())
    # 1) Portfolio risk (baseline)
    portfolio = load_portfolio("data/portfolio_demo.json")
    gross = gross_exposure_usd(portfolio.positions)
    net_ccy = net_exposure_by_ccy(portfolio.positions)
    lev = leverage(gross, portfolio.equity_usd)
    dd = 0.00

    breaches = check_limits(lev, dd, portfolio.max_leverage, portfolio.max_drawdown)
    pnl_down = stress_pnl_usd(portfolio.positions, shock=-0.02, cost_bps=2.0)
    pnl_up = stress_pnl_usd(portfolio.positions, shock=+0.02, cost_bps=2.0)

    # 2) RSS macro sources + IA signals (limited)
    docs = fetch_rss_sources(max_items_per_feed=2)
    docs = docs[:6]
    doc_map = {d.source_id: d for d in docs}

    signals = []
    for d in docs[:4]:
        s = extract_macro_signal(text=d.text, source_id=d.source_id)
        signals.append(s)
        append_jsonl(
            "logs/macro_signals.jsonl",
            {"source_id": d.source_id, "provider": d.provider, "signal": s.model_dump()},
        )

    # 3) Link RSS signals -> exposures (what moved risk)
    macro_impacts = []
    ccy_factor = {}
    threshold_usd = 20000.0

    for s in signals:
        factor = _macro_factor(s.hawkishness, s.surprise)
        for ccy in s.currencies:
            expo = float(net_ccy.get(ccy.upper(), 0.0))
            if abs(expo) < threshold_usd:
                continue

            doc = doc_map.get(s.source_id)
            side = "LONG" if expo > 0 else "SHORT"

            macro_impacts.append(
                {
                    "source_id": s.source_id,
                    "provider": getattr(doc, "provider", "UNK"),
                    "title": getattr(doc, "title", ""),
                    "published_at": getattr(doc, "published_at", ""),
                    "url": getattr(doc, "url", ""),
                    "ccy": ccy.upper(),
                    "exposure_usd": expo,
                    "side": side,
                    "event_type": s.event_type,
                    "country": s.country,
                    "hawkishness": s.hawkishness,
                    "surprise": s.surprise,
                    "rationale": s.rationale,
                    "evidence_quotes": s.evidence_quotes,
                }
            )

            ccy_factor[ccy.upper()] = max(ccy_factor.get(ccy.upper(), 0.0), factor)

    # 4) Before/after risk scoring (macro overlay)
    before_scores = {ccy: abs(float(expo)) for ccy, expo in net_ccy.items()}
    after_scores = {
        ccy: abs(float(expo)) * (1.0 + ccy_factor.get(ccy, 0.0))
        for ccy, expo in net_ccy.items()
    }

    risk_before_total = round(sum(before_scores.values()), 2)
    risk_after_total = round(sum(after_scores.values()), 2)

    # 5) Plots
    Path("reports/daily").mkdir(parents=True, exist_ok=True)
    plot_net_exposure(net_ccy, f"reports/daily/{today}_net_exposure.png")
    plot_stress_pnl(pnl_down, pnl_up, f"reports/daily/{today}_stress_pnl.png")

    # 6) Markdown report
    md = []
    md.append(f"# Daily Macro + Risk Report (Unified) - {today}\n")

    md.append("## RSS Signals That Moved Portfolio Risk\n")
    if not macro_impacts:
        md.append("- None (no RSS signal crossed exposure threshold)\n")
    else:
        for i, m in enumerate(macro_impacts, start=1):
            md.append(f"Signal {i}: {m['provider']} | {m['title']} | {m['published_at']}")
            md.append(f"Source ID: {m['source_id']}")
            md.append(f"Exposure touched: {m['ccy']} {m['side']} {m['exposure_usd']:,.0f} USD")
            md.append(
                f"IA analysis: event_type={m['event_type']} country={m['country']} "
                f"hawkishness={m['hawkishness']:+.2f} surprise={m['surprise']:+.2f}"
            )
            md.append(f"Rationale: {m['rationale']}")
            if m["evidence_quotes"]:
                md.append("Evidence quotes: " + " | ".join(m["evidence_quotes"]))
            md.append("")

    md.append("## Portfolio Analysis (Before / After Macro Overlay)\n")
    md.append(f"- Equity: **{portfolio.equity_usd:,.0f} USD**")
    md.append(f"- Gross exposure: **{gross:,.0f} USD**")
    md.append(f"- Leverage: **{lev:.2f}x**")
    md.append(f"- Stress FX -2%: **{pnl_down:,.0f} USD**")
    md.append(f"- Stress FX +2%: **{pnl_up:,.0f} USD**")
    md.append(f"- Risk score BEFORE: **{risk_before_total:,.0f}**")
    md.append(f"- Risk score AFTER: **{risk_after_total:,.0f}**")

    md.append("\n## Before/After by Currency\n")
    md.append("| CCY | Net Exposure (USD) | Risk Score Before | Risk Score After |")
    md.append("| --- | ---: | ---: | ---: |")
    for ccy in sorted(net_ccy.keys()):
        md.append(
            f"| {ccy} | {net_ccy[ccy]:,.0f} | "
            f"{before_scores[ccy]:,.0f} | {after_scores[ccy]:,.0f} |"
        )

    md.append("\n## Limit Checks\n")
    if breaches:
        for b in breaches:
            md.append(f"- {b}")
    else:
        md.append("- No limit breach")

    md.append("\n## Plots\n")
    md.append(f"- `reports/daily/{today}_net_exposure.png`")
    md.append(f"- `reports/daily/{today}_stress_pnl.png`")

    out_md = f"reports/daily/{today}_daily_report_unified.md"
    Path(out_md).write_text("\n".join(md), encoding="utf-8")

    # 7) JSON report for programmatic use
    out_json = f"reports/daily/{today}_daily_report_unified.json"
    payload = {
        "date": today,
        "portfolio_id": portfolio.portfolio_id,
        "macro_impacts": macro_impacts,
        "portfolio": {
            "equity_usd": portfolio.equity_usd,
            "gross_exposure_usd": gross,
            "net_exposure_by_ccy_usd": net_ccy,
            "leverage": lev,
            "drawdown": dd,
            "stress": {"FX_-2%": pnl_down, "FX_+2%": pnl_up},
            "limit_breaches": breaches,
        },
        "risk_score_before": risk_before_total,
        "risk_score_after": risk_after_total,
        "risk_scores_by_ccy": {
            ccy: {"before": before_scores[ccy], "after": after_scores[ccy]}
            for ccy in net_ccy.keys()
        },
    }
    Path(out_json).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print("Saved:", out_md)
    print("Saved:", out_json)


if __name__ == "__main__":
    main()
