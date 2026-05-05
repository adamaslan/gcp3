"""Growth fundamentals adapter with yfinance-backed fallback data."""
from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from typing import Any

from schemas.fundamentals import (
    BalanceSheetSnapshot,
    CashFlowSnapshot,
    FundamentalsToolResult,
    IncomeStatementSnapshot,
)


class FundamentalsAdapter:
    def __init__(self, config: Any | None = None) -> None:
        self.config = config

    async def fetch(self, ticker: str, run_id: str, force_refresh: bool = False) -> FundamentalsToolResult:
        inputs_hash = hashlib.sha256(f"{ticker}:{run_id}:{force_refresh}".encode()).hexdigest()[:16]
        try:
            data = await asyncio.to_thread(self._fetch_yfinance, ticker)
            missing = self._missing_fields(data)
            return FundamentalsToolResult(
                tool_name="fundamentals",
                tool_family="fundamental",
                inputs_hash=inputs_hash,
                timeframe="annual",
                status="partial" if missing else "ok",
                score_delta=0.0,
                evidence=[f"Fetched normalized fundamentals for {ticker}"],
                risk_flags=[f"missing_{m}" for m in missing],
                source_timestamps={"yfinance": datetime.now(timezone.utc)},
                provider="yfinance",
                missing_key_fields=missing,
                **data,
            )
        except Exception as exc:
            return FundamentalsToolResult(
                tool_name="fundamentals",
                tool_family="fundamental",
                inputs_hash=inputs_hash,
                timeframe="annual",
                status="failed",
                risk_flags=["fundamentals_failed"],
                counter_evidence=[str(exc)[:240]],
                provider="yfinance",
            )

    def _fetch_yfinance(self, ticker: str) -> dict[str, Any]:
        import yfinance as yf

        t = yf.Ticker(ticker)
        financials = t.financials
        balance_sheet = t.balance_sheet
        cashflow = t.cashflow
        income: list[IncomeStatementSnapshot] = []
        balances: list[BalanceSheetSnapshot] = []
        cashflows: list[CashFlowSnapshot] = []

        years = list(financials.columns[:5]) if hasattr(financials, "columns") else []
        for col in reversed(years):
            year = int(getattr(col, "year", datetime.now().year))
            income.append(IncomeStatementSnapshot(
                fiscal_year=year,
                revenue=self._cell(financials, "Total Revenue", col),
                net_income=self._cell(financials, "Net Income", col),
                ebit=self._cell(financials, "EBIT", col),
                ebitda=self._cell(financials, "EBITDA", col),
                interest_expense=self._cell(financials, "Interest Expense", col),
                gross_profit=self._cell(financials, "Gross Profit", col),
                operating_income=self._cell(financials, "Operating Income", col),
                weighted_average_shares=self._cell(financials, "Diluted Average Shares", col),
            ))
            balances.append(BalanceSheetSnapshot(
                fiscal_year=year,
                total_assets=self._cell(balance_sheet, "Total Assets", col),
                total_debt=self._cell(balance_sheet, "Total Debt", col),
                cash_and_equivalents=self._cell(balance_sheet, "Cash And Cash Equivalents", col),
                total_equity=self._cell(balance_sheet, "Stockholders Equity", col),
                current_assets=self._cell(balance_sheet, "Current Assets", col),
                current_liabilities=self._cell(balance_sheet, "Current Liabilities", col),
            ))
            ocf = self._cell(cashflow, "Operating Cash Flow", col)
            capex = self._cell(cashflow, "Capital Expenditure", col)
            cashflows.append(CashFlowSnapshot(
                fiscal_year=year,
                operating_cash_flow=ocf,
                capital_expenditure=capex,
                free_cash_flow=(ocf + capex) if ocf is not None and capex is not None else self._cell(cashflow, "Free Cash Flow", col),
                dividends_paid=self._cell(cashflow, "Cash Dividends Paid", col),
                stock_based_compensation=self._cell(cashflow, "Stock Based Compensation", col),
            ))
        return {
            "income_statements": income,
            "balance_sheets": balances,
            "cash_flows": cashflows,
            "quarterly_revenue": [],
            "insider_cluster_selling_detected": False,
            "going_concern_doubt": False,
        }

    @staticmethod
    def _cell(frame: Any, row: str, col: Any) -> float | None:
        try:
            value = frame.loc[row, col]
            if value != value:
                return None
            return float(value)
        except (KeyError, AttributeError, TypeError, ValueError):
            return None

    @staticmethod
    def _missing_fields(data: dict[str, Any]) -> list[str]:
        missing: list[str] = []
        income = data.get("income_statements") or []
        balances = data.get("balance_sheets") or []
        cashflows = data.get("cash_flows") or []
        if len(income) < 5:
            missing.append("five_year_income_history")
        if not income or income[-1].revenue is None:
            missing.append("revenue")
        if not income or income[-1].net_income is None:
            missing.append("net_income")
        if not balances or balances[-1].total_debt is None:
            missing.append("total_debt")
        if not cashflows or cashflows[-1].free_cash_flow is None:
            missing.append("free_cash_flow")
        return missing
