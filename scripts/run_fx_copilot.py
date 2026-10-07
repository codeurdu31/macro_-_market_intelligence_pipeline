"""Collect real public macro/FX data and produce a portfolio desk report."""

import argparse
from datetime import datetime, timezone
from pathlib import Path

from src.copilot.fx_pipeline import DeskConfig, run_pipeline

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/fx_desk.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--no-llm", action="store_true", help="Collect real data without OpenAI calls"
    )
    args = parser.parse_args()
    config = DeskConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
    output = args.output or ROOT / "reports/fx_desk" / datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )
    print("Collecting official RSS, public calendar and ECB FX references...", flush=True)
    report = run_pipeline(ROOT, output, config, no_llm=args.no_llm)
    print(f"Report: {output / 'desk_report.md'}")
    print(
        f"Publications: {len(report['publications'])}; LLM budget slots: {report['llm_budget_slots_used']}; coverage issues: {len(report['issues'])}"
    )
    for issue in report["issues"]:
        print(f"  - {issue}")


if __name__ == "__main__":
    main()
