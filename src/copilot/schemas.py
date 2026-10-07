from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class ImpactItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset: str = Field(..., description="Asset impacted, e.g. EURUSD, DXY, US10Y")
    direction: Literal["up", "down", "mixed"] = Field(..., description="Expected move direction")
    confidence: float = Field(..., ge=0.0, le=1.0)


class MacroMetrics(BaseModel):
    """
    Numeric signals that can be inferred from a macro news item or announcement.
    Use small bounded scales to discourage hallucinations.
    """

    model_config = ConfigDict(extra="forbid")

    # -1 negative, +1 positive, None unknown
    inflation_impulse: float | None = Field(
        default=None, ge=-1.0, le=1.0, description="Inflation pressure sign (neg/pos)"
    )
    growth_impulse: float | None = Field(
        default=None, ge=-1.0, le=1.0, description="Growth impulse sign (neg/pos)"
    )
    labor_market_tightness: float | None = Field(
        default=None, ge=-1.0, le=1.0, description="Labor market loosening/tightening"
    )
    financial_conditions: float | None = Field(
        default=None, ge=-1.0, le=1.0, description="Easing/tightening in financial conditions"
    )
    risk_sentiment: float | None = Field(
        default=None, ge=-1.0, le=1.0, description="Risk-off (-1) to risk-on (+1)"
    )
    policy_rate_change_bps: float | None = Field(
        default=None, ge=-300.0, le=300.0, description="Announced or signaled policy rate change"
    )
    balance_sheet_tone: float | None = Field(
        default=None, ge=-1.0, le=1.0, description="QT (-1) vs QE (+1) tone"
    )
    fiscal_impulse: float | None = Field(
        default=None, ge=-1.0, le=1.0, description="Fiscal tightening (-1) vs stimulus (+1)"
    )
    trade_balance_bias: float | None = Field(
        default=None, ge=-1.0, le=1.0, description="Imports up/exports down (-1) vs exports up (+1)"
    )


class MacroSignal(BaseModel):
    """
    Output ultra-structuré = garde-fou anti-hallucination.
    """

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(..., description="Unique id for the input text/news item")
    event_type: Literal["data_release", "central_bank", "news", "policy"] = Field(...)
    country: str = Field(..., description="Country or zone, e.g. US, EZ, UK, JP")
    currencies: list[str] = Field(default_factory=list, description="Currency codes, e.g. USD, EUR")
    hawkishness: float = Field(..., ge=-1.0, le=1.0, description="-1 dovish / +1 hawkish")
    surprise: float = Field(..., ge=-1.0, le=1.0, description="-1 negative surprise / +1 positive")
    impacts: list[ImpactItem] = Field(default_factory=list)
    metrics: MacroMetrics = Field(default_factory=MacroMetrics)
    rationale: str = Field(..., min_length=5, max_length=400)
    evidence_quotes: list[str] = Field(
        default_factory=list,
        description="Short quotes copied from the input text only",
        max_length=5,
    )


class DevilsAdvocateReport(BaseModel):
    """
    Devil's advocate report: 3 counter-arguments, 3 ignored risks, actionable checklist.
    """

    model_config = ConfigDict(extra="forbid")

    counter_arguments: list[str] = Field(
        ...,
        min_length=3,
        max_length=3,
        description="Exactly 3 counter-arguments to the current thesis",
    )
    ignored_risks: list[str] = Field(
        ...,
        min_length=3,
        max_length=3,
        description="Exactly 3 risks that are being ignored",
    )
    action_checklist: list[str] = Field(
        ...,
        min_length=3,
        max_length=7,
        description="Actionable checklist items",
    )
