"""Research-only chat over persisted run artifacts."""
from __future__ import annotations

from compliance.research_only import sanitize_response_text
from schemas.rag import RagChatRequest, RagChatResponse


async def answer_run_question(request: RagChatRequest) -> RagChatResponse:
    text = (
        f"This is a research-only {request.system} run answer for {request.run_id}. "
        "Run-scoped vector citations are not yet indexed, so this response is limited to persisted structured results."
    )
    sanitized, violated = sanitize_response_text(text)
    return RagChatResponse(run_id=request.run_id, answer=sanitized, citations=[], sanitized=violated)

