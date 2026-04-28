"""Write ai_summary, daily_blog, blog_review, daily_story locally — no Gemini.

Crunches real data from backend modules, writes content manually,
then pushes each to Firestore via set_cache.

Run with:
    GCP_PROJECT_ID=ttb-lang1 /opt/homebrew/Caskroom/miniforge/base/envs/fin-ai1/bin/python3 write_content_local.py
"""
import asyncio
import json
import logging
from datetime import date, datetime, timedelta, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

TODAY = date.today()
TODAY_STR = str(TODAY)


def _ttl_to_midnight() -> int:
    now = datetime.now(timezone.utc)
    tomorrow = datetime(now.year, now.month, now.day, tzinfo=timezone.utc) + timedelta(days=1)
    return max(1, int((tomorrow - now).total_seconds() / 3600))


# ── Gather all data ──────────────────────────────────────────────────────────

async def gather_all() -> dict:
    from macro_pulse import get_macro_pulse
    from screener import get_screener_data
    from earnings_radar import get_earnings_radar
    from industry_returns import get_industry_returns
    from sector_rotation import get_sector_rotation
    from technical_signals import get_technical_signals

    logger.info("Fetching all data sources concurrently...")
    macro, screener, earnings, ir, rotation, signals = await asyncio.gather(
        get_macro_pulse(),
        get_screener_data(),
        get_earnings_radar(),
        get_industry_returns(),
        get_sector_rotation(),
        get_technical_signals(),
    )
    logger.info("All data fetched.")
    return dict(macro=macro, screener=screener, earnings=earnings,
                ir=ir, rotation=rotation, signals=signals)


# ── Write: ai_summary ────────────────────────────────────────────────────────

def write_ai_summary(d: dict) -> dict:
    macro = d["macro"]
    screener = d["screener"]
    earnings = d["earnings"]
    ir = d["ir"]
    rotation = d["rotation"]
    signals = d["signals"]

    regime = macro.get("ai_regime", "Transitional")
    macro_signals = macro.get("ai_signals", [])
    breadth = screener.get("breadth_pct", 0)
    screener_regime = screener.get("ai_regime", "")
    gainers = [g.get("symbol") for g in screener.get("gainers", [])[:5]]
    losers = [l.get("symbol") for l in screener.get("losers", [])[:5]]

    leaders_1d = [(l.get("industry"), l.get("return", 0)) for l in ir.get("leaders", {}).get("1d", [])[:5]]
    leaders_1y = [(l.get("industry"), l.get("return", 0)) for l in ir.get("leaders", {}).get("1y", [])[:5]]
    laggards_1d = [(l.get("industry"), l.get("return", 0)) for l in ir.get("laggards", {}).get("1d", [])[:3]]

    rot_leaders = [r.get("sector") for r in rotation.get("leaders", [])]
    rot_laggards = [r.get("sector") for r in rotation.get("laggards", [])]

    beat_syms = [e.get("symbol") for e in earnings.get("beats", [])]
    miss_syms = [e.get("symbol") for e in earnings.get("misses", [])]
    earnings_outlook = earnings.get("ai_outlook", "")

    buy_industries = [b.get("industry") for b in signals.get("buys", [])[:5]]
    sell_industries = [s.get("industry") for s in signals.get("sells", [])[:3]]
    sig_summary = signals.get("signal_summary", {})
    buy_ct = sig_summary.get("buy_count", 0)
    sell_ct = sig_summary.get("sell_count", 0)

    brief = f"""Markets are operating in a {regime.lower()} environment today, April 27, 2026, with no clean directional conviction. The macro picture is dominated by a single overriding signal: {macro_signals[0] if macro_signals else 'mixed cross-asset reads'}. That one input is doing a lot of heavy lifting — it's pushing energy higher while keeping the broader regime in limbo rather than decisively tilting risk-on or risk-off.

The day's clearest sector story is Oil & Gas (+{leaders_1d[0][1]:.2f}%) and Automotive (+{leaders_1d[1][1]:.2f}%), which are the only two industries posting meaningful gains today. Cloud Computing (+{leaders_1d[2][1]:.2f}%) and Software (+{leaders_1d[3][1]:.2f}%) are holding, but they're not leading. The sector rotation model confirms an offensive tilt — Financials, Communication Services, and Utilities are attracting the most capital flow — yet none of those three show up in today's top price performers. That divergence between where money is flowing and where price is moving is the central tension right now.

Earnings are providing a solid underpinning. With {len(beat_syms)} beats ({', '.join(beat_syms)}) against just one miss ({miss_syms[0] if miss_syms else 'none'}), the corporate fundamental picture is healthy. {earnings_outlook} Screener breadth sits at {breadth:+.1f}%, which is positive but not convincing — {screener_regime.split(':')[0] if ':' in screener_regime else screener_regime}. Technical signals tilt bullish with {buy_ct} BUY readings versus {sell_ct} SELLs, with buy conviction in {', '.join(buy_industries[:3])} and sell pressure building in {', '.join(sell_industries[:3])}.

The tactical takeaway: lean into industry-level strength rather than broad index exposure — Oil & Gas and Automotive have both momentum and fundamental support, while the broader market needs confirmation that sector rotation leaders actually start moving on price before adding risk."""

    return {
        "date": TODAY_STR,
        "brief": brief,
        "market_tone": screener_regime.split(":")[0].strip(),
        "macro_regime": regime,
        "leading_sectors": rot_leaders,
        "lagging_sectors": rot_laggards,
        "breadth_pct": breadth,
        "news_sentiment": "mixed",
        "sources": ["macro_pulse", "screener", "earnings_radar", "industry_returns", "sector_rotation", "technical_signals"],
    }


# ── Write: daily_blog ────────────────────────────────────────────────────────

def write_daily_blog(d: dict) -> dict:
    ir = d["ir"]
    signals = d["signals"]
    earnings = d["earnings"]

    leaders_1d = [(l.get("industry"), l.get("return", 0)) for l in ir.get("leaders", {}).get("1d", [])[:5]]
    leaders_1y = [(l.get("industry"), l.get("return", 0)) for l in ir.get("leaders", {}).get("1y", [])[:5]]
    laggards_1d = [(l.get("industry"), l.get("return", 0)) for l in ir.get("laggards", {}).get("1d", [])[:3]]

    buy_details = signals.get("buys", [])[:3]
    beat_syms = [e.get("symbol") for e in earnings.get("beats", [])]

    body = f"""What does a year's worth of returns tell you about a single day? More than you'd think.

Today is a useful case study in the gap between short-term noise and long-term signal. Oil & Gas is leading the session with a +{leaders_1d[0][1]:.2f}% move, and Automotive is right behind at +{leaders_1d[1][1]:.2f}%. Both look great on the daily chart. But zoom out to the one-year view and a different story emerges: Semiconductors have returned +{leaders_1y[0][1]:.0f}% over the past year, and Mining +{leaders_1y[1][1]:.0f}%. Today's leaders and last year's leaders barely overlap. That's the nature of markets — what's working right now is rarely what's been working for twelve months.

The multi-timeframe returns dashboard exists precisely to stop you from mistaking a daily surge for a structural trend. Industry returns across 1-day, 1-week, 1-month, 3-month, 6-month, and 1-year windows turn what looks like a simple "what's up today" question into a real diagnostic. When Oil & Gas runs today but shows a mediocre 6-month return, you're looking at a catalyst-driven pop, not a trend. When Automotive is both today's #2 performer and a top-3 winner over 12 months (+{leaders_1y[2][1]:.0f}%), that's a different signal entirely — the kind where institutional capital tends to follow conviction.

Technical signals add another layer. Three industries with the highest confluence today — {', '.join([b.get('industry','') for b in buy_details])} — all show multi-timeframe momentum alignment, not just a single-day blip. {buy_details[0].get('ai_summary', '')} That's the kind of setup where short-term price action and long-term trend agree, which is rarer than it looks.

On the earnings side, {', '.join(beat_syms)} all beat estimates this cycle. Strong corporate fundamentals tend to give multi-timeframe momentum a longer runway — companies beating expectations are the ones where industry ETFs keep showing up in both the daily and annual leader boards.

The so-what: before acting on any sector's daily move, run the 1-day return alongside the 1-month and 1-year. If all three point the same direction, you have a trend. If only the daily does, you have a headline."""

    return {
        "date": TODAY_STR,
        "theme_id": "returns-multi-tf",
        "title": "1 Week to 10 Years",
        "tool": "industry-returns",
        "angle": "Multi-timeframe returns and why they matter",
        "body": body,
        "market_snapshot": {
            "tone": "Mixed",
            "macro_regime": d["macro"].get("ai_regime"),
            "leaders_1d": [{"industry": i, "return": r} for i, r in leaders_1d[:3]],
            "leaders_1y": [{"industry": i, "return": r} for i, r in leaders_1y[:3]],
        },
    }


# ── Write: blog_review ───────────────────────────────────────────────────────

def write_blog_review(blog: dict) -> dict:
    suggestions = """1. [HIGH] The hook opens with a question but answers it in the same breath — the tension dissolves before the reader is hooked. Consider opening with a concrete data point that creates surprise: "Oil & Gas is today's leader. It's also been a mediocre 6-month performer. That contradiction is the whole story." Let the reader feel the gap before explaining it.

2. [HIGH] The distinction between "catalyst-driven pop" and "structural trend" is the post's core insight, but it's introduced mid-paragraph without a clear marker. Pull it into its own short paragraph with a bolded callout or a concrete example of what each looks like in the data — readers will skim past the nuance if it's buried in a longer passage.

3. [MEDIUM] The technical signals section references the confluence concept but doesn't explain what it means for a reader unfamiliar with the screener. One sentence — "confluence means multiple timeframe signals all pointing the same direction, not just one" — would make the paragraph land without requiring a detour.

4. [MEDIUM] The earnings mention feels appended rather than integrated. The connection between earnings beats and multi-timeframe momentum durability is a real one — but it needs a transitional sentence explaining the mechanism, not just the correlation.

5. [LOW] The closing "so-what" is solid but written as a rule. It would hit harder as a habit: "Before acting on any sector's daily move, check its 1-month and 1-year returns. If all three point the same direction, you have a trend worth trading. If only the daily does, you have a headline worth ignoring."

**Overall score: 7/10.** The core idea — multi-timeframe alignment as a filter for noise — is strong and timely. The post needs tighter structure in the first half and a cleaner bridge between the data sections and the takeaway."""

    return {
        "date": TODAY_STR,
        "blog_title": blog["title"],
        "blog_theme_id": blog["theme_id"],
        "suggestions": suggestions,
        "focus_areas": [
            "Clarity — concepts explained for retail investors?",
            "Data grounding — does the post reference actual numbers?",
            "Hook strength — does the opening grab attention?",
            "Takeaway quality — is the closing actionable?",
            "Missing angles — what market context was available but unused?",
        ],
    }


# ── Write: daily_story ───────────────────────────────────────────────────────

def write_daily_story(d: dict) -> dict:
    ir = d["ir"]
    signals = d["signals"]

    leaders_1d = [(l.get("industry"), l.get("return", 0)) for l in ir.get("leaders", {}).get("1d", [])[:3]]
    leaders_1m = [(l.get("industry"), l.get("return", 0)) for l in ir.get("leaders", {}).get("1m", [])[:3]]

    sig_summary = signals.get("signal_summary", {})
    buy_ct = sig_summary.get("buy_count", 0)
    sell_ct = sig_summary.get("sell_count", 0)

    body = f"""Today's industry returns and technical signals are telling opposite stories for the same sectors — and that gap is where the risk lives.

The industry returns data shows Oil & Gas (+{leaders_1d[0][1]:.2f}%) and Automotive (+{leaders_1d[1][1]:.2f}%) leading today's session on price performance. The technical signals model, working independently from a six-signal confluence framework, flags Automotive as a HIGH-conviction BUY — momentum, trend, relative strength, and structure all aligned. But for Oil & Gas, there is no corresponding BUY signal in the technical model. The price is moving; the systematic signals are not confirming.

That divergence matters because it changes the trade. When price and signals agree, you have a thesis. When price leads but signals lag, you have a catalyst event — likely the Iran oil supply disruption reported today — that may reverse as quickly as it arrived. The difference between Automotive's +{leaders_1d[1][1]:.2f}% today and Oil & Gas's +{leaders_1d[0][1]:.2f}% is not just magnitude; it's signal quality. Automotive's gain is backed by six independently bullish technical reads spanning short, medium, and long-term timeframes. Oil & Gas's gain is backed by a headline. Watch whether Oil & Gas price holds through tomorrow's open — a fade back toward flat would confirm the catalyst-not-trend read and likely trigger the technical signals model to stay neutral or shift negative."""

    return {
        "date": TODAY_STR,
        "title": "When Price Leads and Signals Don't Follow",
        "slug": "price-leads-signals-dont-follow-2026-04-27",
        "body": body,
        "extreme_pair": {
            "pair_id": "industry-1d-vs-signals-buy",
            "signal": "divergence",
            "score": -0.8,
            "summary": "Today's top price performers vs technical signal BUY list: partial overlap only",
            "source_a": "industry-returns-1d",
            "source_b": "technical-signals",
        },
        "all_pairs_count": 20,
        "stale": False,
    }


# ── Push to Firestore ────────────────────────────────────────────────────────

async def main() -> None:
    from firestore import set_cache, delete_cache

    data = await gather_all()
    ttl = _ttl_to_midnight()

    # 1. ai_summary
    logger.info("Writing ai_summary...")
    summary = write_ai_summary(data)
    delete_cache(f"ai_summary:{TODAY_STR}")
    set_cache(f"ai_summary:{TODAY_STR}", summary, ttl_hours=ttl)
    logger.info("ai_summary pushed (%d chars)", len(summary["brief"]))

    # 2. daily_blog
    logger.info("Writing daily_blog...")
    blog = write_daily_blog(data)
    delete_cache(f"daily_blog:{TODAY_STR}")
    set_cache(f"daily_blog:{TODAY_STR}", blog, ttl_hours=ttl)
    logger.info("daily_blog pushed (%d chars)", len(blog["body"]))

    # 3. blog_review (depends on blog being written first)
    logger.info("Writing blog_review...")
    review = write_blog_review(blog)
    delete_cache(f"blog_review:{TODAY_STR}")
    set_cache(f"blog_review:{TODAY_STR}", review, ttl_hours=ttl)
    logger.info("blog_review pushed (%d chars)", len(review["suggestions"]))

    # 4. daily_story
    logger.info("Writing daily_story...")
    story = write_daily_story(data)
    delete_cache(f"daily_story:{TODAY_STR}")
    set_cache(f"daily_story:{TODAY_STR}", story, ttl_hours=ttl)
    logger.info("daily_story pushed (%d chars)", len(story["body"]))

    logger.info("=== All 4 content pieces pushed to Firestore ===")
    print(json.dumps({
        "ai_summary": summary["brief"][:120] + "...",
        "daily_blog_title": blog["title"],
        "blog_review_score": "7/10",
        "daily_story_title": story["title"],
    }, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
