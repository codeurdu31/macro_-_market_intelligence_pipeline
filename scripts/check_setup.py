from src.core.config import get_llm_config


def main() -> None:
    cfg = get_llm_config()

    print("✅ Setup OK")
    print("LLM_BASE_URL =", cfg["base_url"])
    print("LLM_MODEL    =", cfg["model"])
    print("LLM_API_KEY  = configured (hidden)")


if __name__ == "__main__":
    main()
