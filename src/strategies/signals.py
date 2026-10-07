"""Signals use closing observations through t; execution lag belongs to the engine."""

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.data_sources.market_data import validate_panel


class StrategyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    name: Literal["momentum", "vol_target"]
    universe: list[str] = Field(min_length=1)
    lookback: int = Field(default=60, ge=2)
    top_n: int = Field(default=1, ge=1)
    target_vol: float = Field(default=0.10, gt=0, le=1)
    vol_floor: float = Field(default=0.01, gt=0)
    leverage_cap: float = Field(default=1.5, gt=0, le=5)

    @model_validator(mode="after")
    def validate_universe(self) -> "StrategyConfig":
        if len(set(self.universe)) != len(self.universe) or self.top_n > len(self.universe):
            raise ValueError("Unique universe and top_n <= universe size required")
        return self


@dataclass(frozen=True)
class StrategySignals:
    values: pd.DataFrame
    targets: pd.DataFrame


def generate_signals(prices: pd.DataFrame, config: StrategyConfig) -> StrategySignals:
    prices = validate_panel(prices)[config.universe]
    targets = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    if config.name == "momentum":
        values = prices / prices.shift(config.lookback) - 1.0
        # Long-only cross-sectional momentum with an absolute momentum cash filter.
        ranks = values.rank(axis=1, ascending=False, method="first")
        chosen = (values > 0) & (ranks <= config.top_n)
        counts = chosen.sum(axis=1).replace(0, np.nan)
        targets = chosen.div(counts, axis=0).fillna(0.0)
        targets *= min(1.0, config.leverage_cap)
    else:
        # Volatility of a hypothetical daily equal-weight basket, including correlations.
        basket = prices.pct_change(fill_method=None).mean(axis=1, skipna=False)
        realised = basket.rolling(config.lookback).std(ddof=1) * np.sqrt(252)
        exposure = (
            (config.target_vol / realised.clip(lower=config.vol_floor))
            .clip(upper=config.leverage_cap)
            .fillna(0.0)
        )
        targets = targets.add(exposure / len(prices.columns), axis=0)
        values = realised.to_frame("realised_vol")
    return StrategySignals(values=values, targets=targets)
