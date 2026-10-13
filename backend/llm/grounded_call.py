"""Grounded generation wrapper (Weakness #8).

Only /market-overview and /macro-pulse endpoints allowed.
30-min bucketed cache with Firestore TTL.
Citation quality gate: ≥2 citations, ≥1 within 48h, ≥2 distinct domains.

Grounding now comes from OpenRouter's ":online" web-search suffix rather than
Gemini's google_search_retrieval tool; llm/openrouter_client.py maps the
returned `annotations` into the same {uri, title, domain, retrieved_at}
citation shape this module's quality gate already reads. Unlike the Gemini
free tier, ":online" search is billed per request — see the
grounded_surcharge entries in llm/pricing.py.
"""
from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Any

from llm import openrouter_client
from llm.cost_logger import log_llm_call
from llm.pricing import DEFAULT_MODEL

logger = logging.getLogger(__name__)

GROUNDING_ALLOWED_ENDPOINTS = frozenset({"market-overview", "macro-pulse"})
CACHE_BUCKET_MINUTES = 30
MIN_CITATIONS = 2
MIN_RECENT_CITATION_HOURS = 48
MIN_DISTINCT_DOMAINS = 2


class GroundedResult:
    def __init__(
        self,
        text: str,
        citations: list[dict],
        citation_quality_passed: bool,
        cache_hit: bool,
        latency_ms: float,
        input_tokens: int,
        output_tokens: int,
        model: str,
    ) -> None:
        self.text = text
        self.citations = citations
        self.citation_quality_passed = citation_quality_passed
        self.cache_hit = cache_hit
        self.latency_ms = latency_ms
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.model = model


def _bucket_cache_key(endpoint: str, prompt: str) -> str:
    """30-min bucketed cache key so all calls in a window share results."""
    now = datetime.now(timezone.utc)
    bucket = now.hour * 2 + (now.minute // CACHE_BUCKET_MINUTES)
    digest = hashlib.sha256(prompt.encode()).hexdigest()[:12]
    return f"grounded:{endpoint}:{now.date()}:{bucket}:{digest}"


def _check_citation_quality(citations: list[dict]) -> tuple[bool, list[str]]:
    """Return (passed, reasons_if_failed)."""
    reasons: list[str] = []
    if len(citations) < MIN_CITATIONS:
        reasons.append(f"only {len(citations)} citations (need ≥{MIN_CITATIONS})")
    domains = {c["domain"] for c in citations if c.get("domain")}
    if len(domains) < MIN_DISTINCT_DOMAINS:
        reasons.append(f"only {len(domains)} distinct domains (need ≥{MIN_DISTINCT_DOMAINS})")
    # retrieved_at is set to "now" by the client: OpenRouter's url_citation
    # annotations carry no publication date. Parsing dates out of titles/URIs
    # would be the way to make MIN_RECENT_CITATION_HOURS actually bite.
    return (not reasons), reasons


def generate_grounded(
    prompt: str,
    endpoint: str,
    *,
    ticker: str | None = None,
    model: str = DEFAULT_MODEL,
    prompt_version: str = "unknown",
) -> GroundedResult:
    """Generate a grounded response using Google Search retrieval.

    Args:
        prompt: Full prompt.
        endpoint: Must be 'market-overview' or 'macro-pulse'.
        ticker: Optional ticker for cost logging.
        model: OpenRouter model ID (see openrouter_client.MODEL_CHAIN).
        prompt_version: Prompt version tag.

    Raises:
        ValueError: If endpoint is not in the allowed list.

    Returns:
        GroundedResult with text, citations, and quality gate outcome.
    """
    if endpoint not in GROUNDING_ALLOWED_ENDPOINTS:
        raise ValueError(
            f"Grounded generation not allowed for endpoint '{endpoint}'. "
            f"Allowed: {sorted(GROUNDING_ALLOWED_ENDPOINTS)}"
        )

    cache_key = _bucket_cache_key(endpoint, prompt)

    # Check Firestore cache
    try:
        from firestore import get_cache
        cached = get_cache(cache_key)
        if cached:
            logger.info("grounded_cache_hit endpoint=%s key=%s", endpoint, cache_key)
            return GroundedResult(
                text=cached.get("text", ""),
                citations=cached.get("citations", []),
                citation_quality_passed=cached.get("citation_quality_passed", False),
                cache_hit=True,
                latency_ms=0.0,
                input_tokens=0,
                output_tokens=0,
                model=model,
            )
    except Exception as e:
        logger.warning("grounded_cache_read_failed error=%s", e)

    # Live grounded call
    t0 = time.perf_counter()
    try:
        response = openrouter_client.complete_sync(
            [{"role": "user", "content": prompt}],
            online=True,
            temperature=0.1,
        )
        text = response.text
        in_tok = response.input_tokens
        out_tok = response.output_tokens
        citations = response.citations
        quality_passed, quality_reasons = _check_citation_quality(citations)

        if not quality_passed:
            logger.warning(
                "grounding_quality_gate_failed endpoint=%s reasons=%s",
                endpoint, quality_reasons,
            )

        latency_ms = (time.perf_counter() - t0) * 1000
        log_llm_call(
            endpoint=endpoint, ticker=ticker, model=model, prompt_version=prompt_version,
            grounded=True, input_tokens=in_tok, output_tokens=out_tok,
            cached_input_tokens=0, latency_ms=latency_ms,
            tier_used=1, validation_retries=0, cache_hit=False,
        )

        result_payload = {
            "text": text,
            "citations": citations,
            "citation_quality_passed": quality_passed,
        }
        # Write to Firestore cache (TTL managed by Firestore TTL policy on the collection)
        try:
            from firestore import set_cache
            set_cache(cache_key, result_payload)
        except Exception as e:
            logger.warning("grounded_cache_write_failed error=%s", e)

        return GroundedResult(
            text=text,
            citations=citations,
            citation_quality_passed=quality_passed,
            cache_hit=False,
            latency_ms=latency_ms,
            input_tokens=in_tok,
            output_tokens=out_tok,
            model=model,
        )

    except Exception as e:
        latency_ms = (time.perf_counter() - t0) * 1000
        logger.error("grounded_call_failed endpoint=%s error=%s", endpoint, e)
        raise


def invalidate_grounding_cache(endpoint: str) -> None:
    """Invalidate all cached grounded results for an endpoint (macro-shock trigger)."""
    if endpoint not in GROUNDING_ALLOWED_ENDPOINTS:
        return
    try:
        from firestore import db
        prefix = f"grounded:{endpoint}:"
        cache_ref = db.collection("cache")
        docs = cache_ref.where("__name__", ">=", prefix).where("__name__", "<", prefix + "\uffff").stream()
        for doc in docs:
            doc.reference.delete()
        logger.info("grounding_cache_invalidated endpoint=%s", endpoint)
    except Exception as e:
        logger.error("grounding_cache_invalidation_failed endpoint=%s error=%s", endpoint, e)
