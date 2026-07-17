"""
Provider abstraction so a bot's chat model is swappable (OpenAI / Anthropic /
Ollama) without touching call sites, per the "never hardcode providers"
requirement.

Important architectural note: Anthropic does not offer a public embeddings
endpoint. Rather than inventing one, embeddings are generated via OpenAI or
a local Ollama embedding model (see DEFAULT_EMBEDDING_PROVIDER), while chat
completion can independently use OpenAI, Anthropic, or Ollama. This mirrors
how real RAG stacks are actually built.
"""
from __future__ import annotations

import abc

import httpx
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI, OpenAI

from app.config import get_settings

settings = get_settings()


# ─────────────────────────── Chat (async — used by the API/websocket layer) ───────────────────────────
class ChatProvider(abc.ABC):
    @abc.abstractmethod
    async def generate(self, system: str, user_message: str, model: str) -> str:
        ...


class OpenAIChatProvider(ChatProvider):
    def __init__(self) -> None:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def generate(self, system: str, user_message: str, model: str) -> str:
        response = await self._client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user_message}],
            max_tokens=1000,
        )
        return (response.choices[0].message.content or "").strip()


class AnthropicChatProvider(ChatProvider):
    def __init__(self) -> None:
        if not settings.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured")
        self._client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    async def generate(self, system: str, user_message: str, model: str) -> str:
        response = await self._client.messages.create(
            model=model,
            max_tokens=1000,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )
        return "".join(block.text for block in response.content if block.type == "text").strip()


class OllamaChatProvider(ChatProvider):
    """Local/self-hosted models — no API key, no data leaving the customer's
    own infrastructure if they point OLLAMA_BASE_URL at their own host."""

    async def generate(self, system: str, user_message: str, model: str) -> str:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_message},
                    ],
                    "stream": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return (data.get("message", {}).get("content") or "").strip()


def get_chat_provider(name: str) -> ChatProvider:
    providers = {
        "openai": OpenAIChatProvider,
        "anthropic": AnthropicChatProvider,
        "ollama": OllamaChatProvider,
    }
    provider_cls = providers.get(name)
    if not provider_cls:
        raise ValueError(f"Unknown chat provider: {name}")
    return provider_cls()


# ─────────────────────────── Embeddings (sync — used by Celery workers) ───────────────────────────
class EmbeddingProvider(abc.ABC):
    @abc.abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        ...


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self) -> None:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        self._client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(model=settings.DEFAULT_EMBEDDING_MODEL, input=texts)
        return [item.embedding for item in response.data]


class OllamaEmbeddingProvider(EmbeddingProvider):
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        embeddings = []
        with httpx.Client(timeout=60.0) as client:
            for text in texts:
                resp = client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/embeddings",
                    json={"model": settings.DEFAULT_EMBEDDING_MODEL, "prompt": text},
                )
                resp.raise_for_status()
                embeddings.append(resp.json()["embedding"])
        return embeddings


def get_embedding_provider(name: str | None = None) -> EmbeddingProvider:
    name = name or settings.DEFAULT_EMBEDDING_PROVIDER
    providers = {
        "openai": OpenAIEmbeddingProvider,
        "ollama": OllamaEmbeddingProvider,
    }
    provider_cls = providers.get(name)
    if not provider_cls:
        raise ValueError(f"Unknown or unsupported embedding provider: {name}")
    return provider_cls()
