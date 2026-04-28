"""One-shot script: generate ai_summary, daily_blog, blog_review, and daily_story
and push all four to Firestore.

Run from backend/ with fin-ai1 activated:
    python run_content_refresh.py
"""
import asyncio
import logging
import sys
from datetime import date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("content_refresh")


async def main() -> None:
    from ai_summary import refresh_ai_summary
    from daily_blog import refresh_daily_blog
    from blog_reviewer import refresh_blog_review
    from story_picker import refresh_story_article

    today = date.today()
    logger.info("Starting content refresh for %s", today)
    results: dict[str, str] = {}

    # 1. AI Summary
    logger.info("=== Stage 1/4: ai_summary ===")
    try:
        summary = await refresh_ai_summary()
        results["ai_summary"] = "ok"
        logger.info("ai_summary done — %d chars in brief", len(summary.get("brief", "")))
    except Exception as exc:
        results["ai_summary"] = f"ERROR: {exc}"
        logger.error("ai_summary failed: %s", exc)

    # 2. Daily Blog
    logger.info("=== Stage 2/4: daily_blog ===")
    try:
        blog = await refresh_daily_blog()
        results["daily_blog"] = "ok"
        logger.info("daily_blog done — theme=%s title=%s", blog.get("theme_id"), blog.get("title"))
    except Exception as exc:
        results["daily_blog"] = f"ERROR: {exc}"
        logger.error("daily_blog failed: %s", exc)

    # 3. Blog Review (depends on daily_blog being in Firestore)
    logger.info("=== Stage 3/4: blog_review ===")
    try:
        review = await refresh_blog_review()
        results["blog_review"] = "ok"
        logger.info(
            "blog_review done — %d chars in suggestions", len(review.get("suggestions", ""))
        )
    except Exception as exc:
        results["blog_review"] = f"ERROR: {exc}"
        logger.error("blog_review failed: %s", exc)

    # 4. Daily Story
    logger.info("=== Stage 4/4: daily_story ===")
    try:
        story = await refresh_story_article()
        results["daily_story"] = "ok"
        logger.info(
            "daily_story done — title=%s pair=%s",
            story.get("title"),
            story.get("extreme_pair", {}).get("pair_id"),
        )
    except Exception as exc:
        results["daily_story"] = f"ERROR: {exc}"
        logger.error("daily_story failed: %s", exc)

    logger.info("=== Content refresh complete ===")
    for name, status in results.items():
        logger.info("  %-15s %s", name, status)

    if any(v.startswith("ERROR") for v in results.values()):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
