from __future__ import annotations

from pathlib import Path
import matplotlib.pyplot as plt


def plot_net_exposure(net_exposure_by_ccy: dict[str, float], outpath: str) -> None:
    Path(outpath).parent.mkdir(parents=True, exist_ok=True)

    ccy = list(net_exposure_by_ccy.keys())
    vals = [net_exposure_by_ccy[k] for k in ccy]

    plt.figure(figsize=(10, 4))
    plt.bar(ccy, vals)
    plt.title("Net Exposure by Currency (USD notionals)")
    plt.xlabel("Currency")
    plt.ylabel("Net exposure (USD)")
    plt.tight_layout()
    plt.savefig(outpath)
    plt.close()


def plot_stress_pnl(pnl_down: float, pnl_up: float, outpath: str) -> None:
    Path(outpath).parent.mkdir(parents=True, exist_ok=True)

    labels = ["FX -2%", "FX +2%"]
    vals = [pnl_down, pnl_up]

    plt.figure(figsize=(6, 4))
    plt.bar(labels, vals)
    plt.title("Stress P&L (USD)")
    plt.xlabel("Scenario")
    plt.ylabel("PnL (USD)")
    plt.tight_layout()
    plt.savefig(outpath)
    plt.close()
