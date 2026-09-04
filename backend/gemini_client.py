"""DEPRECATED — moved to llm/legacy_client.py (call_gemini renamed call_llm).

Kept as a one-release compat alias per Phase 2 of
docs/openrouter-migration-and-db-parity-plan.md (nuwrrrld-portal). Every
in-repo importer has already been updated to `from llm.legacy_client import
call_llm`; this file exists only for any external caller that hasn't. Delete
in the next release.
"""
from llm.legacy_client import call_llm as call_gemini  # noqa: F401
