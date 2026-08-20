from agentx.llm.ollama import OllamaLLM
from agentx.llm.openai import OpenAILLM


def get_llm(provider: str, model: str, base_url: str, api_key: str | None = None):
    if provider == "ollama":
        return OllamaLLM(model=model, base_url=base_url, api_key=api_key)
    elif provider == "openai":
        return OpenAILLM(model=model, base_url=base_url, api_key=api_key)
    else:
        raise ValueError(f"Unsupported provider: {provider}")
