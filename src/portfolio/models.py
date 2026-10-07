from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class FxPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pair: str = Field(..., description="e.g. EURUSD, USDJPY")
    direction: Literal["long", "short"]
    notional_usd: float = Field(..., gt=0)


class PortfolioInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    portfolio_id: str
    equity_usd: float = Field(..., gt=0)

    max_leverage: float = Field(..., gt=0)
    max_drawdown: float = Field(..., ge=0, le=1)

    positions: list[FxPosition]
