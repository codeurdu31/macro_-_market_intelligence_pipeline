import os
from dotenv import load_dotenv

load_dotenv()


def get_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


def get_llm_config() -> dict:
    return {
        "api_key": get_env("LLM_API_KEY"),
        "base_url": get_env("LLM_BASE_URL"),
        "model": get_env("LLM_MODEL"),
    }
