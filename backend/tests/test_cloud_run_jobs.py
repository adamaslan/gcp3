"""Tests for every Cloud Scheduler-triggered endpoint (Cloud Run jobs).

Each job endpoint is tested for:
  1. Auth guard — unauthenticated requests are rejected with 401
  2. Happy path — correct auth + mocked dependencies → expected response shape
  3. Non-trading-day skip — endpoints that gate on trading day return "skipped"
  4. Stage error isolation — one stage failing does not crash the whole pipeline

Cloud Scheduler jobs in production:
  POST /refresh/premarket       gcp3-premarket-warmup          (8:30 AM ET)
  POST /refresh/fetch           gcp3-ai-summary-refresh        (9:30 AM ET Mon-Fri)
  POST /refresh/bake            (9:45 AM ET Mon-Fri)
  POST /refresh/intraday        gcp3-midday-intraday-refresh   (noon + 4:15 PM ET)
  POST /refresh/ai-summary      legacy endpoint
  POST /admin/purge-cache       gcp3-nightly-cache-purge       (2:00 AM ET)
  POST /admin/refresh-industry-cache  (manual / on-demand)
  POST /admin/compute-returns         (manual / on-demand)
  POST /admin/seed-etf-history        (manual / on-demand)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

import main as app_module

# TestClient wraps the ASGI app for sync HTTP calls
client = TestClient(app_module.app, raise_server_exceptions=False)

# Shared secret used in all auth-passing requests
_SECRET = "test-scheduler-secret"
_AUTH_HEADERS = {"X-Scheduler-Token": _SECRET}

# ── Helpers ────────────────────────────────────────────────────────────────────

def _patch_verify_scheduler():
    """No-op patch so auth does not block happy-path tests."""
    return patch.object(app_module, "_verify_scheduler", return_value=None)


def _patch_trading_day(is_trading: bool):
    return patch("main.is_trading_day", return_value=is_trading)


# ── /refresh/premarket ────────────────────────────────────────────────────────

class TestRefreshPremarket:
    """gcp3-premarket-warmup: 8:30 AM ET lightweight warm-up."""

    def test_no_auth_returns_401(self):
        resp = client.post("/refresh/premarket")
        assert resp.status_code == 401

    def test_wrong_secret_returns_401(self):
        with patch.dict(os.environ, {"SCHEDULER_SECRET": _SECRET}):
            resp = client.post("/refresh/premarket", headers={"X-Scheduler-Token": "wrong"})
        assert resp.status_code == 401

    def test_happy_path_returns_premarket_warmed(self):
        with _patch_verify_scheduler(), \
             patch("main.get_morning_brief", new_callable=AsyncMock, return_value={"ok": True}), \
             patch("main.get_news_sentiment", new_callable=AsyncMock, return_value={"ok": True}), \
             patch("main.get_macro_pulse", new_callable=AsyncMock, return_value={"ok": True}):
            resp = client.post("/refresh/premarket", headers=_AUTH_HEADERS)

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "premarket_warmed"
        assert "stages" in body
        assert "total_ms" in body

    def test_partial_stage_failure_still_returns_200(self):
        """One failing stage should not crash the endpoint."""
        with _patch_verify_scheduler(), \
             patch("main.get_morning_brief", new_callable=AsyncMock, side_effect=Exception("Finnhub down")), \
             patch("main.get_news_sentiment", new_callable=AsyncMock, return_value={"ok": True}), \
             patch("main.get_macro_pulse", new_callable=AsyncMock, return_value={"ok": True}):
            resp = client.post("/refresh/premarket", headers=_AUTH_HEADERS)

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "premarket_warmed"


# ── /refresh/fetch ────────────────────────────────────────────────────────────

class TestRefreshFetch:
    """gcp3-ai-summary-refresh: 9:30 AM ET Phase 1 data ingestion."""

    def test_no_auth_returns_401(self):
        resp = client.post("/refresh/fetch")
        assert resp.status_code == 401

    def test_skips_on_non_trading_day(self):
        with _patch_verify_scheduler(), _patch_trading_day(False):
            resp = client.post("/refresh/fetch", headers=_AUTH_HEADERS)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "skipped"
        assert body["reason"] == "not_trading_day"

    def test_happy_path_on_trading_day(self):
        with _patch_verify_scheduler(), \
             _patch_trading_day(True), \
             patch("main.trading_date", return_value=MagicMock()), \
             patch("main.seed_etf_history", new_callable=AsyncMock, return_value={"SPY": 100}), \
             patch("main.get_morning_brief", new_callable=AsyncMock, return_value={}), \
             patch("main.get_macro_pulse", new_callable=AsyncMock, return_value={}), \
             patch("main.get_earnings_radar", new_callable=AsyncMock, return_value={}), \
             patch("main.get_news_sentiment", new_callable=AsyncMock, return_value={}), \
             patch("main.get_sector_rotation", new_callable=AsyncMock, return_value={}), \
             patch("main.build_screener_cache", new_callable=AsyncMock, return_value={"total_screened": 270}), \
             patch("main.get_industry_data", new_callable=AsyncMock, return_value={"rankings": []}), \
             patch("main.write_checkpoint", return_value=None):
            resp = client.post("/refresh/fetch", headers=_AUTH_HEADERS)

        assert resp.status_code == 200
        body = resp.json()
        assert "stages" in body
        assert "total_ms" in body

    def test_f0_failure_does_not_abort_pipeline(self):
        """ETF history seed failure is non-fatal — later stages should still run."""
        with _patch_verify_scheduler(), \
             _patch_trading_day(True), \
             patch("main.trading_date", return_value=MagicMock()), \
             patch("main.seed_etf_history", new_callable=AsyncMock, side_effect=Exception("yfinance down")), \
             patch("main.get_morning_brief", new_callable=AsyncMock, return_value={}), \
             patch("main.get_macro_pulse", new_callable=AsyncMock, return_value={}), \
             patch("main.get_earnings_radar", new_callable=AsyncMock, return_value={}), \
             patch("main.get_news_sentiment", new_callable=AsyncMock, return_value={}), \
             patch("main.get_sector_rotation", new_callable=AsyncMock, return_value={}), \
             patch("main.build_screener_cache", new_callable=AsyncMock, return_value={}), \
             patch("main.get_industry_data", new_callable=AsyncMock, return_value={}), \
             patch("main.write_checkpoint", return_value=None):
            resp = client.post("/refresh/fetch", headers=_AUTH_HEADERS)

        assert resp.status_code == 200
        body = resp.json()
        assert body["stages"]["etf_history"]["status"] == "error"


# ── /refresh/bake ─────────────────────────────────────────────────────────────

class TestRefreshBake:
    """Phase 2: AI synthesis from cached data only."""

    def test_no_auth_returns_401(self):
        resp = client.post("/refresh/bake")
        assert resp.status_code == 401

    def test_skips_on_non_trading_day(self):
        with _patch_verify_scheduler(), _patch_trading_day(False):
            resp = client.post("/refresh/bake", headers=_AUTH_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["status"] == "skipped"

    def test_aborts_503_when_no_fetch_checkpoint(self):
        with _patch_verify_scheduler(), \
             _patch_trading_day(True), \
             patch("main.trading_date", return_value=MagicMock(__str__=lambda s: "2026-04-28")), \
             patch("main.read_checkpoint", return_value=None):
            resp = client.post("/refresh/bake", headers=_AUTH_HEADERS)
        assert resp.status_code == 503

    def test_aborts_503_when_fetch_checkpoint_is_stale(self):
        stale_checkpoint = {"trading_date": "2026-01-01", "status": "fetch_ok"}
        with _patch_verify_scheduler(), \
             _patch_trading_day(True), \
             patch("main.trading_date", return_value=MagicMock(__str__=lambda s: "2026-04-28")), \
             patch("main.read_checkpoint", return_value=stale_checkpoint):
            resp = client.post("/refresh/bake", headers=_AUTH_HEADERS)
        assert resp.status_code == 503

    def test_aborts_503_when_fetch_totally_failed(self):
        today = "2026-04-28"
        bad_checkpoint = {"trading_date": today, "status": "fetch_failed"}
        with _patch_verify_scheduler(), \
             _patch_trading_day(True), \
             patch("main.trading_date", return_value=MagicMock(__str__=lambda s: today)), \
             patch("main.read_checkpoint", return_value=bad_checkpoint):
            resp = client.post("/refresh/bake", headers=_AUTH_HEADERS)
        assert resp.status_code == 503

    def test_happy_path_with_valid_checkpoint(self):
        today = "2026-04-28"
        good_checkpoint = {"trading_date": today, "status": "fetch_ok", "stages_failed": []}
        with _patch_verify_scheduler(), \
             _patch_trading_day(True), \
             patch("main.trading_date", return_value=MagicMock(__str__=lambda s: today)), \
             patch("main.read_checkpoint", return_value=good_checkpoint), \
             patch("main.compute_returns", new_callable=AsyncMock, return_value={}), \
             patch("main.get_industry_returns", new_callable=AsyncMock, return_value={}), \
             patch("main.refresh_ai_summary", new_callable=AsyncMock, return_value={"date": today}), \
             patch("main.refresh_daily_blog", new_callable=AsyncMock, return_value={"date": today}), \
             patch("main.refresh_blog_review", new_callable=AsyncMock, return_value={}), \
             patch("main.refresh_correlation_article", new_callable=AsyncMock, return_value={}), \
             patch("main.refresh_story_article", new_callable=AsyncMock, return_value={}), \
             patch("main.write_checkpoint", return_value=None), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            resp = client.post("/refresh/bake", headers=_AUTH_HEADERS)

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "bake_ok"
        assert "stages" in body

    def test_partial_fetch_proceeds_not_aborts(self):
        today = "2026-04-28"
        partial_checkpoint = {"trading_date": today, "status": "fetch_partial", "stages_failed": ["etf_history"]}
        with _patch_verify_scheduler(), \
             _patch_trading_day(True), \
             patch("main.trading_date", return_value=MagicMock(__str__=lambda s: today)), \
             patch("main.read_checkpoint", return_value=partial_checkpoint), \
             patch("main.compute_returns", new_callable=AsyncMock, return_value={}), \
             patch("main.get_industry_returns", new_callable=AsyncMock, return_value={}), \
             patch("main.refresh_ai_summary", new_callable=AsyncMock, return_value={"date": today}), \
             patch("main.refresh_daily_blog", new_callable=AsyncMock, return_value={"date": today}), \
             patch("main.refresh_blog_review", new_callable=AsyncMock, return_value={}), \
             patch("main.refresh_correlation_article", new_callable=AsyncMock, return_value={}), \
             patch("main.refresh_story_article", new_callable=AsyncMock, return_value={}), \
             patch("main.write_checkpoint", return_value=None), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            resp = client.post("/refresh/bake", headers=_AUTH_HEADERS)

        assert resp.status_code == 200

    def test_blog_review_skipped_when_blog_fails(self):
        """B4 (blog_review) must be skipped if B3 (daily_blog) failed."""
        today = "2026-04-28"
        good_checkpoint = {"trading_date": today, "status": "fetch_ok", "stages_failed": []}
        with _patch_verify_scheduler(), \
             _patch_trading_day(True), \
             patch("main.trading_date", return_value=MagicMock(__str__=lambda s: today)), \
             patch("main.read_checkpoint", return_value=good_checkpoint), \
             patch("main.compute_returns", new_callable=AsyncMock, return_value={}), \
             patch("main.get_industry_returns", new_callable=AsyncMock, return_value={}), \
             patch("main.refresh_ai_summary", new_callable=AsyncMock, return_value={"date": today}), \
             patch("main.refresh_daily_blog", new_callable=AsyncMock, side_effect=Exception("Gemini 429")), \
             patch("main.refresh_blog_review", new_callable=AsyncMock, return_value={}) as mock_review, \
             patch("main.refresh_correlation_article", new_callable=AsyncMock, return_value={}), \
             patch("main.refresh_story_article", new_callable=AsyncMock, return_value={}), \
             patch("main.write_checkpoint", return_value=None), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            resp = client.post("/refresh/bake", headers=_AUTH_HEADERS)

        assert resp.status_code == 200
        body = resp.json()
        assert body["stages"]["blog_review"]["status"] == "skipped"
        mock_review.assert_not_called()


# ── /refresh/intraday ─────────────────────────────────────────────────────────

class TestRefreshIntraday:
    """gcp3-midday and EOD intraday refresh."""

    def test_no_auth_returns_401(self):
        resp = client.post("/refresh/intraday")
        assert resp.status_code == 401

    def test_happy_path_returns_refreshed(self):
        with _patch_verify_scheduler(), \
             patch("main.get_morning_brief", new_callable=AsyncMock, return_value={}), \
             patch("main.get_macro_pulse", new_callable=AsyncMock, return_value={}), \
             patch("main.get_news_sentiment", new_callable=AsyncMock, return_value={}), \
             patch("main.get_sector_rotation", new_callable=AsyncMock, return_value={}), \
             patch("main.get_screener_data", new_callable=AsyncMock, return_value={"total_screened": 270}), \
             patch("main._warm_backend2", new_callable=AsyncMock, return_value={"status": "ok"}):
            resp = client.post("/refresh/intraday", headers=_AUTH_HEADERS)

        assert resp.status_code == 200
        assert resp.json()["status"] == "refreshed"

    def test_skip_gemini_flag_passed_through(self):
        """skip_gemini=true should reach get_sector_rotation as force_rule_based=True."""
        captured = {}
        async def mock_sector(force_rule_based=False):
            captured["force_rule_based"] = force_rule_based
            return {}

        with _patch_verify_scheduler(), \
             patch("main.get_morning_brief", new_callable=AsyncMock, return_value={}), \
             patch("main.get_macro_pulse", new_callable=AsyncMock, return_value={}), \
             patch("main.get_news_sentiment", new_callable=AsyncMock, return_value={}), \
             patch("main.get_sector_rotation", side_effect=mock_sector), \
             patch("main.get_screener_data", new_callable=AsyncMock, return_value={}), \
             patch("main._warm_backend2", new_callable=AsyncMock, return_value={"status": "ok"}):
            resp = client.post("/refresh/intraday?skip_gemini=true", headers=_AUTH_HEADERS)

        assert resp.status_code == 200
        assert captured.get("force_rule_based") is True


# ── /refresh/ai-summary (legacy) ──────────────────────────────────────────────

class TestRefreshAiSummaryLegacy:
    """Legacy single-endpoint refresh — kept for backwards compat."""

    def test_no_auth_returns_401(self):
        resp = client.post("/refresh/ai-summary")
        assert resp.status_code == 401

    def test_happy_path_returns_refreshed(self):
        with _patch_verify_scheduler(), \
             patch("main.refresh_ai_summary", new_callable=AsyncMock, return_value={"date": "2026-04-28"}):
            resp = client.post("/refresh/ai-summary", headers=_AUTH_HEADERS)

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "refreshed"
        assert body["date"] == "2026-04-28"

    def test_exception_returns_503(self):
        with _patch_verify_scheduler(), \
             patch("main.refresh_ai_summary", new_callable=AsyncMock, side_effect=Exception("Gemini down")):
            resp = client.post("/refresh/ai-summary", headers=_AUTH_HEADERS)
        assert resp.status_code == 503


# ── /admin/purge-cache ────────────────────────────────────────────────────────

class TestAdminPurgeCache:
    """gcp3-nightly-cache-purge: 2:00 AM ET safety-net deletion of expired docs."""

    def test_no_auth_returns_401(self):
        resp = client.post("/admin/purge-cache")
        assert resp.status_code == 401

    def test_happy_path_returns_deleted_count(self):
        mock_db = MagicMock()
        mock_db.return_value = mock_db
        mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = []
        mock_db.batch.return_value = MagicMock()

        with _patch_verify_scheduler(), \
             patch("main.firestore_db", return_value=mock_db):
            resp = client.post("/admin/purge-cache", headers=_AUTH_HEADERS)

        assert resp.status_code == 200
        body = resp.json()
        assert "deleted" in body
        assert "timestamp" in body
        assert isinstance(body["deleted"], int)

    def test_firestore_error_inside_try_returns_503(self):
        """Firestore failure inside the deletion loop → 503 (caught by the try/except)."""
        mock_db = MagicMock()
        # batch() outside the try must succeed; collection() inside the try raises
        mock_db.batch.return_value = MagicMock()
        mock_db.collection.side_effect = Exception("Firestore unavailable")

        with _patch_verify_scheduler(), \
             patch("main.firestore_db", return_value=mock_db):
            resp = client.post("/admin/purge-cache", headers=_AUTH_HEADERS)
        assert resp.status_code == 503


# ── /admin/refresh-industry-cache ─────────────────────────────────────────────

class TestAdminRefreshIndustryCache:
    """On-demand force-rebuild of industry_data cache."""

    def test_no_auth_returns_401(self):
        resp = client.post("/admin/refresh-industry-cache")
        assert resp.status_code == 401

    def test_happy_path_returns_industry_count(self):
        fake_result = {"rankings": [{"etf": "XLK"}, {"etf": "XLF"}], "date": "2026-04-28"}
        with _patch_verify_scheduler(), \
             patch("main.get_industry_data", new_callable=AsyncMock, return_value=fake_result):
            resp = client.post("/admin/refresh-industry-cache", headers=_AUTH_HEADERS)

        assert resp.status_code == 200
        body = resp.json()
        assert body["industries"] == 2

    def test_exception_returns_503(self):
        with _patch_verify_scheduler(), \
             patch("main.get_industry_data", new_callable=AsyncMock, side_effect=Exception("Finnhub timeout")):
            resp = client.post("/admin/refresh-industry-cache", headers=_AUTH_HEADERS)
        assert resp.status_code == 503


# ── /admin/compute-returns ────────────────────────────────────────────────────

class TestAdminComputeReturns:
    """Zero-API-cost multi-period return pre-computation."""

    def test_no_auth_returns_401(self):
        resp = client.post("/admin/compute-returns")
        assert resp.status_code == 401

    def test_happy_path_returns_200(self):
        with _patch_verify_scheduler(), \
             patch("main.compute_returns", new_callable=AsyncMock, return_value={"updated": 50}):
            resp = client.post("/admin/compute-returns", headers=_AUTH_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["updated"] == 50

    def test_exception_returns_503(self):
        with _patch_verify_scheduler(), \
             patch("main.compute_returns", new_callable=AsyncMock, side_effect=Exception("store unavailable")):
            resp = client.post("/admin/compute-returns", headers=_AUTH_HEADERS)
        assert resp.status_code == 503


# ── /admin/seed-etf-history ───────────────────────────────────────────────────

class TestAdminSeedEtfHistory:
    """Delta-append ETF history seed."""

    def test_no_auth_returns_401(self):
        resp = client.post("/admin/seed-etf-history")
        assert resp.status_code == 401

    def test_happy_path_returns_etf_count_and_rows(self):
        fake_results = {"SPY": 252, "QQQ": 250, "XLK": 248}
        with _patch_verify_scheduler(), \
             patch("main.seed_etf_history", new_callable=AsyncMock, return_value=fake_results):
            resp = client.post("/admin/seed-etf-history", headers=_AUTH_HEADERS)

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["etfs"] == 3
        assert body["total_rows"] == 750

    def test_exception_returns_503(self):
        with _patch_verify_scheduler(), \
             patch("main.seed_etf_history", new_callable=AsyncMock, side_effect=Exception("yfinance rate limited")):
            resp = client.post("/admin/seed-etf-history", headers=_AUTH_HEADERS)
        assert resp.status_code == 503
