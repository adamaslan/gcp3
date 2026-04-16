"""Tests for _verify_scheduler() auth — ensures bad tokens are rejected."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from unittest.mock import patch, MagicMock
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


# Import after sys.path is set
import main as app_module


class TestVerifySchedulerSecretFallback:
    """Test the SCHEDULER_SECRET fallback path (no Bearer token)."""

    def _make_request(self, headers: dict) -> MagicMock:
        req = MagicMock()
        req.headers = headers
        return req

    def test_correct_secret_passes(self):
        req = self._make_request({"X-Scheduler-Token": "test-secret-123"})
        with patch.dict(os.environ, {"SCHEDULER_SECRET": "test-secret-123"}):
            # Should not raise
            app_module._verify_scheduler(req)

    def test_wrong_secret_raises_401(self):
        req = self._make_request({"X-Scheduler-Token": "wrong-token"})
        with patch.dict(os.environ, {"SCHEDULER_SECRET": "correct-secret"}):
            with pytest.raises(HTTPException) as exc_info:
                app_module._verify_scheduler(req)
            assert exc_info.value.status_code == 401

    def test_missing_token_raises_401(self):
        req = self._make_request({})
        with patch.dict(os.environ, {"SCHEDULER_SECRET": "some-secret"}):
            with pytest.raises(HTTPException) as exc_info:
                app_module._verify_scheduler(req)
            assert exc_info.value.status_code == 401

    def test_empty_token_raises_401(self):
        req = self._make_request({"X-Scheduler-Token": ""})
        with patch.dict(os.environ, {"SCHEDULER_SECRET": "some-secret"}):
            with pytest.raises(HTTPException) as exc_info:
                app_module._verify_scheduler(req)
            assert exc_info.value.status_code == 401

    def test_no_secret_configured_raises_401(self):
        # SCHEDULER_SECRET not set in env → any token fails
        req = self._make_request({"X-Scheduler-Token": "anything"})
        env_without_secret = {k: v for k, v in os.environ.items() if k != "SCHEDULER_SECRET"}
        with patch.dict(os.environ, env_without_secret, clear=True):
            with pytest.raises(HTTPException) as exc_info:
                app_module._verify_scheduler(req)
            assert exc_info.value.status_code == 401

    def test_detail_is_unauthorized_not_descriptive(self):
        # Error detail must not leak internal info (just "Unauthorized")
        req = self._make_request({"X-Scheduler-Token": "bad"})
        with patch.dict(os.environ, {"SCHEDULER_SECRET": "good"}):
            with pytest.raises(HTTPException) as exc_info:
                app_module._verify_scheduler(req)
            assert exc_info.value.detail == "Unauthorized"


class TestVerifySchedulerBearerPath:
    """Test the OIDC Bearer token path."""

    def _make_request(self, headers: dict) -> MagicMock:
        req = MagicMock()
        req.headers = headers
        return req

    def test_valid_oidc_token_with_matching_email_passes(self):
        req = self._make_request({"Authorization": "Bearer valid.jwt.token"})
        mock_claims = {"email": "gcp3-scheduler@ttb-lang1.iam.gserviceaccount.com"}
        with patch("main.google_id_token.verify_oauth2_token", return_value=mock_claims), \
             patch.dict(os.environ, {
                 "SCHEDULER_EXPECTED_AUDIENCE": "https://example.run.app",
                 "SCHEDULER_EXPECTED_SA": "gcp3-scheduler@ttb-lang1.iam.gserviceaccount.com",
             }):
            app_module._EXPECTED_AUDIENCE = "https://example.run.app"
            app_module._EXPECTED_SA = "gcp3-scheduler@ttb-lang1.iam.gserviceaccount.com"
            app_module._verify_scheduler(req)  # Should not raise

    def test_valid_token_wrong_email_raises_401(self):
        req = self._make_request({"Authorization": "Bearer valid.jwt.token"})
        mock_claims = {"email": "attacker@evil.com"}
        with patch("main.google_id_token.verify_oauth2_token", return_value=mock_claims):
            app_module._EXPECTED_SA = "gcp3-scheduler@ttb-lang1.iam.gserviceaccount.com"
            with pytest.raises(HTTPException) as exc_info:
                app_module._verify_scheduler(req)
            assert exc_info.value.status_code == 401

    def test_invalid_oidc_token_raises_401(self):
        req = self._make_request({"Authorization": "Bearer garbage.token.here"})
        with patch("main.google_id_token.verify_oauth2_token", side_effect=Exception("invalid token")):
            with pytest.raises(HTTPException) as exc_info:
                app_module._verify_scheduler(req)
            assert exc_info.value.status_code == 401
