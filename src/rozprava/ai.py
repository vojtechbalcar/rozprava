"""The one place that calls paid AI services: Voyage embeddings and Claude summaries.

Every request is recorded in ai_usage with its tokens and list-price cost.
Embedding stops before a model's recorded tokens would pass the configured limit,
which is set inside Voyage's free allowance. Embedded search queries are cached in
query_embedding, so a repeated query costs nothing. A summary is written only if its
worst-case cost still fits this calendar month's limit for Claude. Failures raise
AIUnavailable; callers fall back to results without AI. Importing this module
performs no I/O.
"""

import time
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

import anthropic
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
    # Claude Haiku 5.5 up to 100K prompt tokens; summaries stay far below.
    "claude-haiku-5-5": (Decimal("0.10"), Decimal("0.50")),
    "claude-sonnet-5-5": (Decimal("2"), Decimal("10")),
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


def cost(model: str, input_tokens: int, output_tokens: int = 0) -> Decimal:
    price_in, price_out = PRICES.get(model, (Decimal(0), Decimal(0)))
    return (input_tokens * price_in + output_tokens * price_out) / Decimal(1_000_000)


def record(
    session: Session, provider: str, model: str, purpose: str, input_tokens: int, output_tokens=0
) -> None:
    session.add(
        models.AIUsage(
            provider=provider,
            model=model,
            purpose=purpose,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost(model, input_tokens, output_tokens),
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


# --- Claude summaries -------------------------------------------------------------------


@dataclass
class Answer:
    """A Claude response: content blocks (text blocks carry `citations`) and usage."""

    blocks: list[Any]
    stop_reason: str | None
    input_tokens: int
    output_tokens: int


class Writer(Protocol):
    model: str

    def write(self, system: str, content: list[dict], max_tokens: int) -> Answer: ...


class ClaudeWriter:
    def __init__(self, key: str, model: str, timeout: float = 60.0):
        self.model = model
        self._client = anthropic.Anthropic(api_key=key, timeout=timeout, max_retries=2)

    def write(self, system: str, content: list[dict], max_tokens: int) -> Answer:
        try:
            # Thinking is adaptive by default on Claude Haiku 5.5; effort keeps it brief.
            message = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": content}],  # type: ignore[list-item]
                output_config={"effort": "medium"},
            )
        except anthropic.RateLimitError as error:
            raise AIUnavailable("Claude rate limit reached") from error
        except anthropic.APIStatusError as error:
            raise AIUnavailable(f"Claude HTTP {error.status_code}: {error.message}") from error
        except anthropic.APIConnectionError as error:
            raise AIUnavailable("Claude did not answer") from error
        usage = message.usage
        return Answer(
            list(message.content),
            message.stop_reason,
            usage.input_tokens
            + (usage.cache_creation_input_tokens or 0)
            + (usage.cache_read_input_tokens or 0),
            usage.output_tokens,
        )


def writer(settings: Settings) -> Writer | None:
    """The configured summary writer, or None without an Anthropic key."""
    if settings.anthropic_api_key is None:
        return None
    return ClaudeWriter(settings.anthropic_api_key.get_secret_value(), settings.summary_model)


def month_spend(session: Session, provider: str = "anthropic") -> Decimal:
    usage = models.AIUsage
    return session.scalar(
        select(func.coalesce(func.sum(usage.cost_usd), 0)).where(
            usage.provider == provider,
            usage.created_at >= func.date_trunc("month", func.now()),
        )
    ) or Decimal(0)


def write_summary(
    session: Session,
    writer: Writer,
    system: str,
    content: list[dict],
    estimate: int,
    max_tokens: int,
    limit_usd: Decimal,
) -> Answer:
    """Ask Claude, unless the worst case (estimated input, full output) would pass the
    monthly limit. The usage is committed even when the answer is a refusal."""
    spent = month_spend(session)
    if spent + cost(writer.model, estimate, max_tokens) > limit_usd:
        raise LimitReached(f"Claude has used ${spent:.2f} of ${limit_usd} this month")
    answer = writer.write(system, content, max_tokens)
    record(session, "anthropic", writer.model, "summary", answer.input_tokens, answer.output_tokens)
    session.commit()
    if answer.stop_reason == "refusal":
        raise AIUnavailable("Claude declined to summarise")
    return answer
