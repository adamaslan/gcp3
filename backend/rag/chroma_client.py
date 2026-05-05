"""Minimal Chroma facade placeholder for run-scoped RAG."""
from __future__ import annotations


class ChromaRunClient:
    def __init__(self) -> None:
        self.enabled = False

    def query(self, run_id: str, question: str, max_chunks: int = 6) -> list[dict]:
        return []

