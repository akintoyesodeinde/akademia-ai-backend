import hashlib
import math
import re

import httpx

from app.ai.contracts import EmbeddingResult
from app.core.config import get_settings
from app.shared.errors import ExternalProviderError

STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "to",
    "in",
    "on",
    "for",
    "with",
    "is",
    "are",
    "was",
    "were",
    "be",
    "by",
    "as",
    "at",
    "from",
    "that",
    "this",
    "it",
    "what",
    "how",
    "why",
    "when",
    "where",
    "which",
    "who",
    "does",
    "do",
    "can",
    "explain",
    "describe",
}


def _tokenize_features(text: str) -> list[tuple[str, float]]:
    words = [
        w
        for w in re.findall(r"[a-z0-9]+", text.lower())
        if len(w) > 1 and w not in STOPWORDS
    ]
    features: list[tuple[str, float]] = []
    for w in words:
        features.append((f"w:{w}", 2.0))
        if len(w) > 4:
            features.append((f"stem:{w[:5]}", 1.5))
    for i in range(len(words) - 1):
        features.append((f"bg:{words[i]}_{words[i + 1]}", 2.5))
    return features


class DeterministicSemanticEmbeddingModel:
    """Feature-hashing L2-normalized embedding adapter (64-d) for reproducible local/CI vector search."""

    def __init__(
        self,
        model_id: str = "akademia-embed-v1",
        model_version: str = "v1",
        dimension: int = 64,
    ) -> None:
        self.provider_name = "deterministic"
        self.model_id = model_id
        self.model_version = model_version
        self.dimension = dimension

    def _embed_single(self, text: str) -> list[float]:
        vec = [0.0] * self.dimension
        features = _tokenize_features(text)
        if not features:
            vec[0] = 1.0
            return vec
        for token, weight in features:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if (digest[4] & 1) == 0 else -1.0
            vec[idx] += sign * weight
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 1e-9:
            vec = [round(v / norm, 6) for v in vec]
        else:
            vec[0] = 1.0
        return vec

    async def embed_texts(self, texts: list[str]) -> EmbeddingResult:
        vectors = [self._embed_single(t) for t in texts]
        total_tokens = sum(max(1, len(t.split())) for t in texts)
        return EmbeddingResult(
            vectors=vectors,
            model_id=self.model_id,
            model_version=self.model_version,
            dimension=self.dimension,
            total_tokens=total_tokens,
        )


class OpenAICompatibleEmbeddingModel:
    """OpenAI-compatible REST embedding adapter."""

    def __init__(self) -> None:
        settings = get_settings()
        self.provider_name = "openai_compatible"
        self.model_id = settings.ai_embedding_model
        self.model_version = "v1"
        self.dimension = settings.ai_embedding_dimension
        self.api_key = settings.ai_api_key
        self.base_url = settings.ai_base_url.rstrip("/")
        self.timeout = settings.ai_request_timeout_seconds

    async def embed_texts(self, texts: list[str]) -> EmbeddingResult:
        if not self.api_key:
            raise ExternalProviderError("AI_API_KEY is not configured for openai_compatible provider.")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/embeddings",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"model": self.model_id, "input": texts},
                )
                resp.raise_for_status()
                data = resp.json()
                vectors = [item["embedding"][: self.dimension] for item in data["data"]]
                total_tokens = int(data.get("usage", {}).get("total_tokens", len(texts) * 10))
                return EmbeddingResult(
                    vectors=vectors,
                    model_id=self.model_id,
                    model_version=self.model_version,
                    dimension=self.dimension,
                    total_tokens=total_tokens,
                )
            except Exception as exc:
                raise ExternalProviderError(f"Embedding provider request failed: {exc}") from exc
