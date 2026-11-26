"""The one place that calls paid AI services: Voyage embeddings (and Claude summaries).

Every request is recorded in ai_usage with its tokens and list-price cost.
Embedding stops before a model's recorded tokens would pass the configured limit,
which is set inside Voyage's free allowance. Embedded search queries are cached in
query_embedding, so a repeated query costs nothing. Failures raise AIUnavailable;
callers fall back to keyword search. Importing this module performs no I/O.
"""

import time
from collections.abc import Sequence
from decimal import Decimal
from typing import Protocol

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from rozprava import models
from rozprava.settings import Settings

# USD per million input and output tokens, from the providers' pricing pages
# (read 26 Nov 2026). Voyage's first 200 M tokens per model are free; usage is
# still recorded at list price.
PRICES: dict[str, tuple[Decimal, Decimal]] = {
    "voyage-4-large": (Decimal("0.12"), Decimal(0)),
    "voyage-4": (Decimal("0.06"), Decimal(0)),
    "voyage-4-lite": (Decimal("0.02"), Decimal(0)),
}


class AIUnavailable(Exception):
    """No key, a spending limit reached, or the service did not answer."""


class LimitReached(AIUnavailable):
    pass


class Embedder(Protocol):
    model: str

    def embed(self, texts: Sequence[str], input_type: str) -> tuple[list[list[float]], int]:
        """Vectors in input order, and the tokens billed. input_type: document or query."""
        ...


class VoyageEmbedder:
    URL = "https://api.voyageai.com/v1/embeddings"

    def __init__(
        self,
        key: str,
        model: str,
        timeout: float = 60.0,
        attempts: int = 6,
        client: httpx.Client | None = None,
    ):
        self.model = model
        self._key = key
        self._timeout = timeout
        self._attempts = attempts
        self._client = client or httpx.Client()

    def embed(self, texts: Sequence[str], input_type: str) -> tuple[list[list[float]], int]:
        payload = {
            "input": list(texts),
            "model": self.model,
            "input_type": input_type,
            "output_dimension": models.DIMENSIONS,
        }
        headers = {"Authorization": f"Bearer {self._key}"}
        problem = "no answer"
        for attempt in range(self._attempts):
            if attempt:
                time.sleep(min(60.0, 2.0**attempt))
            try:
                response = self._client.post(
                    self.URL, json=payload, headers=headers, timeout=self._timeout
                )
            except httpx.HTTPError as error:
                problem = type(error).__name__
                continue
            if response.status_code == 429 or response.status_code >= 500:
                problem = f"HTTP {response.status_code}"
                wait = response.headers.get("retry-after", "")
                if wait.isdigit() and attempt + 1 < self._attempts:
                    time.sleep(min(60, int(wait)))
                continue
            if response.status_code != 200:
                # The body explains the problem (e.g. too many tokens); it never has the key.
                raise AIUnavailable(f"Voyage HTTP {response.status_code}: {response.text[:300]}")
            data = response.json()
            rows = sorted(data["data"], key=lambda row: row["index"])
            return [row["embedding"] for row in rows], int(data["usage"]["total_tokens"])
        raise AIUnavailable(f"Voyage did not answer ({problem})")


def embedder(settings: Settings, **options) -> Embedder | None:
    """The configured embedder, or None without a Voyage key."""
    if settings.voyage_api_key is None:
        return None
    return VoyageEmbedder(
        settings.voyage_api_key.get_secret_value(), settings.embedding_model, **options
    )


def record(
    session: Session, provider: str, model: str, purpose: str, input_tokens: int, output_tokens=0
) -> None:
    price_in, price_out = PRICES.get(model, (Decimal(0), Decimal(0)))
    cost = (input_tokens * price_in + output_tokens * price_out) / Decimal(1_000_000)
    session.add(
        models.AIUsage(
            provider=provider,
            model=model,
            purpose=purpose,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
        )
    )


def tokens_used(session: Session, model: str) -> int:
    usage = models.AIUsage
    return (
        session.scalar(
            select(func.coalesce(func.sum(usage.input_tokens), 0)).where(usage.model == model)
        )
        or 0
    )


def embed_documents(
    session: Session, embedder: Embedder, texts: Sequence[str], estimate: int, limit: int
) -> list[list[float]]:
    """Embed passages for storage, refusing when `estimate` more tokens would pass `limit`.

    The usage row is added to the session; the caller commits it with the vectors.
    """
    used = tokens_used(session, embedder.model)
    if used + estimate > limit:
        raise LimitReached(
            f"{embedder.model} has used {used:,} of {limit:,} tokens; "
            "raise ROZPRAVA_EMBEDDING_TOKEN_LIMIT to continue (Voyage then charges)."
        )
    vectors, tokens = embedder.embed(texts, "document")
    record(session, "voyage", embedder.model, "documents", tokens)
    return vectors


def query_key(query: str) -> str:
    return " ".join(query.split())


def query_vector(session: Session, embedder: Embedder, query: str, limit: int) -> list[float]:
    """The embedding of a search query, cached across requests. Commits the session."""
    key = query_key(query)
    cached = session.scalar(
        select(models.QueryEmbedding.embedding).where(
            models.QueryEmbedding.model == embedder.model, models.QueryEmbedding.query == key
        )
    )
    if cached is not None:
        return cached
    if tokens_used(session, embedder.model) >= limit:
        raise LimitReached(f"{embedder.model} has reached its token limit")
    (vector,), tokens = embedder.embed([key], "query")
    session.execute(
        insert(models.QueryEmbedding)
        .values(model=embedder.model, query=key, embedding=vector)
        .on_conflict_do_nothing()
    )
    record(session, "voyage", embedder.model, "query", tokens)
    session.commit()
    return vector
