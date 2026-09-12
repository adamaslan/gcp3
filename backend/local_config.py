"""Configuration loader for local runs — merges keys from homebase and backend .env files."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load from both .env files
_HOMEBASE_ENV = Path.home() / "code" / "homebase" / ".env"
_BACKEND_ENV = Path(__file__).parent / ".env"

# load_dotenv() defaults to override=False, so it never touches a key
# already in os.environ — meaning whichever load call runs FIRST wins
# between the two files (a pre-existing process env var always wins over
# both, regardless of order). "Backend keys take precedence" therefore
# requires loading the backend file first, then homebase to fill gaps.
if _BACKEND_ENV.exists():
    load_dotenv(_BACKEND_ENV, verbose=False)
if _HOMEBASE_ENV.exists():
    load_dotenv(_HOMEBASE_ENV, verbose=False)


def get_config() -> dict:
    """Get all configured API keys and settings.

    Returns a dict with keys from both .env files. Backend keys take precedence.
    """
    return {
        # LLM keys
        "mistral_key": os.getenv("MISTRAL_KEY"),
        "openrouter_key": os.getenv("OPENROUTER_API_KEY") or os.getenv("OPEN_ROUTER_KEY2"),

        # Market data
        "finnhub_key": os.getenv("FINNHUB_API_KEY2"),
        "finnhub_webhook_secret": os.getenv("FINNHUB_WEBHOOK_SECRET"),

        # Firebase / GCP
        "gcp_project_id": os.getenv("GCP_PROJECT_ID", "nuwrrrld-prod"),
        "gcp_credentials_path": os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),

        # Other services
        "cloudflare_key": os.getenv("CLOUDFLARE_API_KEY_NU1"),
        "eleven_labs_key": os.getenv("ELEVEN_LABS_API_KEY"),
        "together_api_key": os.getenv("TOGETHER_API_KEY1"),
    }


def validate_config() -> tuple[bool, list[str]]:
    """Validate that required keys are present.

    Returns:
        (is_valid, list_of_missing_keys)
    """
    config = get_config()
    required = ["mistral_key", "openrouter_key", "finnhub_key", "gcp_project_id"]
    missing = [k for k in required if not config.get(k)]
    return len(missing) == 0, missing


if __name__ == "__main__":
    config = get_config()
    valid, missing = validate_config()

    print("Configuration loaded:")
    print("-" * 60)
    for key, val in config.items():
        # Never print secret values or prefixes here — this script's stdout
        # gets pasted into chats, logs, and CI output. "configured" is all
        # this diagnostic needs to say.
        status = "✓ configured" if val else "✗ (not set)"
        print(f"  {key:30s} {status}")
    print("-" * 60)
    if valid:
        print("✅ All required keys configured")
    else:
        print(f"❌ Missing keys: {', '.join(missing)}")
