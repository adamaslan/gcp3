"""Fundamental statement schemas for Growth scoring."""
from __future__ import annotations

from pydantic import BaseModel, Field

from schemas.tool_result import ToolResult


class IncomeStatementSnapshot(BaseModel):
    fiscal_year: int
    revenue: float | None = None
    net_income: float | None = None
    ebit: float | None = None
    ebitda: float | None = None
    interest_expense: float | None = None
    gross_profit: float | None = None
    operating_income: float | None = None
    weighted_average_shares: float | None = None


class BalanceSheetSnapshot(BaseModel):
    fiscal_year: int
    total_assets: float | None = None
    total_debt: float | None = None
    cash_and_equivalents: float | None = None
    total_equity: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None


class CashFlowSnapshot(BaseModel):
    fiscal_year: int
    operating_cash_flow: float | None = None
    capital_expenditure: float | None = None
    free_cash_flow: float | None = None
    dividends_paid: float | None = None
    stock_based_compensation: float | None = None


class FundamentalsToolResult(ToolResult):
    income_statements: list[IncomeStatementSnapshot] = Field(default_factory=list)
    balance_sheets: list[BalanceSheetSnapshot] = Field(default_factory=list)
    cash_flows: list[CashFlowSnapshot] = Field(default_factory=list)
    quarterly_revenue: list[float] = Field(default_factory=list)
    insider_cluster_selling_detected: bool = False
    going_concern_doubt: bool = False
    missing_key_fields: list[str] = Field(default_factory=list)
    provider: str | None = None

