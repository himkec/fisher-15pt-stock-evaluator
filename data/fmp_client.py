"""
Financial data client — backed by yfinance (Yahoo Finance).
Free, no API key required. Maintains the same interface as the original
FMP client so no other files need to change.
"""

import time
import yfinance as yf
import pandas as pd
from typing import Any

from config.settings import CACHE_TTL_SECONDS, SECTOR_FALLBACK_GROSS_MARGINS
from data import cache


class FMPRateLimitError(Exception):
    pass


class FMPError(Exception):
    pass


def _get_ticker(ticker: str) -> yf.Ticker:
    return yf.Ticker(ticker)


def _safe_val(val: Any, default=0) -> Any:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    return val


def _df_to_annual_list(df: pd.DataFrame, field_map: dict, limit: int = 5) -> list[dict]:
    """
    Convert a yfinance financial DataFrame (columns = dates, rows = fields)
    to a list of dicts (newest first), mapped to FMP-compatible field names.
    """
    if df is None or df.empty:
        return []

    results = []
    for col in list(df.columns)[:limit]:
        row = {"date": str(col.date()) if hasattr(col, "date") else str(col)}
        for yf_field, fmp_field in field_map.items():
            try:
                val = df.loc[yf_field, col] if yf_field in df.index else None
                row[fmp_field] = _safe_val(val)
            except Exception:
                row[fmp_field] = 0
        results.append(row)
    return results


# ── Public interface (mirrors original fmp_client) ────────────────────────────

def get_profile(ticker: str) -> dict:
    """Company profile: name, sector, industry, description."""
    cached = cache.get("yf:profile", ticker)
    if cached:
        return cached

    t = _get_ticker(ticker)
    info = t.info
    if not info or info.get("trailingPegRatio") is None and info.get("symbol") is None:
        # yfinance returns a minimal dict for unknown tickers
        if "shortName" not in info and "longName" not in info:
            raise FMPError(f"No data found for ticker '{ticker}'. Check the symbol.")

    profile = {
        "symbol": ticker,
        "companyName": info.get("longName") or info.get("shortName", ticker),
        "sector": info.get("sector", "default"),
        "industry": info.get("industry", ""),
        "description": info.get("longBusinessSummary", ""),
        "fullTimeEmployees": _safe_val(info.get("fullTimeEmployees"), 0),
        "country": info.get("country", ""),
        "exchange": info.get("exchange", ""),
    }
    cache.set("yf:profile", ticker, profile, ttl=CACHE_TTL_SECONDS)
    cache.log_request("fmp", "profile", ticker)
    return profile


def get_income_statements(ticker: str, limit: int = 5) -> list[dict]:
    cached = cache.get("yf:income_stmt", ticker)
    if cached:
        return cached

    t = _get_ticker(ticker)
    df = t.financials  # annual income statement, columns = dates newest first

    field_map = {
        "Total Revenue":                          "revenue",
        "Gross Profit":                           "grossProfit",
        "Operating Income":                       "operatingIncome",
        "Selling General Administrative":         "sellingGeneralAndAdministrativeExpenses",
        "Research And Development":               "researchAndDevelopmentExpenses",
        "Net Income":                             "netIncome",
        "EBIT":                                   "ebit",
    }
    result = _df_to_annual_list(df, field_map, limit)
    cache.set("yf:income_stmt", ticker, result, ttl=CACHE_TTL_SECONDS)
    cache.log_request("fmp", "income-statement", ticker)
    return result


def get_balance_sheets(ticker: str, limit: int = 5) -> list[dict]:
    cached = cache.get("yf:balance_sheet", ticker)
    if cached:
        return cached

    t = _get_ticker(ticker)
    df = t.balance_sheet

    field_map = {
        "Total Assets":                    "totalAssets",
        "Total Liabilities Net Minority Interest": "totalLiabilities",
        "Stockholders Equity":             "totalStockholdersEquity",
        "Common Stock":                    "commonStock",
        "Ordinary Shares Number":          "commonStockSharesOutstanding",
        "Total Debt":                      "totalDebt",
        "Cash And Cash Equivalents":       "cashAndCashEquivalents",
    }
    result = _df_to_annual_list(df, field_map, limit)
    cache.set("yf:balance_sheet", ticker, result, ttl=CACHE_TTL_SECONDS)
    cache.log_request("fmp", "balance-sheet-statement", ticker)
    return result


def get_cash_flow_statements(ticker: str, limit: int = 5) -> list[dict]:
    cached = cache.get("yf:cash_flow", ticker)
    if cached:
        return cached

    t = _get_ticker(ticker)
    df = t.cashflow

    field_map = {
        "Operating Cash Flow":             "operatingCashFlow",
        "Capital Expenditure":             "capitalExpenditure",
        "Free Cash Flow":                  "freeCashFlow",
        "Issuance Of Capital Stock":       "commonStockIssued",
        "Repurchase Of Capital Stock":     "commonStockRepurchased",
    }
    result = _df_to_annual_list(df, field_map, limit)
    cache.set("yf:cash_flow", ticker, result, ttl=CACHE_TTL_SECONDS)
    cache.log_request("fmp", "cash-flow-statement", ticker)
    return result


def get_ratios(ticker: str, limit: int = 5) -> list[dict]:
    """Calculate margins from income statement data."""
    cached = cache.get("yf:ratios", ticker)
    if cached:
        return cached

    income = get_income_statements(ticker, limit)
    ratios = []
    for stmt in income:
        rev = stmt.get("revenue", 0) or 0
        gross = stmt.get("grossProfit", 0) or 0
        op_income = stmt.get("operatingIncome", 0) or 0
        net_income = stmt.get("netIncome", 0) or 0
        ratios.append({
            "date": stmt.get("date", ""),
            "grossProfitMargin":    gross / rev if rev else 0,
            "operatingProfitMargin": op_income / rev if rev else 0,
            "netProfitMargin":      net_income / rev if rev else 0,
        })

    cache.set("yf:ratios", ticker, ratios, ttl=CACHE_TTL_SECONDS)
    return ratios


def get_key_metrics(ticker: str, limit: int = 5) -> list[dict]:
    """Revenue per employee, capex per share, etc."""
    cached = cache.get("yf:key_metrics", ticker)
    if cached:
        return cached

    profile = get_profile(ticker)
    employees = profile.get("fullTimeEmployees", 0) or 0
    income = get_income_statements(ticker, limit)
    cash_flows = get_cash_flow_statements(ticker, limit)

    # Get shares outstanding from yfinance info for capex/share
    t = _get_ticker(ticker)
    info = t.info
    shares = _safe_val(info.get("sharesOutstanding"), 0)

    metrics = []
    for i, stmt in enumerate(income):
        rev = stmt.get("revenue", 0) or 0
        capex = abs(cash_flows[i].get("capitalExpenditure", 0) or 0) if i < len(cash_flows) else 0
        metrics.append({
            "date": stmt.get("date", ""),
            "revenuePerEmployee": rev / employees if employees > 0 else 0,
            "capexPerShare":      capex / shares if shares > 0 else 0,
        })

    cache.set("yf:key_metrics", ticker, metrics, ttl=CACHE_TTL_SECONDS)
    cache.log_request("fmp", "key-metrics", ticker)
    return metrics


def get_peers(ticker: str) -> list[str]:
    """yfinance doesn't have a peers endpoint — return empty (sector fallback used)."""
    return []


def get_peers_ratios(ticker: str) -> list[dict]:
    """No peer data from yfinance free tier — scoring falls back to sector medians."""
    return []


def request_count_today() -> int:
    """Proxy to cache counter — kept for sidebar display compatibility."""
    from data.cache import request_count_today as _count
    return _count("fmp")
