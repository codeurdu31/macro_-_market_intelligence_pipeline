"""Offline fixtures are test data only; production never falls back to them."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import httpx
import pytest

from src.analytics.fx_desk import market_context, portfolio_risk, reaction
from src.copilot.desk import AnnouncedRate, DeskSignal, compare_rate, validate_evidence
from src.copilot.fx_pipeline import DeskConfig, run_pipeline
from src.data_sources.desk_sources import Expectation, PublicSources, collect_expectations, parse_fx
from src.data_sources.models import SourceDoc
from src.portfolio.models import PortfolioInput


def expectation(observed, forecast="4.25%"):
    return Expectation(
        event_id="rate",
        title="Federal Funds Rate",
        currency="USD",
        event_at="2026-09-16T18:00Z",
        observed_at=observed,
        impact="High",
        forecast=forecast,
        previous="4.00%",
        source="https://example.test/calendar",
        indicator="fed_funds_upper",
        value=float(forecast[:-1]),
        unit="percent",
    )


def test_surprise_requires_ex_ante_forecast_and_exact_definition():
    published = datetime(2026, 9, 16, 18, tzinfo=timezone.utc)
    rate = AnnouncedRate(
        indicator="fed_funds_upper", value=4.5, evidence="target range of 4.25 to 4.5 percent"
    )
    early = expectation("2026-09-16T17:00Z")
    late = expectation("2026-09-16T19:00Z", "4.50%")
    result = compare_rate(rate, published, [early, late])
    assert result["surprise_bps"] == 25
    assert compare_rate(rate, published, [late])["surprise_bps"] is None
    assert (
        compare_rate(rate.model_copy(update={"indicator": "ecb_deposit"}), published, [early])[
            "expected_percent"
        ]
        is None
    )
    zero = expectation("2026-09-16T17:00Z", "0.00%")
    assert compare_rate(rate, published, [zero])["expected_percent"] == 0


def test_evidence_rejects_invented_quote():
    doc = SourceDoc(
        source_id="test",
        source_type="central_bank",
        provider="FED",
        title="test",
        published_at="2026-09-16T18:00Z",
        url="https://example.test",
        text="The Committee increased the rate.",
    )
    signal = DeskSignal(
        relevant_to_fx=True,
        hawkishness=0.5,
        rationale="Rate increased.",
        evidence_quotes=["The Committee increased the rate."],
        announced_rates=[],
    )
    validate_evidence(signal, doc)
    with pytest.raises(ValueError, match="verbatim"):
        validate_evidence(
            signal.model_copy(update={"evidence_quotes": ["Invented quotation."]}), doc
        )
    fragment = signal.model_copy(update={"evidence_quotes": ["The Committee increased."]})
    validate_evidence(fragment, doc)
    assert fragment.evidence_quotes == ["The Committee increased"]


def test_fx_crosses_availability_and_release_day_exclusion():
    xml = '<root><Cube time="2026-09-15"><Cube currency="USD" rate="1.1"/><Cube currency="JPY" rate="165"/></Cube><Cube time="2026-09-16"><Cube currency="USD" rate="1.2"/><Cube currency="JPY" rate="168"/></Cube><Cube time="2026-09-17"><Cube currency="USD" rate="1.3"/><Cube currency="JPY" rate="169"/></Cube></root>'
    now = datetime(2026, 9, 18, tzinfo=timezone.utc)
    market = parse_fx(xml, ["EURUSD", "USDJPY"], now)
    assert market.USDJPY.iloc[0] == 150
    event = datetime(2026, 9, 16, 18, tzinfo=timezone.utc)
    assert market_context(market, "EURUSD", event)["level"] == 1.1
    assert reaction(market, "EURUSD", event)["post_1_reference_return"] == pytest.approx(
        1.3 / 1.1 - 1
    )
    assert len(parse_fx(xml, ["EURUSD"], event)) == 1
    with pytest.raises(ValueError):
        parse_fx("<html>", ["EURUSD"], now)


def test_calendar_archives_revision_without_backdating(tmp_path):
    class Source:
        forecast = "4.25%"
        observed = datetime(2026, 9, 16, 16, tzinfo=timezone.utc)

        def get(self, url):
            return json.dumps(
                [
                    {
                        "title": "Federal Funds Rate",
                        "country": "USD",
                        "date": "2026-09-16T18:00:00Z",
                        "forecast": self.forecast,
                        "previous": "4.00%",
                        "impact": "High",
                    }
                ]
            ), self.observed

    source = Source()
    archive = tmp_path / "expectations.jsonl"
    assert len(collect_expectations(source, archive)) == 1
    assert len(collect_expectations(source, archive)) == 1
    source.observed += timedelta(hours=1)
    source.forecast = "4.50%"
    assert len(collect_expectations(source, archive)) == 2
    source.observed += timedelta(hours=2)
    source.forecast = "4.25%"
    rows = collect_expectations(source, archive)
    assert len(rows) == 3
    assert rows[-1].observed_at.hour == 19


def test_public_http_cache_avoids_repeat_requests(tmp_path):
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(200, text="body")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        source = PublicSources(client, tmp_path)
        assert source.get("https://example.test") == source.get("https://example.test")
    assert len(calls) == 1


def test_real_pipeline_contract_with_mock_http(tmp_path, monkeypatch):
    import src.copilot.fx_pipeline as pipeline

    root = Path(__file__).resolve().parents[1]
    (tmp_path / "data").mkdir()
    (tmp_path / "data/portfolio_demo.json").write_bytes(
        (root / "data/portfolio_demo.json").read_bytes()
    )
    now = datetime.now(timezone.utc)
    release = (now - timedelta(days=1)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    text = "The Committee decided to maintain the target range. " * 8

    def handler(request):
        url = str(request.url)
        if "faireconomy" in url:
            return httpx.Response(200, json=[])
        if "eurofxref" in url:
            days = "".join(
                f'<Cube time="{(now - timedelta(days=i)).date()}"><Cube currency="USD" rate="1.1"/><Cube currency="JPY" rate="165"/><Cube currency="GBP" rate="0.85"/></Cube>'
                for i in range(1, 25)
            )
            return httpx.Response(200, text=f"<root>{days}</root>")
        if "bankofengland" in url:
            return httpx.Response(403)
        if url.endswith("article"):
            return httpx.Response(200, text=f"<main><p>{text}</p></main>")
        host = request.url.host
        return httpx.Response(
            200,
            text=f"<rss><channel><item><title>Monetary policy</title><link>https://{host}/article</link><pubDate>{release}</pubDate></item></channel></rss>",
        )

    called = []

    def extract(doc, cache, allow_call):
        if not allow_call:
            return None, False
        called.append(doc.source_id)
        return DeskSignal(
            relevant_to_fx=True,
            hawkishness=None,
            rationale="Rate maintained; assess portfolio risk.",
            evidence_quotes=[text.strip()],
            announced_rates=[],
        ), True

    monkeypatch.setattr(pipeline, "extract_desk_signal", extract)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        report = run_pipeline(
            tmp_path, tmp_path / "out", DeskConfig(max_llm_calls=1), client=client
        )
    assert len(called) == 1
    assert len(report["publications"]) == 2
    assert report["publications"][0]["alerts"]
    assert report["market"]["USDJPY"]["level"] == 150
    assert any("BOE RSS" in issue for issue in report["issues"])
    assert report["risk"]["drawdown"] is None
    assert (tmp_path / "out/desk_report.md").exists()


def test_usd_strengthening_hurts_short_usd_demo_book():
    root = Path(__file__).resolve().parents[1]
    portfolio = PortfolioInput.model_validate_json((root / "data/portfolio_demo.json").read_text())
    risk = portfolio_risk(portfolio)
    scenario = next(s for s in risk["scenarios"] if s["currency"] == "USD" and s["shock"] > 0)
    assert scenario["pnl_usd_approx"] < 0
    assert risk["net_usd_equivalent"]["USD"] == -110000
