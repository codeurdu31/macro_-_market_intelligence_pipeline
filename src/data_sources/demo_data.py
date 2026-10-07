"""Deterministic synthetic inputs, deliberately never labelled historical market data."""

from pathlib import Path

import numpy as np
import pandas as pd


def write_demo_inputs(
    directory: Path, seed: int, observations: int, as_of: pd.Timestamp
) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    index = pd.bdate_range(end=as_of.normalize(), periods=observations) + pd.Timedelta(hours=22)
    shocks = rng.normal(size=(observations, 7))
    market = pd.DataFrame(index=index)
    for j, (name, level, daily_vol) in enumerate(
        [
            ("EURUSD", 1.08, 0.005),
            ("USDJPY", 140, 0.006),
            ("SPX_USD", 4500, 0.011),
            ("SX5E_EUR", 4000, 0.012),
        ]
    ):
        regime = np.where(np.arange(observations) % 180 < 90, 0.7, 1.5)
        market[name] = level * np.exp(np.cumsum(0.00015 + daily_vol * regime * shocks[:, j]))
    market["US2Y"] = 4 + np.cumsum(shocks[:, 4] * 0.025)
    market["US10Y"] = 3.5 + np.cumsum(shocks[:, 5] * 0.02)
    market["VIX"] = 20 * np.exp(np.cumsum(shocks[:, 6] * 0.025))
    market.index.name = "timestamp"
    paths = {name: directory / f"{name}.csv" for name in ["market", "cash", "events"]}
    market.to_csv(paths["market"])
    pd.DataFrame(
        {"annual_rate": 0.025 + 0.005 * np.sin(np.arange(observations) / 100)}, index=market.index
    ).to_csv(paths["cash"])
    events = []
    names = ["US CPI", "NFP", "FOMC", "ECB rate decision"]
    for j, pos in enumerate(range(40, observations - 5, 21)):
        name = names[j % len(names)]
        events.append(
            {
                "event_id": f"SYNTHETIC_{j:03}",
                "name": name,
                "timestamp": (
                    index[pos].normalize() + pd.Timedelta(hours=13, minutes=30)
                ).isoformat(),
                "currency": "EUR" if name.startswith("ECB") else "USD",
                "actual": 3.0 + 0.1 * ((j % 3) - 1),
                "consensus": 3.0,
                "unit": "synthetic_units",
                "source": "SYNTHETIC — not actual releases",
            }
        )
    events.append(
        {
            "event_id": "SYNTHETIC_UPCOMING",
            "name": "US CPI",
            "timestamp": (as_of + pd.Timedelta(days=2)).isoformat(),
            "currency": "USD",
            "actual": None,
            "consensus": None,
            "unit": "synthetic_units",
            "source": "SYNTHETIC",
        }
    )
    pd.DataFrame(events).to_csv(paths["events"], index=False)
    return paths
