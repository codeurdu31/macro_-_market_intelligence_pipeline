"""Portable reports and matplotlib figures for the three analytics modules."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from src.strategies.backtest import BacktestResult


def plot_backtest(
    result: BacktestResult,
    rolling: pd.DataFrame,
    output: Path,
    *,
    label: str = "",
    target_vol: float | None = None,
) -> None:
    with plt.style.context("seaborn-v0_8-whitegrid"):
        fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True)
        fig.suptitle(label)
        result.history[["index", "benchmark"]].plot(
            ax=axes[0], title="Index net of costs / frictionless benchmark"
        )
        result.weights.sum(axis=1).plot(ax=axes[1], label="Risky exposure")
        result.history["cash_weight"].plot(ax=axes[1], label="Cash exposure")
        axes[1].legend()
        rolling["volatility"].mul(100).plot(ax=axes[2], label="Rolling realised vol")
        if target_vol is not None:
            axes[2].axhline(
                target_vol * 100, color="black", linestyle="--", label="Volatility target"
            )
        axes[2].set_ylabel("Annualised vol (%)")
        axes[2].legend()
        fig.tight_layout()
        fig.savefig(output, dpi=150)
        plt.close(fig)


def desk_report(reactions: pd.DataFrame, as_of: pd.Timestamp) -> str:
    lines = [
        "# Trading desk — event reactions",
        "",
        f"As of: {as_of.isoformat()}",
        "",
        "Event association does not establish causality. Daily moves run from the last pre-release",
        "close to the first/fifth post-release close; intraday requires separate timestamped quotes.",
        "",
        "| Catalyst | Asset | 1-close move | 5-close move | Macro surprise | Units | Status |",
        "| --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    observed = reactions.loc[reactions.status != "upcoming"].sort_values("event_time").tail(14)

    def fmt(value: object) -> str:
        return "N/A" if pd.isna(value) else f"{float(value):.6f}"

    for row in observed.itertuples():
        lines.append(
            f"| {row.catalyst} | {row.asset} | {fmt(row.post_1_close)} | {fmt(row.post_5_closes)} | {fmt(row.surprise)} | {row.move_unit} / {row.surprise_unit} | {row.status} |"
        )
    lines += ["", "## Upcoming risks", ""]
    upcoming = reactions.loc[reactions.status == "upcoming"].drop_duplicates("event_id")
    lines += [f"- {row.event_time}: {row.catalyst} ({row.source})" for row in upcoming.itertuples()]
    if upcoming.empty:
        lines.append("No upcoming events in the supplied dataset; coverage is not guaranteed.")
    lines += [
        "",
        "Detailed timestamps, sources, intraday and volatility changes: event_reactions.csv.",
    ]
    return "\n".join(lines) + "\n"
