"""Blog Reviewer: Gemini reads today's blog post and produces 3-5 improvement suggestions."""
import logging
import os
from datetime import date, datetime, timedelta, timezone

import httpx

from firestore import delete_cache, get_cache, set_cache

logger = logging.getLogger(__name__)

REVIEW_FOCUS = [
    "Clarity — concepts explained for retail investors?",
    "Data grounding — does the post reference actual numbers?",
    "Hook strength — does the opening grab attention?",
    "Takeaway quality — is the closing actionable?",
    "Missing angles — what market context was available but unused?",
]


def _build_review_prompt(blog: dict) -> str:
    """Build the Gemini prompt for reviewing today's blog post."""
    return f"""You are a senior finance content editor. Review the following blog post and provide 3-5 specific, actionable improvement suggestions.

BLOG DATE: {blog['date']}
BLOG TITLE: {blog['title']}
BLOG BODY:
{blog['body']}

MARKET SNAPSHOT USED: {blog.get('market_snapshot', {})}

FOCUS AREAS:
{chr(10).join(f'{i+1}. {f}' for i, f in enumerate(REVIEW_FOCUS))}

INSTRUCTIONS:
- Give 3-5 numbered suggestions, each 1-3 sentences.
- Be specific — reference exact sentences or claims in the post.
- Score each suggestion by impact: [HIGH] [MEDIUM] [LOW]
- End with one overall score (1-10) and a single sentence summary.
- Format as clean markdown."""


async def _call_gemini_review(prompt: str) -> str:
    """Send a prompt to Gemini 2.0 Flash and return the text response."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={api_key}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    async with httpx.AsyncClient(timeout=45) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


async def get_blog_review() -> dict:
    """Get today's blog review (cached) or generate a new one via Gemini."""
    today = date.today()
    cache_key = f"blog_review:{today}"

    if cached := get_cache(cache_key):
        logger.info("blog_review cache hit key=%s", cache_key)
        return cached

    blog_key = f"daily_blog:{today}"
    blog = get_cache(blog_key)
    if not blog:
        logger.warning("blog_review: no blog found for %s, skipping", today)
        raise RuntimeError(f"No blog available for {today}")

    logger.info("blog_review cache miss — generating review for %s", today)
    prompt = _build_review_prompt(blog)
    review_text = await _call_gemini_review(prompt)
    logger.info("blog_review: Gemini response received (%d chars)", len(review_text))

    result = {
        "date": str(today),
        "blog_title": blog["title"],
        "blog_theme_id": blog["theme_id"],
        "suggestions": review_text,
        "focus_areas": REVIEW_FOCUS,
    }

    # Cache until midnight UTC
    now = datetime.now(timezone.utc)
    tomorrow = datetime(now.year, now.month, now.day, tzinfo=timezone.utc) + timedelta(days=1)
    ttl_hours = max(1, int((tomorrow - now).total_seconds() / 3600))
    set_cache(cache_key, result, ttl_hours=ttl_hours)
    return result


async def refresh_blog_review() -> dict:
    """Delete today's cache and regenerate. Called by Cloud Scheduler."""
    cache_key = f"blog_review:{date.today()}"
    delete_cache(cache_key)
    logger.info("blog_review cache cleared for refresh key=%s", cache_key)
    return await get_blog_review()
