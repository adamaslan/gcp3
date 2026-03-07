"""Shared Finnhub HTTP helper.

- Passes API key via X-Finnhub-Token header (never in URL query params)
- Strips the key from any exception messages before they propagate
"""
import os
import re

import httpx

_KEY_PATTERN = re.compile(r"token=[^&\s]+")
_FINNHUB_BASE = "https://finnhub.io/api/v1"


def _sanitize(msg: str) -> str:
    """Remove any token=... from error strings."""
    return _KEY_PATTERN.sub("token=<redacted>", msg)


def _headers() -> dict[str, str]:
    return {"X-Finnhub-Token": os.environ["FINNHUB_API_KEY"]}


async def get(client: httpx.AsyncClient, path: str, params: dict | None = None) -> dict:
    """GET a Finnhub endpoint. Raises httpx.HTTPStatusError on bad status.

    The API key is always sent via header, never in the URL.
    Any exception message containing the key is sanitized before re-raising.
    """
    try:
        r = await client.get(
            f"{_FINNHUB_BASE}{path}",
            params=params,
            headers=_headers(),
        )
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as exc:
        raise httpx.HTTPStatusError(
            _sanitize(str(exc)),
            request=exc.request,
            response=exc.response,
        ) from None
    except Exception as exc:
        raise type(exc)(_sanitize(str(exc))) from None
