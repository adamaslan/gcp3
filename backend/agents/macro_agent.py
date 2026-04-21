"""Macro-pulse specialist agent for /macro-pulse endpoint."""
from __future__ import annotations

import logging
from typing import Any

from agents.base import AgentLoop
from llm.grounded_call import generate_grounded

logger = logging.getLogger(__name__)


class MacroAgent(AgentLoop):
    """Extends AgentLoop for /macro-pulse: grounded generation + tool calls."""

    def __init__(self, model: str = "gemini-2.0-flash") -> None:
        super().__init__(endpoint="macro-pulse", model=model)

    async def run_macro(
        self,
        macro_context: dict[str, Any],
        output_schema: Any,
        fallback_fn: Any = None,
    ) -> tuple[Any, Any]:
        """Run macro-pulse pipeline: grounded search → agent loop → structured output.

        Args:
            macro_context: Dict of macro indicator readings.
            output_schema: Pydantic schema for final output.
            fallback_fn: Rule-based fallback callable.

        Returns:
            Tuple of (parsed output | None, AgentSession).
        """
        # Grounded generation for news/market context
        grounded_summary = ""
        try:
            grounded = generate_grounded(
                prompt=(
                    "Summarize today's key macro events affecting US equities: "
                    "Fed signals, Treasury yields, DXY moves, credit spreads, "
                    "energy prices. Be concise, 3-5 bullet points."
                ),
                endpoint="macro-pulse",
                model=self.model,
                prompt_version="macro_grounded_v1",
            )
            grounded_summary = grounded.text
        except Exception as e:
            logger.warning("macro_agent_grounding_failed error=%s", e)

        enriched_context = {**macro_context, "grounded_news_summary": grounded_summary}
        return await self.run(
            ticker=None,
            initial_context=enriched_context,
            output_schema=output_schema,
            fallback_fn=fallback_fn,
        )
