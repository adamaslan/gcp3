"""Pytest configuration for GCP3 backend tests.

Stubs out GCP/Firestore credentials so tests run without cloud access.
"""
import os
import sys

# Ensure backend/ is on path for all test modules
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Provide minimal env vars required at import time by main.py / firestore.py
os.environ.setdefault("GCP_PROJECT_ID", "test-project")
os.environ.setdefault("SCHEDULER_EXPECTED_AUDIENCE", "https://test.run.app")
os.environ.setdefault("SCHEDULER_EXPECTED_SA", "test-sa@test.iam.gserviceaccount.com")
os.environ.setdefault("FINNHUB_API_KEY", "test-key")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
