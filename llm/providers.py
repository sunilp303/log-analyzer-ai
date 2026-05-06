from langchain_core.language_models import BaseChatModel
from config import LLM_PROVIDER, ANTHROPIC_MODEL, OPENAI_MODEL


def get_llm(temperature: float = 0) -> BaseChatModel:
    if LLM_PROVIDER == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=ANTHROPIC_MODEL, temperature=temperature)
    elif LLM_PROVIDER == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=OPENAI_MODEL, temperature=temperature)
    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER={LLM_PROVIDER!r}. Set to 'anthropic' or 'openai'."
        )


def get_embeddings():
    from config import EMBEDDINGS_PROVIDER, HUGGINGFACE_MODEL, OPENAI_API_KEY

    if EMBEDDINGS_PROVIDER == "openai":
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings()
    else:
        from langchain_community.embeddings import HuggingFaceEmbeddings
        return HuggingFaceEmbeddings(model_name=HUGGINGFACE_MODEL)
