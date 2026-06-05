from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import numpy as np


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, text: str) -> list[float]:
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        pass


class SentenceTransformerEmbedding(EmbeddingProvider):
    _instance: Optional["SentenceTransformerEmbedding"] = None

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None
        self._dim = 384

    @classmethod
    def get_instance(cls, model_name: str) -> "SentenceTransformerEmbedding":
        if cls._instance is None or cls._instance.model_name != model_name:
            cls._instance = cls(model_name)
        return cls._instance

    def _load_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.model_name)
                self._dim = getattr(
                    self._model,
                    "get_embedding_dimension",
                    self._model.get_sentence_embedding_dimension,
                )()
            except Exception:
                self._model = "fallback"

    @property
    def dimension(self) -> int:
        self._load_model()
        return self._dim

    def embed(self, text: str) -> list[float]:
        self._load_model()
        if self._model == "fallback":
            return self._hash_embed(text)
        vector = self._model.encode(text, normalize_embeddings=True)
        return vector.tolist()

    def _hash_embed(self, text: str) -> list[float]:
        rng = np.random.RandomState(hash(text) % (2**32))
        vec = rng.randn(self._dim).astype(np.float32)
        vec /= np.linalg.norm(vec) + 1e-8
        return vec.tolist()


class HashEmbedding(EmbeddingProvider):
    """Deterministic fallback when sentence-transformers unavailable."""

    def __init__(self, dim: int = 384):
        self._dim = dim

    @property
    def dimension(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        rng = np.random.RandomState(hash(text) % (2**32))
        vec = rng.randn(self._dim).astype(np.float32)
        vec /= np.linalg.norm(vec) + 1e-8
        return vec.tolist()
