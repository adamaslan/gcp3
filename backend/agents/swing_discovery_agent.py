"""Deterministic Swing discovery agent (A1)."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
from datetime import date
from typing import Any

from agents.base import AgentLoop
from config.agent_config import SwingConfig, load_swing_config
from feature_store import FEATURE_UNAVAILABLE, get_features
from firestore import write_agent_document
from schemas.swing import SwingEvidencePacket
from schemas.tool_result import ToolResult


FEATURES = [
    "bollinger",
    "rsi",
    "macd",
    "volume",
    "correlation",
    "regime",
    "alignment",
    "sector_relative",
    "breadth",
    "options_sentiment",
    "vix_term",
    "cross_asset",
]


class SwingDiscoveryAgent(AgentLoop):
    def __init__(self) -> None:
        super().__init__(endpoint="agents/swing/discovery")

    async def run(self, run_id: str, candidates: list[str], config: SwingConfig) -> list[SwingEvidencePacket]:  # type: ignore[override]
        packets = await asyncio.gather(
            *[self._analyze_candidate(run_id, ticker.strip().upper(), config) for ticker in candidates if ticker.strip()],
            return_exceptions=True,
        )
        out: list[SwingEvidencePacket] = []
        for ticker, packet in zip(candidates, packets):
            if isinstance(packet, Exception):
                out.append(self._failed_packet(run_id, ticker.strip().upper(), str(packet)))
            else:
                out.append(packet)
        return out

    async def _analyze_candidate(self, run_id: str, ticker: str, config: SwingConfig) -> SwingEvidencePacket:
        raw_features = await get_features(ticker, date.today(), FEATURES, timeframe="1D")
        feature_scores: dict[str, float] = {}
        tool_results: list[ToolResult] = []
        evidence: list[str] = []
        counter: list[str] = []
        risk_flags: list[str] = []

        for name in FEATURES:
            value = raw_features.get(name, FEATURE_UNAVAILABLE)
            score, ev, ce, flags = self._score_feature(name, value)
            feature_scores[name] = score
            evidence.extend(ev)
            counter.extend(ce)
            risk_flags.extend(flags)
            tr = ToolResult(
                tool_name=name,
                tool_family="technical" if name not in {"regime", "cross_asset"} else "risk",
                inputs_hash=self._hash(run_id, ticker, name),
                timeframe="1D",
                status="partial" if flags else "ok",
                score_delta=score,
                evidence=ev,
                counter_evidence=ce,
                risk_flags=flags,
                raw=value if isinstance(value, dict) else {},
            )
            tool_results.append(tr)
            self._persist_tool_result(run_id, ticker, 1, tr)

        if not counter:
            counter.append("no_material_counter_evidence_found")

        score = self._weighted_average(feature_scores, config.feature_weights)
        direction = "long" if score >= 0.58 else "short" if score <= 0.38 else "neutral"
        packet = SwingEvidencePacket(
            run_id=run_id,
            ticker=ticker,
            iteration_number=1,
            direction=direction,
            horizon="1w-3w",
            swing_discovery_score=score,
            feature_scores=feature_scores,
            tool_results=tool_results,
            supporting_evidence=evidence[:20],
            counter_evidence=counter[:20],
            risk_flags=sorted(set(risk_flags)),
            is_stale="feature_unavailable" in risk_flags,
            ai_degraded=True,
        )
        write_agent_document("swing_evidence_packets", f"{run_id}:{ticker}:1", packet.model_dump(mode="json"))
        return packet

    def _score_feature(self, name: str, value: Any) -> tuple[float, list[str], list[str], list[str]]:
        if value == FEATURE_UNAVAILABLE or value is None:
            return 0.35, [], [f"{name} unavailable"], ["feature_unavailable"]
        if not isinstance(value, dict):
            return 0.50, [f"{name} returned data"], [], []
        score = 0.50
        text = str(value).lower()
        if any(word in text for word in ["bullish", "accumulation", "positive", "uptrend", "risk_on"]):
            score += 0.20
        if any(word in text for word in ["bearish", "distribution", "negative", "downtrend", "risk_off"]):
            score -= 0.20
        for key in ("score", "signal_score", "percentile_rank", "relative_strength"):
            if isinstance(value.get(key), (int, float)):
                raw = float(value[key])
                score = raw if 0 <= raw <= 1 else max(0.0, min(1.0, (raw + 100) / 200))
                break
        return max(0.0, min(1.0, score)), [f"{name} score {score:.2f}"], [], []

    @staticmethod
    def _weighted_average(scores: dict[str, float], weights: dict[str, float]) -> float:
        if not scores:
            return 0.0
        mapped = {
            "liquidity": scores.get("volume", 0.5),
            "trend": (scores.get("bollinger", 0.5) + scores.get("macd", 0.5)) / 2,
            "momentum": scores.get("rsi", 0.5),
            "volume": scores.get("volume", 0.5),
            "volatility_quality": scores.get("bollinger", 0.5),
            "multi_timeframe": scores.get("alignment", 0.5),
            "sector_relative": scores.get("sector_relative", 0.5),
            "counter_evidence": 0.70,
        }
        total_weight = sum(weights.values()) or 1.0
        return round(sum(mapped.get(k, 0.5) * w for k, w in weights.items()) / total_weight, 4)

    def _failed_packet(self, run_id: str, ticker: str, error: str) -> SwingEvidencePacket:
        return SwingEvidencePacket(
            run_id=run_id,
            ticker=ticker,
            swing_discovery_score=0.0,
            feature_scores={},
            counter_evidence=[error[:240]],
            risk_flags=["tool_failed"],
            is_stale=True,
            ai_degraded=True,
        )

    @staticmethod
    def _hash(*parts: str) -> str:
        return hashlib.sha256(":".join(parts).encode()).hexdigest()[:16]

    @staticmethod
    def _persist_tool_result(run_id: str, ticker: str, iteration: int, result: ToolResult) -> None:
        key = f"{run_id}:{ticker}:{iteration}:{result.tool_name}:{result.inputs_hash}"
        write_agent_document("agent_tool_results", key, result.model_dump(mode="json"))


async def _cli() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", required=True)
    parser.add_argument("--mode", default="manual")
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()
    run_id = args.run_id or f"swing-{date.today().isoformat()}-{args.mode}"
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    packets = await SwingDiscoveryAgent().run(run_id, tickers, load_swing_config())
    print({"run_id": run_id, "packets": len(packets)})


if __name__ == "__main__":
    asyncio.run(_cli())
