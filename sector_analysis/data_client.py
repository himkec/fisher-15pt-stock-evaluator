"""
Epic 2 — Market data ingestion via yfinance.

All public functions are cached in the existing SQLite cache:
  key "sector:sp500"             → S&P 500 constituent list (7 day TTL)
  key "sector:etf_prices:{Y}y"   → sector ETF price history  (24 h TTL)
  key "sector:stock_prices:..."  → subsector stock prices     (24 h TTL)
  key "sector:fundamentals:TICK" → single-stock fundamentals  (24 h TTL)

Uses "SECTOR_ANALYSIS" as the pseudo-ticker for non-stock cache entries.
"""

import time
import requests
import pandas as pd
import yfinance as yf
from io import StringIO
from typing import Any

from data import cache

_PSEUDO = "SECTOR_ANALYSIS"
_TTL_SP500      = 60 * 60 * 24 * 7    # 7 days
_TTL_PRICES     = 60 * 60 * 24        # 24 h
_TTL_FUND       = 60 * 60 * 24        # 24 h


# ── S&P 500 universe (Epic 5 / Story 5.1) ────────────────────────────────────

def get_sp500_universe() -> pd.DataFrame:
    """
    Return a DataFrame of S&P 500 constituents with GICS classifications.
    Columns: Symbol, Security, GICS Sector, GICS Sub-Industry
    Fetched from Wikipedia; cached for 7 days.
    """
    cached = cache.get("sector:sp500", _PSEUDO)
    if cached:
        return pd.DataFrame(cached)

    try:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        resp = requests.get(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            headers=headers, timeout=15,
        )
        resp.raise_for_status()
        tables = pd.read_html(StringIO(resp.text))
        df = tables[0][["Symbol", "Security", "GICS Sector", "GICS Sub-Industry"]].copy()
        df.columns = ["ticker", "name", "sector", "sub_industry"]
        # Fix BRK.B / BF.B ticker dots → yfinance uses dashes
        df["ticker"] = df["ticker"].str.replace(".", "-", regex=False)
        cache.set("sector:sp500", _PSEUDO, df.to_dict("records"), ttl=_TTL_SP500)
        return df
    except Exception as e:
        raise RuntimeError(f"Failed to fetch S&P 500 universe: {e}") from e


def get_sp500_for_sector(sector_name: str) -> pd.DataFrame:
    """Return S&P 500 stocks in a given GICS sector."""
    df = get_sp500_universe()
    return df[df["sector"] == sector_name].reset_index(drop=True)


def get_sp500_for_subsector(sub_industry: str) -> pd.DataFrame:
    """Return S&P 500 stocks in a given GICS sub-industry."""
    df = get_sp500_universe()
    return df[df["sub_industry"] == sub_industry].reset_index(drop=True)


# ── ETF / sector price history (Epic 2 / Story 2.2, 2.3) ─────────────────────

def get_etf_prices(tickers: list[str], years: int) -> pd.DataFrame:
    """
    Download adjusted-close price history for the given ETFs.
    Returns a DataFrame with dates as index, tickers as columns.
    Cached per (years) value.
    """
    key = f"sector:etf_prices:{years}y"
    cached = cache.get(key, _PSEUDO)
    if cached:
        df = pd.DataFrame.from_dict(cached, orient="index")
        df.index = pd.to_datetime(df.index)
        return df

    period = f"{years + 1}y"   # fetch a bit extra to cover the full lookback
    raw = yf.download(
        " ".join(tickers),
        period=period,
        auto_adjust=True,
        progress=False,
        threads=True,
    )
    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw["Close"]
    else:
        prices = raw[["Close"]] if "Close" in raw.columns else raw

    prices = prices.dropna(how="all")
    serialisable = prices.to_dict("index")
    # Convert Timestamp keys to str for JSON
    serialisable = {str(k): v for k, v in serialisable.items()}
    cache.set(key, _PSEUDO, serialisable, ttl=_TTL_PRICES)
    return prices


# ── Stock price history for subsector ranking (Epic 4) ───────────────────────

def get_stock_prices(tickers: list[str], years: int) -> pd.DataFrame:
    """
    Download adjusted-close price history for a list of stock tickers.
    Returns a DataFrame (dates × tickers).  Columns that fail are dropped.
    """
    if not tickers:
        return pd.DataFrame()

    key = f"sector:stock_prices:{years}y:{'_'.join(sorted(tickers)[:8])}"
    cached = cache.get(key, _PSEUDO)
    if cached:
        df = pd.DataFrame.from_dict(cached, orient="index")
        df.index = pd.to_datetime(df.index)
        return df

    period = f"{years + 1}y"
    try:
        raw = yf.download(
            tickers if len(tickers) > 1 else tickers[0],
            period=period,
            auto_adjust=True,
            progress=False,
            threads=True,
        )
        if isinstance(raw.columns, pd.MultiIndex):
            prices = raw["Close"]
        else:
            prices = raw.rename(columns={"Close": tickers[0]}) if len(tickers) == 1 else raw
        prices = prices.dropna(how="all")
    except Exception:
        return pd.DataFrame()

    serialisable = {str(k): v for k, v in prices.to_dict("index").items()}
    cache.set(key, _PSEUDO, serialisable, ttl=_TTL_PRICES)
    return prices


# ── Single-stock fundamentals (Epic 5 / Story 5.3) ───────────────────────────

def get_stock_fundamentals(ticker: str) -> dict:
    """
    Return basic fundamentals for one ticker from yfinance.info.
    Fields: market_cap_b, pe_ratio, ps_ratio, peg_ratio,
            revenue_growth, forward_eps_growth, dividend_yield
    """
    key = f"sector:fundamentals:{ticker}"
    cached = cache.get(key, _PSEUDO)
    if cached:
        return cached

    try:
        info = yf.Ticker(ticker).info
    except Exception:
        info = {}

    def _safe(val: Any, default: float = 0.0) -> float:
        if val is None:
            return default
        try:
            f = float(val)
            return default if f != f else f
        except (TypeError, ValueError):
            return default

    result = {
        "market_cap_b":        round(_safe(info.get("marketCap")) / 1e9, 2),
        "pe_ratio":            round(_safe(info.get("trailingPE")), 1),
        "ps_ratio":            round(_safe(info.get("priceToSalesTrailingTwelveMonths")), 1),
        "peg_ratio":           round(_safe(info.get("trailingPegRatio") or info.get("pegRatio")), 2),
        "revenue_growth":      round(_safe(info.get("revenueGrowth")), 4),   # yf trailing 1Y
        "earnings_growth":     round(_safe(info.get("earningsGrowth")), 4),
        "dividend_yield":      round(_safe(info.get("dividendYield")), 4),
        "profit_margin":       round(_safe(info.get("profitMargins")), 4),
        "roe":                 round(_safe(info.get("returnOnEquity")), 4),
        "beta":                round(_safe(info.get("beta"), 1.0), 2),
        "fifty_two_week_high": round(_safe(info.get("fiftyTwoWeekHigh")), 2),
        "fifty_two_week_low":  round(_safe(info.get("fiftyTwoWeekLow")), 2),
        "current_price":       round(_safe(info.get("currentPrice") or info.get("regularMarketPrice")), 2),
        "short_name":          info.get("shortName") or info.get("longName") or ticker,
    }
    cache.set(key, _PSEUDO, result, ttl=_TTL_FUND)
    return result
