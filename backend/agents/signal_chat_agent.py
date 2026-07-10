"""Per-ticker signal-explain chat agent (interactivity Axis 2, ask-anything tool use).

Lets a user ask a free-form question about one ticker's live signal
("why bullish?", "what would flip this bearish?") and answers it via the
existing ReAct tool-calling loop instead of an LLM guessing from training
data alone — the agent must call `explain_signal` to see the real score,
action, and contributing signal counts before answering.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from agents.base import AgentLoop

logger = logging.getLogger(__name__)


class SignalChatAgent(AgentLoop):
    """Answers a free-form question about one ticker's live scored signal."""

    SYSTEM_PROMPT: str = (
        "You are a financial signal explainer. The user is asking about a specific "
        "ticker's current BUY/HOLD/SELL signal. Call explain_signal first to see the "
        "real score, action, contributing signal counts, and data quality before "
        "answering — never guess. Be concise and concrete. Max {max_turns} turns, "
        "{max_tools} tool calls, {max_seconds}s total."
    ).format(max_turns=4, max_tools=5, max_seconds=15)

    AVAILABLE_TOOLS = ["explain_signal"]

    def __init__(self, model: str = "gemini-2.0-flash") -> None:
        super().__init__(endpoint="signals/chat", model=model)

    def _build_initial_prompt(self, ticker: str | None, context: dict[str, Any]) -> str:
        question = context.get("question", "")
        return (
            f"Ticker: {ticker}\n"
            f"Question: {question}\n\n"
            f"Available tools: {', '.join(self.AVAILABLE_TOOLS)}\n"
            f"Call explain_signal with this ticker first. Then answer the question "
            f"using what it returns. Return your final answer as JSON matching this "
            f'shape exactly: {{"ticker": "{ticker}", "answer": "<your answer>"}}'
        )

    async def ask(self, ticker: str, question: str) -> tuple[str, bool, int]:
        """Answer a question about a ticker's signal.

        Returns:
            Tuple of (answer text, fallback_used, tool_call_count). Answer text
            is a plain-language explanation, or a safe fallback message if the
            agent loop couldn't produce structured output.
        """
        from schemas.signal_chat import SignalChatResponse

        result, session = await self.run(
            ticker=ticker,
            initial_context={"question": question},
            output_schema=SignalChatResponse,
            fallback_fn=lambda: {
                "ticker": ticker,
                "answer": (
                    "I wasn't able to look up that signal right now — try again "
                    "in a moment."
                ),
            },
        )

        # The system prompt instructs the model to call explain_signal before
        # answering, but that's not enforced by the loop itself — a model can
        # skip straight to a final answer with zero tool calls, which would be
        # ungrounded/hallucinated signal data. Refuse rather than trust it.
        if not session.tool_calls:
            logger.warning(
                "signal_chat_no_tool_call ticker=%s — model answered without "
                "calling explain_signal, discarding its response",
                ticker,
            )
            return (
                "I wasn't able to look up that signal's real data just now — "
                "please try again.",
                True,
                0,
            )

        answer = result.answer if result is not None else (
            "I wasn't able to answer that — try rephrasing your question."
        )
        return answer, session.fallback_used, len(session.tool_calls)
