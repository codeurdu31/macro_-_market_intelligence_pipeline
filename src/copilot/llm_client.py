from __future__ import annotations

from openai import OpenAI
from src.core.config import get_llm_config
from src.copilot.schemas import MacroSignal


SYSTEM_PROMPT = """
You are a Macro Intelligence extractor for a Global Macro / Fixed Income / FX desk.

Rules (STRICT):
- Only use information present in the user text.
- If you are not sure, set surprise=0 and hawkishness=0 and keep impacts empty.
- For metrics fields, use null unless the text explicitly supports a direction or value.
- Evidence must be short quotes copied from the input text.
- Output must match the schema exactly.
"""


def extract_macro_signal(text: str, source_id: str) -> MacroSignal:
    cfg = get_llm_config()
    client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])

    user_prompt = f"""
SOURCE_ID: {source_id}

Text to analyze:
{text}
"""

    # Structured Outputs with Pydantic parsing (super clean)
    response = client.responses.parse(
        model=cfg["model"],
        input=[
            {"role": "system", "content": SYSTEM_PROMPT.strip()},
            {"role": "user", "content": user_prompt.strip()},
        ],
        text_format=MacroSignal,
        temperature=0.0,
    )

    return response.output_parsed
