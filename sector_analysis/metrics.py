"""
Epic 3 — Performance metric calculations.

All functions operate on pandas Series of prices or returns.
Pure functions — no I/O, no cache, fully testable.
"""

import numpy as np
import pandas as pd
from datetime import date

from sector_analysis.taxonomy import RISK_FREE_RATE


def total_return(prices: pd.Series) -> float:
    """(end / start) - 1 over the full price series."""
    if prices.empty or prices.iloc[0] <= 0:
        return 0.0
    return float(prices.iloc[-1] / prices.iloc[0]) - 1.0


def annualized_return(prices: pd.Series) -> float:
    """Compound annualised return: (1 + total)^(1/years) - 1."""
    if prices.empty or len(prices) < 2:
        return 0.0
    years = (prices.index[-1] - prices.index[0]).days / 365.25
    if years <= 0:
        return 0.0
    tr = total_return(prices)
    return float((1.0 + tr) ** (1.0 / years) - 1.0)


def daily_returns(prices: pd.Series) -> pd.Series:
    return prices.pct_change().dropna()


def annualized_volatility(prices: pd.Series) -> float:
    """Annualised standard deviation of daily returns × sqrt(252)."""
    dr = daily_returns(prices)
    if dr.empty:
        return 0.0
    return float(dr.std() * np.sqrt(252))


def sharpe_ratio(ann_ret: float, ann_vol: float) -> float:
    if ann_vol <= 0:
        return 0.0
    return float((ann_ret - RISK_FREE_RATE) / ann_vol)


def max_drawdown(prices: pd.Series) -> float:
    """Maximum peak-to-trough decline (negative fraction)."""
    if prices.empty:
        return 0.0
    roll_max = prices.expanding().max()
    drawdowns = (prices - roll_max) / roll_max
    return float(drawdowns.min())


def ytd_return(prices: pd.Series) -> float:
    """Return from Jan 1 of the current year to the last price."""
    if prices.empty:
        return 0.0
    year_start = str(date.today().year)
    ytd = prices[prices.index >= year_start]
    if len(ytd) < 2:
        return 0.0
    return float(ytd.iloc[-1] / ytd.iloc[0]) - 1.0


def compute_all(prices: pd.Series) -> dict:
    """Convenience wrapper — returns all metrics as a dict."""
    ann_ret = annualized_return(prices)
    ann_vol = annualized_volatility(prices)
    return {
        "total_return":      round(total_return(prices),     4),
        "annualized_return": round(ann_ret,                  4),
        "volatility":        round(ann_vol,                  4),
        "sharpe":            round(sharpe_ratio(ann_ret, ann_vol), 3),
        "max_drawdown":      round(max_drawdown(prices),     4),
        "ytd_return":        round(ytd_return(prices),       4),
    }


def equal_weighted_return(stock_prices: pd.DataFrame) -> pd.Series:
    """
    Given a DataFrame of stock close prices (columns = tickers, index = dates),
    return a synthetic equal-weighted portfolio price series (rebased to 100).
    """
    if stock_prices.empty:
        return pd.Series(dtype=float)
    # Forward-fill to handle missing days, then compute normalised returns
    normed = stock_prices.ffill().dropna(how="all")
    # Rebase each column to 1.0 at start
    rebased = normed / normed.iloc[0]
    # Equal-weight average
    portfolio = rebased.mean(axis=1)
    return portfolio * 100.0   # synthetic price series starting at 100
