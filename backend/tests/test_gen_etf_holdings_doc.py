"""Unit tests for gen_etf_holdings_doc module."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

from gen_etf_holdings_doc import (
    fetch_top_holdings,
    fetch_all_holdings,
    Holding,
    holdings_to_csv_row,
)


@pytest.fixture
def mock_client():
    """Fixture for mocked AsyncClient."""
    return AsyncMock(spec=httpx.AsyncClient)


@pytest.mark.asyncio
async def test_fetch_top_holdings_success(mock_client):
    """Test successful fetch of holdings."""
    ticker = "IGV"
    response_data = {
        "quoteSummary": {
            "result": [
                {
                    "topHoldings": {
                        "holdings": [
                            {
                                "symbol": "MSFT",
                                "holdingName": "Microsoft Corp",
                                "holdingPercent": {"raw": 0.0823},
                            },
                            {
                                "symbol": "ORCL",
                                "holdingName": "Oracle Corp",
                                "holdingPercent": {"raw": 0.0712},
                            },
                        ]
                    }
                }
            ]
        }
    }

    mock_response = MagicMock()
    mock_response.json.return_value = response_data
    mock_client.get = AsyncMock(return_value=mock_response)

    holdings = await fetch_top_holdings(mock_client, ticker, limit=4)

    assert len(holdings) == 2
    assert holdings[0].etf == "IGV"
    assert holdings[0].symbol == "MSFT"
    assert holdings[0].name == "Microsoft Corp"
    assert holdings[0].weight == 0.0823

    mock_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_top_holdings_limit(mock_client):
    """Test limit parameter is respected."""
    ticker = "SOXX"
    response_data = {
        "quoteSummary": {
            "result": [
                {
                    "topHoldings": {
                        "holdings": [
                            {
                                "symbol": f"TICK{i}",
                                "holdingName": f"Company {i}",
                                "holdingPercent": {"raw": 0.05},
                            }
                            for i in range(10)
                        ]
                    }
                }
            ]
        }
    }

    mock_response = MagicMock()
    mock_response.json.return_value = response_data
    mock_client.get = AsyncMock(return_value=mock_response)

    holdings = await fetch_top_holdings(mock_client, ticker, limit=4)

    assert len(holdings) == 4
    assert holdings[0].symbol == "TICK0"
    assert holdings[3].symbol == "TICK3"


@pytest.mark.asyncio
async def test_fetch_top_holdings_empty_result(mock_client):
    """Test handling of empty quoteSummary result."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"quoteSummary": {"result": None}}
    mock_client.get = AsyncMock(return_value=mock_response)

    holdings = await fetch_top_holdings(mock_client, "INVALID", limit=4)

    assert holdings == []


@pytest.mark.asyncio
async def test_fetch_top_holdings_http_error(mock_client):
    """Test handling of HTTP errors."""
    mock_client.get.side_effect = httpx.HTTPError("Connection failed")

    holdings = await fetch_top_holdings(mock_client, "BROKEN", limit=4)

    assert holdings == []


@pytest.mark.asyncio
async def test_fetch_top_holdings_malformed_json(mock_client):
    """Test handling of malformed JSON responses."""
    mock_response = AsyncMock()
    mock_response.json.side_effect = json.JSONDecodeError("msg", "doc", 0)
    mock_client.get.return_value = mock_response

    holdings = await fetch_top_holdings(mock_client, "BAD", limit=4)

    assert holdings == []


@pytest.mark.asyncio
async def test_fetch_top_holdings_missing_weight(mock_client):
    """Test handling of missing weight field (defaults to 0.0)."""
    response_data = {
        "quoteSummary": {
            "result": [
                {
                    "topHoldings": {
                        "holdings": [
                            {
                                "symbol": "TEST",
                                "holdingName": "Test Corp",
                                "holdingPercent": {},  # missing raw
                            }
                        ]
                    }
                }
            ]
        }
    }

    mock_response = MagicMock()
    mock_response.json.return_value = response_data
    mock_client.get = AsyncMock(return_value=mock_response)

    holdings = await fetch_top_holdings(mock_client, "TST", limit=4)

    assert len(holdings) == 1
    assert holdings[0].weight == 0.0


@pytest.mark.asyncio
async def test_fetch_all_holdings_concurrency(mock_client):
    """Test fetch_all_holdings with concurrency control."""
    tickers = ["IGV", "SOXX", "CLOU"]

    # Mock consistent responses for all tickers
    def make_response(ticker):
        response = AsyncMock()
        response.json.return_value = {
            "quoteSummary": {
                "result": [
                    {
                        "topHoldings": {
                            "holdings": [
                                {
                                    "symbol": "TICK1",
                                    "holdingName": "Holding 1",
                                    "holdingPercent": {"raw": 0.05},
                                }
                            ]
                        }
                    }
                ]
            }
        }
        return response

    async def mock_get(*args, **kwargs):
        return make_response(None)

    with patch("gen_etf_holdings_doc.httpx.AsyncClient") as mock_client_class:
        mock_instance = AsyncMock()
        mock_instance.get.side_effect = mock_get
        mock_instance.__aenter__.return_value = mock_instance
        mock_client_class.return_value = mock_instance

        results = await fetch_all_holdings(tickers, limit=4, concurrency=2)

    assert len(results) == 3
    assert all(ticker in results for ticker in tickers)


@pytest.mark.asyncio
async def test_fetch_all_holdings_rate_limit(mock_client):
    """Test concurrency cap (max 20)."""
    tickers = ["T1", "T2"]

    async def mock_get(*args, **kwargs):
        response = AsyncMock()
        response.json.return_value = {
            "quoteSummary": {
                "result": [
                    {
                        "topHoldings": {
                            "holdings": [
                                {
                                    "symbol": "TICK",
                                    "holdingName": "Holding",
                                    "holdingPercent": {"raw": 0.05},
                                }
                            ]
                        }
                    }
                ]
            }
        }
        return response

    with patch("gen_etf_holdings_doc.httpx.AsyncClient") as mock_client_class:
        mock_instance = AsyncMock()
        mock_instance.get.side_effect = mock_get
        mock_instance.__aenter__.return_value = mock_instance
        mock_client_class.return_value = mock_instance

        # Request concurrency > 20 should be capped
        results = await fetch_all_holdings(tickers, limit=4, concurrency=100)

    assert len(results) == 2


def test_holdings_to_csv_row():
    """Test conversion of Holding to CSV row dict."""
    holding = Holding(etf="IGV", symbol="MSFT", name="Microsoft", weight=0.0823)
    row = holdings_to_csv_row(holding)

    assert row == {
        "etf": "IGV",
        "symbol": "MSFT",
        "name": "Microsoft",
        "weight": "0.0823",
    }


def test_holdings_to_csv_row_zero_weight():
    """Test CSV row with zero weight."""
    holding = Holding(etf="IGV", symbol="TEST", name="Test", weight=0.0)
    row = holdings_to_csv_row(holding)

    assert row["weight"] == "0.0000"
