"""Manual RSS → validated extraction → observable context → FX risk pipeline."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict, Field

from src.analytics.fx_desk import market_context, portfolio_risk, reaction
from src.copilot.desk import compare_rate, extract_desk_signal
from src.data_sources.desk_sources import (
    PublicSources,
    FX_URL,
    collect_documents,
    collect_expectations,
    load_expectations,
    parse_fx,
)
from src.portfolio.models import PortfolioInput
from src.reporting.fx_desk import render_report


class DeskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    articles_per_feed: int = Field(default=2, ge=1, le=5)
    max_age_days: int = Field(default=30, ge=1, le=90)
    max_llm_calls: int = Field(default=3, ge=0, le=10)
    alert_max_age_days: int = Field(default=7, ge=1, le=30)
    exposure_threshold_usd: float = Field(default=20000, ge=0)
    upcoming_hours: int = Field(default=168, ge=1, le=168)


def run_pipeline(
    root: Path,
    output: Path,
    config: DeskConfig,
    *,
    no_llm: bool = False,
    client: httpx.Client | None = None,
) -> dict:
    started = datetime.now(timezone.utc)
    portfolio = PortfolioInput.model_validate_json(
        (root / "data/portfolio_demo.json").read_text(encoding="utf-8")
    )
    pairs = sorted({p.pair for p in portfolio.positions})
    for pair in pairs:
        if len(pair) != 6 or not pair.isalpha() or pair != pair.upper():
            raise ValueError(f"invalid FX pair: {pair}")
    output.mkdir(parents=True, exist_ok=True)
    cache = root / "data/cache/fx_desk"
    archive = cache / "expectations.jsonl"
    owns_client = client is None
    client = client or httpx.Client(
        timeout=15,
        follow_redirects=True,
        headers={"User-Agent": "fx-risk-copilot/0.3 (personal research)"},
    )
    try:
        sources = PublicSources(client, cache / "http")
        docs, issues = collect_documents(
            sources, started, config.articles_per_feed, config.max_age_days
        )
        try:
            expectations = collect_expectations(sources, archive)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            expectations = load_expectations(archive)
            issues.append(f"Calendar unavailable ({type(exc).__name__}); using dated archive only.")
        market = None
        try:
            xml, collected = sources.get(FX_URL, 4)
            market = parse_fx(xml, pairs, started)
            market.to_csv(output / "fx_reference.csv")
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            issues.append(f"ECB FX unavailable: {type(exc).__name__}")
    finally:
        if owns_client:
            client.close()
    risk = portfolio_risk(portfolio)
    publications = []
    calls = 0
    ccy_by_provider = {"FED": "USD", "ECB": "EUR", "BOE": "GBP"}
    # Round-robin providers: no single feed can consume the entire LLM budget.
    docs = [
        group[index]
        for index in range(config.articles_per_feed)
        for provider in ("FED", "ECB", "BOE")
        if len(group := [d for d in docs if d.provider == provider]) > index
    ]
    for doc in docs:
        item = {
            **doc.model_dump(exclude={"text"}),
            "status": "not_extracted",
            "signal": None,
            "comparisons": [],
            "alerts": [],
            "reactions": {},
        }
        signal = None
        if not no_llm:
            try:
                signal, called = extract_desk_signal(
                    doc, cache / "signals", calls < config.max_llm_calls
                )
                calls += int(called)
                item["status"] = (
                    "extracted" if called else "cached" if signal else "budget_exhausted"
                )
            except Exception as exc:
                # Conservatively charge one budget slot even if failure preceded HTTP.
                calls += int(calls < config.max_llm_calls)
                item["status"] = "extraction_unavailable"
                issues.append(
                    f"{doc.source_id} extraction: {type(exc).__name__}. Check local LLM configuration/API access; no signal substituted."
                )
        else:
            item["status"] = "llm_disabled"
        published = datetime.fromisoformat(doc.published_at)
        currency = ccy_by_provider[doc.provider]
        if signal:
            item["signal"] = signal.model_dump(mode="json")
            item["comparisons"] = [
                compare_rate(rate, published, expectations) for rate in signal.announced_rates
            ]
            exposure = risk["net_usd_equivalent"].get(currency, 0)
            if signal.relevant_to_fx and abs(exposure) >= config.exposure_threshold_usd:
                if started - published <= timedelta(days=config.alert_max_age_days):
                    item["alerts"].append(
                        f"À examiner : communiqué {doc.provider}, exposition nette {currency} {exposure:+,.0f} USD équivalent. Vérifier les citations et les stress avant tout ajustement."
                    )
                    stress = [s for s in risk["scenarios"] if s["currency"] == currency]
                    worst = min(stress, key=lambda s: s["pnl_usd_approx"])
                    item["alerts"].append(
                        f"Sensibilité : choc {currency} {worst['shock']:+.0%}, P&L indicatif {worst['pnl_usd_approx']:+,.0f} USD ({worst['equity_fraction']:+.1%} de l'equity), scénario hypothétique."
                    )
                else:
                    item["alerts"].append(
                        "Publication ancienne : contexte historique, pas de nouvelle alerte portefeuille."
                    )
            if signal.relevant_to_fx and market is not None:
                item["reactions"] = {
                    pair: reaction(market, pair, published)
                    for pair in pairs
                    if currency in (pair[:3], pair[3:])
                }
        publications.append(item)
    now = datetime.now(timezone.utc)
    latest = {}
    for e in sorted(expectations, key=lambda x: x.observed_at):
        if e.observed_at <= now:
            latest[e.event_id] = e
    upcoming = [
        e.model_dump(mode="json")
        for e in sorted(latest.values(), key=lambda x: x.event_at)
        if now < e.event_at <= now + timedelta(hours=config.upcoming_hours)
        and e.currency in risk["net_usd_equivalent"]
        and e.impact in {"High", "Medium"}
    ]
    if not docs:
        issues.append("No usable official publication: macro coverage unavailable.")
    if no_llm:
        issues.append(
            "LLM disabled: documents collected, no interpreted macro signals or macro alerts."
        )
    report = {
        "as_of": now.isoformat(),
        "data_mode": "public_sources",
        "portfolio_mode": "fictitious",
        "config": config.model_dump(),
        "llm_budget_slots_used": calls,
        "risk": risk,
        "market_source": FX_URL,
        "market": {
            pair: market_context(market, pair, now)
            if market is not None
            else {"status": "unavailable"}
            for pair in pairs
        },
        "publications": publications,
        "upcoming": upcoming,
        "issues": issues,
    }
    for filename, payload in [
        ("summary.json", report),
        ("source_docs.json", [d.model_dump() for d in docs]),
        ("expectations.json", [e.model_dump(mode="json") for e in expectations]),
    ]:
        (output / filename).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8"
        )
    (output / "desk_report.md").write_text(render_report(report), encoding="utf-8")
    return report
