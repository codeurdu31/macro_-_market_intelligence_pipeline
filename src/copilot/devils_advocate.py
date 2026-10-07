from __future__ import annotations

import json
from openai import OpenAI

from src.core.config import get_llm_config
from src.copilot.schemas import DevilsAdvocateReport


SYSTEM_PROMPT = """
You are a devil's advocate macro risk analyst.

Rules (STRICT):
- Use ONLY the provided inputs (exposures, top positions, scenarios, macro thesis).
- If information is insufficient, still produce 3 items using the prefix "INSUFFICIENT_INFO:".
- Keep items short, specific, and actionable.
- Output must match the schema exactly.
"""


def generate_devils_advocate_report(
    *,
    exposures: dict[str, float],
    top_positions: list[dict],
    scenarios: list[dict],
    macro_thesis: str,
) -> DevilsAdvocateReport:
    cfg = get_llm_config()
    client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])

    payload = {
        "exposures": exposures,
        "top_positions": top_positions,
        "scenarios": scenarios,
        "macro_thesis": macro_thesis,
    }

    user_prompt = f"""
Input data (JSON):
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""

    response = client.responses.parse(
        model=cfg["model"],
        input=[
            {"role": "system", "content": SYSTEM_PROMPT.strip()},
            {"role": "user", "content": user_prompt.strip()},
        ],
        text_format=DevilsAdvocateReport,
        temperature=0.0,
    )

    return response.output_parsed
