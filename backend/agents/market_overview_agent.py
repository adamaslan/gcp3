"""Market overview specialist agent for /market-overview endpoint."""
from __future__ import annotations

import logging
from typing import Any

from agents.base import AgentLoop
from llm.grounded_call import generate_grounded

logger = logging.getLogger(__name__)


class MarketOverviewAgent(AgentLoop):
    """Extends AgentLoop for /market-overview: grounded search + breadth/sector context."""

    def __init__(self, model: str = "gemini-2.0-flash") -> None:
        super().__init__(endpoint="market-overview", model=model)

    async def run_overview(
        self,
        market_context: dict[str, Any],
        output_schema: Any,
        fallback_fn: Any = None,
    ) -> tuple[Any, Any]:
        """Run market-overview pipeline: grounded search → agent loop → structured output.

        Args:
            market_context: Dict of breadth, sector, and index data.
            output_schema: Pydantic schema for final output.
            fallback_fn: Rule-based fallback callable.

        Returns:
            Tuple of (parsed output | None, AgentSession).
        """
        grounded_summary = ""
        try:
            grounded = generate_grounded(
                prompt=(
                    "Summarize today's US stock market overview: S&P 500 breadth, "
                    "sector leadership, notable movers, and investor sentiment. "
                    "Be concise, 3-5 bullet points."
                ),
                endpoint="market-overview",
                model=self.model,
                prompt_version="overview_grounded_v1",
            )
            grounded_summary = grounded.text
        except Exception as e:
            logger.warning("market_overview_agent_grounding_failed error=%s", e)

        enriched_context = {**market_context, "grounded_news_summary": grounded_summary}
        return await self.run(
            ticker=None,
            initial_context=enriched_context,
            output_schema=output_schema,
            fallback_fn=fallback_fn,
        )
