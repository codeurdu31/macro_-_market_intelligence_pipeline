import json
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from src.data_sources.market_data import load_market_csv
from src.portfolio.exposures import gross_exposure_usd, net_exposure_by_ccy
from src.portfolio.models import PortfolioInput
from src.scenarios.stress import stress_pnl_usd

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "text",
    [
        "timestamp,A\n2024-01-01,100\n",
        "timestamp,A\n2024-01-01T00:00Z,100\n2024-01-01T00:00Z,101\n",
        "timestamp,A\n2024-01-01T00:00Z,\n",
        "timestamp,A,A\n2024-01-01T00:00Z,100,101\n",
    ],
)
def test_invalid_market_data_rejected(tmp_path, text):
    path = tmp_path / "bad.csv"
    path.write_text(text)
    with pytest.raises(ValueError):
        load_market_csv(path)


def test_legacy_fx_regression():
    p = PortfolioInput.model_validate_json((ROOT / "data/portfolio_demo.json").read_text())
    assert gross_exposure_usd(p.positions) == 110000
    assert net_exposure_by_ccy(p.positions)["USD"] == -110000
    assert stress_pnl_usd(p.positions, -0.02) == -1022


def test_offline_cli_end_to_end(tmp_path):
    cfg = json.loads((ROOT / "config/markets_demo.json").read_text())
    cfg["observations"] = 100
    config = tmp_path / "config.json"
    config.write_text(json.dumps(cfg))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.run_qis_lab",
            "--config",
            str(config),
            "--output",
            str(tmp_path / "report"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    out = tmp_path / "report"
    summary = json.loads((out / "summary.json").read_text())
    assert summary["provenance"]["synthetic"] is True
    assert summary["legacy_fx_risk"]["drawdown"] is None
    for name in [
        "desk_report.md",
        "vol_target_methodology.md",
        "vol_target.png",
        "momentum_monthly.csv",
    ]:
        assert (out / name).stat().st_size > 0
    history = pd.read_csv(out / "vol_target_history.csv")
    assert len(history) == 100

    # Exercise the separate CSV import path, without claiming imported means real data.
    cfg["assets"] = summary["provenance"]["assets"]
    config.write_text(json.dumps(cfg))
    imported = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.run_qis_lab",
            "--config",
            str(config),
            "--input-dir",
            str(out / "inputs"),
            "--output",
            str(tmp_path / "imported"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert imported.returncode == 0, imported.stderr
    second = json.loads((tmp_path / "imported/summary.json").read_text())
    assert second["provenance"]["data_mode"] == "imported_csv"
    assert second["vol_target"] == summary["vol_target"]
