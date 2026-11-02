"""Vectors for semantic search, from any OpenAI-compatible embeddings endpoint (bring your own key).

OpenAI, Voyage, Azure-style gateways and a local Ollama all take `POST {model, input: [...]}` and
answer `{data: [{index, embedding}]}`. Off unless EMBEDDING_API_KEY is set.
"""

import array
import math
import operator
from urllib.parse import urlsplit

import aiohttp
import structlog

from app.core.config import get_settings

logger = structlog.get_logger()

BATCH_SIZE = 64  # texts per request, under every provider's per-request limit
MAX_TEXT_CHARS = 2000  # per text; keeps a request well under token limits
TIMEOUT_SECONDS = 60


class EmbeddingError(Exception):
    """The embedding API could not be used; the message is safe to show"""

    user_facing = True


def is_configured() -> bool:
    return bool(get_settings().embedding_api_key)


def model_name() -> str:
    return get_settings().embedding_model


async def embed(texts: list[str], kind: str = "document") -> list[bytes]:
    """Unit-length float32 vectors for `texts`, in order. `kind` is "document" or "query".

    Raises EmbeddingError. Error messages carry the status only, never the provider's text,
    which can echo part of the key.
    """
    settings = get_settings()
    voyage = urlsplit(settings.embedding_api_url).hostname == "api.voyageai.com"
    headers = {"Authorization": f"Bearer {settings.embedding_api_key}"}
    vectors: list[bytes] = []
    async with aiohttp.ClientSession(
        headers=headers, timeout=aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)
    ) as session:
        for start in range(0, len(texts), BATCH_SIZE):
            inputs = [text[:MAX_TEXT_CHARS] or " " for text in texts[start : start + BATCH_SIZE]]
            payload = {"model": settings.embedding_model, "input": inputs}
            if voyage:
                payload["input_type"] = kind  # Voyage embeds queries and documents differently
            try:
                async with session.post(settings.embedding_api_url, json=payload) as response:
                    if response.status != 200:
                        logger.warning("Embedding API error", status=response.status)
                        hint = "; check EMBEDDING_API_KEY" if response.status in (401, 403) else ""
                        raise EmbeddingError(f"The embedding API answered {response.status}{hint}")
                    body = await response.json(content_type=None)
            except (aiohttp.ClientError, TimeoutError, ValueError) as e:
                raise EmbeddingError(f"Could not use the embedding API ({type(e).__name__})") from e
            data = body.get("data") if isinstance(body, dict) else None
            try:
                if len(data) != len(inputs):
                    raise ValueError("wrong count")
                vectors.extend(_pack(item["embedding"]) for item in sorted(data, key=lambda d: d.get("index", 0)))
            except (KeyError, TypeError, ValueError, AttributeError) as e:
                raise EmbeddingError("The embedding API returned an unexpected response") from e
    return vectors


def _pack(values: list[float]) -> bytes:
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return array.array("f", (v / norm for v in values)).tobytes()


def unpack(blob: bytes) -> array.array:
    vector = array.array("f")
    vector.frombytes(blob)
    return vector


def similarity(a: array.array, b: array.array) -> float:
    """Cosine similarity of two unit vectors"""
    # shortcut: brute force in plain Python, about 0.1 s per 1000 definitions; switch to numpy
    # or sqlite-vec if repositories grow past tens of thousands of definitions
    return sum(map(operator.mul, a, b)) if len(a) == len(b) else -1.0
