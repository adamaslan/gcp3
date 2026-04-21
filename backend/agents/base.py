"""ReAct agent loop with hard budgets (Weakness #9).

Hard limits: max 4 turns, max 5 tool calls/session, 15s wallclock.
Falls back to one-shot call on budget-exceeded, then rule-based.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

MAX_TURNS = 4
MAX_TOOL_CALLS = 5
MAX_WALLCLOCK_SECONDS = 15.0


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]
    result: Any = None
    error: str | None = None


@dataclass
class AgentSession:
    endpoint: str
    ticker: str | None
    turns: int = 0
    tool_calls: list[ToolCall] = field(default_factory=list)
    start_time: float = field(default_factory=time.perf_counter)
    budget_exceeded: bool = False
    fallback_used: bool = False

    def elapsed_seconds(self) -> float:
        return time.perf_counter() - self.start_time

    def can_call_tool(self) -> bool:
        if self.turns >= MAX_TURNS:
            return False
        if len(self.tool_calls) >= MAX_TOOL_CALLS:
            return False
        if self.elapsed_seconds() > MAX_WALLCLOCK_SECONDS:
            return False
        return True


# Built-in tool registry for the agent loop
_TOOL_REGISTRY: dict[str, Callable] = {}


def register_tool(name: str, fn: Callable) -> None:
    _TOOL_REGISTRY[name] = fn


async def _dispatch_tool(name: str, args: dict[str, Any]) -> Any:
    fn = _TOOL_REGISTRY.get(name)
    if fn is None:
        raise ValueError(f"Unknown tool: {name}")
    if asyncio.iscoroutinefunction(fn):
        return await fn(**args)
    return fn(**args)


class AgentLoop:
    """Base ReAct agent loop."""

    SYSTEM_PROMPT: str = (
        "You are a financial analysis agent. Use tools to gather evidence, "
        "then produce a structured signal. Be concise. Max {max_turns} turns, "
        "{max_tools} tool calls, {max_seconds}s total."
    ).format(max_turns=MAX_TURNS, max_tools=MAX_TOOL_CALLS, max_seconds=int(MAX_WALLCLOCK_SECONDS))

    AVAILABLE_TOOLS = [
        "fetch_recent_news",
        "compute_return",
        "check_earnings_date",
        "get_correlation",
        "fetch_macro_indicator",
    ]

    def __init__(self, endpoint: str, model: str = "gemini-2.0-flash") -> None:
        self.endpoint = endpoint
        self.model = model

    async def run(
        self,
        ticker: str | None,
        initial_context: dict[str, Any],
        output_schema: Any,
        fallback_fn: Callable | None = None,
    ) -> tuple[Any, AgentSession]:
        """Execute the ReAct loop.

        Args:
            ticker: Optional ticker symbol.
            initial_context: Initial feature dict for the prompt.
            output_schema: Pydantic schema for the final structured output.
            fallback_fn: Callable() -> dict for rule-based fallback.

        Returns:
            Tuple of (parsed output | None, AgentSession with audit log).
        """
        session = AgentSession(endpoint=self.endpoint, ticker=ticker)
        messages: list[dict] = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": self._build_initial_prompt(ticker, initial_context)},
        ]

        result = None
        while session.turns < MAX_TURNS:
            if session.elapsed_seconds() > MAX_WALLCLOCK_SECONDS:
                logger.warning(
                    "agent_budget_wallclock endpoint=%s ticker=%s elapsed=%.1fs",
                    self.endpoint, ticker, session.elapsed_seconds(),
                )
                session.budget_exceeded = True
                break

            session.turns += 1
            response_text = await self._call_llm(messages)

            # Check if the model wants to call a tool
            tool_request = self._parse_tool_request(response_text)
            if tool_request and session.can_call_tool():
                tc = ToolCall(name=tool_request["tool"], args=tool_request.get("args", {}))
                try:
                    tc.result = await _dispatch_tool(tc.name, tc.args)
                except Exception as e:
                    tc.error = str(e)
                    logger.warning("agent_tool_error tool=%s error=%s", tc.name, e)
                session.tool_calls.append(tc)
                messages.append({"role": "assistant", "content": response_text})
                messages.append({
                    "role": "tool",
                    "content": json.dumps({"tool": tc.name, "result": tc.result, "error": tc.error}),
                })
                continue

            # No tool call — attempt to parse final output
            try:
                result = output_schema.model_validate_json(response_text)
                break
            except Exception as e:
                logger.warning("agent_parse_failed turn=%d error=%s", session.turns, e)
                messages.append({"role": "assistant", "content": response_text})
                messages.append({
                    "role": "user",
                    "content": f"Parsing failed: {e}. Return valid JSON only.",
                })

        # Budget-exceeded: one-shot fallback
        if result is None and session.budget_exceeded:
            logger.warning("agent_one_shot_fallback endpoint=%s ticker=%s", self.endpoint, ticker)
            one_shot_prompt = messages[1]["content"]  # original user prompt
            one_shot_text = await self._call_llm([
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": one_shot_prompt},
            ])
            try:
                result = output_schema.model_validate_json(one_shot_text)
            except Exception:
                pass

        # Rule-based fallback
        if result is None and fallback_fn is not None:
            logger.warning("agent_rule_fallback endpoint=%s ticker=%s", self.endpoint, ticker)
            session.fallback_used = True
            try:
                result = output_schema.model_validate(fallback_fn())
            except Exception as e:
                logger.error("agent_rule_fallback_failed error=%s", e)

        self._log_session(session)
        return result, session

    async def _call_llm(self, messages: list[dict]) -> str:
        try:
            import google.generativeai as genai  # type: ignore
            history = []
            system = ""
            for m in messages:
                if m["role"] == "system":
                    system = m["content"]
                elif m["role"] in ("user", "tool"):
                    history.append({"role": "user", "parts": [m["content"]]})
                else:
                    history.append({"role": "model", "parts": [m["content"]]})

            gemini_model = genai.GenerativeModel(
                model_name=self.model,
                system_instruction=system,
            )
            chat = gemini_model.start_chat(history=history[:-1])
            response = chat.send_message(history[-1]["parts"][0] if history else "")
            return response.text or ""
        except Exception as e:
            logger.error("agent_llm_call_failed error=%s", e)
            return ""

    def _build_initial_prompt(self, ticker: str | None, context: dict[str, Any]) -> str:
        ctx_str = json.dumps(context, indent=2, default=str)
        return (
            f"Analyze {'ticker ' + ticker if ticker else 'the market'} using the following context:\n"
            f"{ctx_str}\n\n"
            f"Available tools: {', '.join(self.AVAILABLE_TOOLS)}\n"
            f"Call tools as needed, then return structured JSON output."
        )

    def _parse_tool_request(self, text: str) -> dict | None:
        """Detect if the LLM response is a tool call JSON."""
        text = text.strip()
        if not text.startswith("{"):
            return None
        try:
            parsed = json.loads(text)
            if "tool" in parsed and parsed["tool"] in self.AVAILABLE_TOOLS:
                return parsed
        except json.JSONDecodeError:
            pass
        return None

    def _log_session(self, session: AgentSession) -> None:
        logger.info(
            "agent_session endpoint=%s ticker=%s turns=%d tool_calls=%d elapsed_ms=%.0f "
            "budget_exceeded=%s fallback_used=%s",
            session.endpoint,
            session.ticker,
            session.turns,
            len(session.tool_calls),
            session.elapsed_seconds() * 1000,
            session.budget_exceeded,
            session.fallback_used,
        )


# Default tool implementations
async def _fetch_recent_news(ticker: str, days: int = 3) -> list[str]:
    try:
        from news_sentiment import get_news_sentiment
        data = await get_news_sentiment()
        return [str(item) for item in data.get("articles", [])[:5]]
    except Exception as e:
        return [f"news_unavailable: {e}"]


async def _compute_return(ticker: str, days: int = 5) -> float:
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period=f"{days + 2}d")
        if len(hist) >= 2:
            return round((hist["Close"].iloc[-1] / hist["Close"].iloc[-days - 1] - 1) * 100, 4)
    except Exception:
        pass
    return float("nan")


async def _check_earnings_date(ticker: str) -> dict:
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).calendar
        return {"earnings_date": str(info.get("Earnings Date", "unknown"))}
    except Exception:
        return {"earnings_date": "unknown"}


async def _get_correlation(ticker_a: str, ticker_b: str, days: int = 20) -> float:
    try:
        import yfinance as yf
        import pandas as pd
        data = yf.download([ticker_a, ticker_b], period=f"{days + 5}d", progress=False)["Close"]
        return round(float(data.corr().iloc[0, 1]), 4)
    except Exception:
        return float("nan")


async def _fetch_macro_indicator(indicator: str) -> dict:
    try:
        import httpx
        url = f"https://api.stlouisfed.org/fred/series/observations?series_id={indicator}&api_key=&file_type=json&limit=1&sort_order=desc"
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(url)
            obs = resp.json().get("observations", [{}])
            return {"indicator": indicator, "value": obs[0].get("value"), "date": obs[0].get("date")}
    except Exception as e:
        return {"indicator": indicator, "error": str(e)}


# Register defaults
register_tool("fetch_recent_news", _fetch_recent_news)
register_tool("compute_return", _compute_return)
register_tool("check_earnings_date", _check_earnings_date)
register_tool("get_correlation", _get_correlation)
register_tool("fetch_macro_indicator", _fetch_macro_indicator)
