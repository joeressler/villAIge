from __future__ import annotations

import logging

import httpx

from config import AppConfig
from exceptions import ConfigurationError
from memory.embedding import EmbeddingProvider

logger = logging.getLogger(__name__)


class OllamaEmbeddingProvider(EmbeddingProvider):
    def __init__(self, base_url: str, model: str, dimension: int):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, text: str) -> list[float]:
        response = httpx.post(
            f"{self.base_url}/api/embed",
            json={"model": self.model, "input": text},
            timeout=60.0,
        )
        response.raise_for_status()
        payload = response.json()
        embeddings = payload.get("embeddings") or payload.get("embedding")
        if isinstance(embeddings, list) and embeddings and isinstance(embeddings[0], list):
            return [float(value) for value in embeddings[0]]
        if isinstance(embeddings, list):
            return [float(value) for value in embeddings]
        raise ConfigurationError("Ollama embedding response missing vectors")


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, base_url: str, api_key: str, model: str, dimension: int):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, text: str) -> list[float]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        response = httpx.post(
            f"{self.base_url}/embeddings",
            headers=headers,
            json={"model": self.model, "input": text},
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()["data"][0]["embedding"]
        return [float(value) for value in data]


class EmbeddingRouter:
    def __init__(self, config: AppConfig):
        self.config = config
        self._provider: EmbeddingProvider | None = None

    def get_provider(self) -> EmbeddingProvider:
        if self._provider is None:
            self._provider = self._build_provider()
        return self._provider

    def _build_provider(self) -> EmbeddingProvider:
        memory = self.config.memory
        provider = memory.embedding_provider.lower()
        if provider == "ollama":
            return OllamaEmbeddingProvider(
                base_url=self.config.llm.ollama_base_url,
                model=memory.embedding_model,
                dimension=memory.embedding_dim,
            )
        if provider == "openai":
            return OpenAIEmbeddingProvider(
                base_url=self.config.llm.openai_base_url,
                api_key=self.config.llm.openai_api_key,
                model=memory.embedding_model,
                dimension=memory.embedding_dim,
            )
        raise ConfigurationError(f"Unknown embedding provider: {provider}")

    def verify(self) -> None:
        provider = self.get_provider()
        vector = provider.embed("health check")
        if len(vector) != provider.dimension:
            raise ConfigurationError(
                f"Embedding dimension mismatch: expected {provider.dimension}, got {len(vector)}"
            )
        logger.info(
            "Embedding provider verified provider=%s model=%s dim=%s",
            self.config.memory.embedding_provider,
            self.config.memory.embedding_model,
            provider.dimension,
        )
