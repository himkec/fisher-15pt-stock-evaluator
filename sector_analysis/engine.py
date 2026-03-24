"""
Epics 3, 4, 5, 6 — Sector Analysis pipeline.

run_sector_analysis(config)
    → fetches sector ETF prices, computes metrics, returns ranked AnalysisResult.
    Takes ~5–15 s (12 ETF downloads).

run_subsector_analysis(sector_name, config)
    → fetches all S&P 500 stocks in sector, downloads their prices,
      groups by GICS Sub-Industry, computes equal-weighted metrics.
    Takes ~30–90 s depending on sector size.  Results cached 24 h.

get_subsector_stocks(sub_industry, config)
    → returns StockItem list with fundamentals for each stock.
    Takes ~10–30 s.  Cached per stock 24 h.
"""

import time
from datetime import date, timedelta

import pandas as pd

from sector_analysis.taxonomy import (
    SECTORS, BENCHMARK_TICKER, ALL_ETFS, MIN_SUBSECTOR_STOCKS,
)
from sector_analysis.models import (
    AnalysisConfig, AnalysisResult, SectorResult, SubsectorResult, StockItem,
)
from sector_analysis import metrics as m
from sector_analysis import data_client as dc
from data import cache

_PSEUDO = "SECTOR_ANALYSIS"
_TTL_ANALYSIS   = 60 * 60 * 24        # 24 h
_TTL_SUBSECTOR  = 60 * 60 * 24        # 24 h


# ── Helpers ───────────────────────────────────────────────────────────────────

def _lookback_start(years: int) -> str:
    return str((date.today() - timedelta(days=int(years * 365.25))).isoformat())


def _trim_to_lookback(prices: pd.DataFrame, years: int) -> pd.DataFrame:
    start = _lookback_start(years)
    return prices[prices.index >= start]


# ── Epic 3 — Sector performance engine ───────────────────────────────────────

def run_sector_analysis(config: AnalysisConfig | None = None) -> AnalysisResult:
    """
    Compute and rank all 11 GICS sectors by annualised return over config.lookback_years.
    Results cached for 24 h.
    """
    if config is None:
        config = AnalysisConfig()

    cache_key = f"sector:analysis:{config.lookback_years}y"
    cached = cache.get(cache_key, _PSEUDO)
    if cached:
        return AnalysisResult.from_dict(cached)

    t0 = time.time()

    # Download all sector ETFs + benchmark
    prices_df = dc.get_etf_prices(ALL_ETFS, config.lookback_years)
    prices_df = _trim_to_lookback(prices_df, config.lookback_years)

    if prices_df.empty:
        raise RuntimeError("No price data returned for sector ETFs.")

    # Benchmark metrics
    bench = prices_df.get(BENCHMARK_TICKER)
    if bench is None or bench.dropna().empty:
        bm_ret = bm_ann = 0.0
    else:
        bench_clean = bench.dropna()
        bm_ret = m.total_return(bench_clean)
        bm_ann = m.annualized_return(bench_clean)

    # Per-sector metrics
    results: list[SectorResult] = []
    for sector_name, meta in SECTORS.items():
        etf  = meta["etf"]
        icon = meta["icon"]
        col  = prices_df.get(etf)
        if col is None or col.dropna().empty:
            continue
        prices = col.dropna()
        stats  = m.compute_all(prices)
        results.append(SectorResult(
            name=sector_name, etf=etf, icon=icon,
            rank=0,
            total_return=      stats["total_return"],
            annualized_return= stats["annualized_return"],
            volatility=        stats["volatility"],
            sharpe=            stats["sharpe"],
            max_drawdown=      stats["max_drawdown"],
            ytd_return=        stats["ytd_return"],
            vs_benchmark=      round(stats["annualized_return"] - bm_ann, 4),
        ))

    # Rank by annualised return (descending)
    results.sort(key=lambda r: r.annualized_return, reverse=True)
    for i, r in enumerate(results):
        r.rank = i + 1

    lookback_start = prices_df.index[0].strftime("%Y-%m-%d") if not prices_df.empty else ""

    result = AnalysisResult(
        config=config,
        as_of_date=date.today().isoformat(),
        lookback_start=lookback_start,
        benchmark_return=round(bm_ret, 4),
        benchmark_annualized=round(bm_ann, 4),
        all_sectors=results,
        run_seconds=round(time.time() - t0, 1),
    )
    cache.set(cache_key, _PSEUDO, result.to_dict(), ttl=_TTL_ANALYSIS)
    return result


# ── Epic 4 — Subsector ranking ───────────────────────────────────────────────

def run_subsector_analysis(
    sector_name: str,
    config: AnalysisConfig | None = None,
    progress_cb=None,   # optional callback(pct: int, msg: str)
) -> list[SubsectorResult]:
    """
    For one top sector, group S&P 500 stocks by GICS Sub-Industry and compute
    equal-weighted performance for each subsector.

    Returns list[SubsectorResult] sorted by annualised_return descending.
    """
    if config is None:
        config = AnalysisConfig()

    cache_key = f"sector:subsector:{sector_name.replace(' ', '_')}:{config.lookback_years}y"
    cached = cache.get(cache_key, _PSEUDO)
    if cached:
        return [SubsectorResult.from_dict(d) for d in cached]

    # Get S&P 500 stocks in this sector
    sector_df = dc.get_sp500_for_sector(sector_name)
    if sector_df.empty:
        return []

    tickers = sector_df["ticker"].tolist()
    if progress_cb:
        progress_cb(10, f"Downloading prices for {len(tickers)} stocks in {sector_name}…")

    # Download all stock prices at once (much faster than one-by-one)
    prices_df = dc.get_stock_prices(tickers, config.lookback_years)
    prices_df = _trim_to_lookback(prices_df, config.lookback_years) if not prices_df.empty else prices_df

    if progress_cb:
        progress_cb(60, "Computing subsector performance…")

    # Group by sub-industry
    sub_groups = sector_df.groupby("sub_industry")["ticker"].apply(list).to_dict()

    subsectors: list[SubsectorResult] = []
    for sub_name, sub_tickers in sub_groups.items():
        # Keep only tickers that have price data
        valid = [t for t in sub_tickers if t in prices_df.columns]
        if not valid:
            continue

        portfolio_prices = m.equal_weighted_return(prices_df[valid])
        if portfolio_prices.empty:
            continue

        stats = m.compute_all(portfolio_prices)
        subsectors.append(SubsectorResult(
            name=sub_name,
            rank=0,
            ticker_count=len(valid),
            total_return=      stats["total_return"],
            annualized_return= stats["annualized_return"],
            volatility=        stats["volatility"],
            sharpe=            stats["sharpe"],
            ytd_return=        stats["ytd_return"],
            small_sample=      len(valid) < MIN_SUBSECTOR_STOCKS,
        ))

    # Rank
    subsectors.sort(key=lambda s: s.annualized_return, reverse=True)
    for i, s in enumerate(subsectors):
        s.rank = i + 1

    if progress_cb:
        progress_cb(100, "Done")

    cache.set(cache_key, _PSEUDO, [s.to_dict() for s in subsectors], ttl=_TTL_SUBSECTOR)
    return subsectors


# ── Epic 5 — Stock universe builder ──────────────────────────────────────────

def get_subsector_stocks(
    sub_industry: str,
    config: AnalysisConfig | None = None,
    progress_cb=None,
) -> list[StockItem]:
    """
    For one sub-industry, return S&P 500 stocks with performance + fundamentals.
    Sorted by market_cap_b descending.
    """
    if config is None:
        config = AnalysisConfig()

    cache_key = f"sector:stocks:{sub_industry.replace(' ', '_')}:{config.lookback_years}y"
    cached = cache.get(cache_key, _PSEUDO)
    if cached:
        return [StockItem.from_dict(d) for d in cached]

    sub_df   = dc.get_sp500_for_subsector(sub_industry)
    tickers  = sub_df["ticker"].tolist()
    if not tickers:
        return []

    if progress_cb:
        progress_cb(10, f"Fetching data for {len(tickers)} stocks…")

    # Price history for total return & YTD
    prices_df = dc.get_stock_prices(tickers, config.lookback_years)
    if not prices_df.empty:
        prices_df = _trim_to_lookback(prices_df, config.lookback_years)

    stocks: list[StockItem] = []
    for i, row in sub_df.iterrows():
        ticker = row["ticker"]
        name   = row["name"]

        # Price-based metrics
        tr = ytd = 0.0
        if not prices_df.empty and ticker in prices_df.columns:
            col = prices_df[ticker].dropna()
            if not col.empty:
                tr  = m.total_return(col)
                ytd = m.ytd_return(col)

        # Fundamentals
        try:
            fund = dc.get_stock_fundamentals(ticker)
        except Exception:
            fund = {}

        mcap = fund.get("market_cap_b", 0.0)
        if mcap < config.min_market_cap_b and config.min_market_cap_b > 0:
            continue

        stocks.append(StockItem(
            ticker=ticker,
            name=fund.get("short_name") or name,
            sub_industry=sub_industry,
            market_cap_b=mcap,
            total_return=round(tr, 4),
            ytd_return=round(ytd, 4),
            pe_ratio=fund.get("pe_ratio", 0.0),
            revenue_growth=fund.get("revenue_growth", 0.0),
        ))

        if progress_cb:
            progress_cb(10 + int(80 * (i + 1) / len(sub_df)), f"Processed {ticker}…")

    stocks.sort(key=lambda s: s.market_cap_b, reverse=True)

    cache.set(cache_key, _PSEUDO, [s.to_dict() for s in stocks], ttl=_TTL_ANALYSIS)
    return stocks


# ── Top-N stocks by growth for a whole sector ─────────────────────────────────

def get_top_sector_stocks(
    sector_name: str,
    config: AnalysisConfig | None = None,
    n: int = 10,
    progress_cb=None,
) -> list[StockItem]:
    """
    Return the top-N S&P 500 stocks in a sector ranked by total return
    over config.lookback_years.  Cached 24 h.
    """
    if config is None:
        config = AnalysisConfig()

    cache_key = f"sector:top_stocks:{sector_name.replace(' ', '_')}:{config.lookback_years}y"
    cached = cache.get(cache_key, _PSEUDO)
    if cached:
        return [StockItem.from_dict(d) for d in cached][:n]

    sector_df = dc.get_sp500_for_sector(sector_name)
    tickers   = sector_df["ticker"].tolist()
    if not tickers:
        return []

    if progress_cb:
        progress_cb(10, f"Downloading prices for {len(tickers)} stocks in {sector_name}…")

    prices_df = dc.get_stock_prices(tickers, config.lookback_years)
    if not prices_df.empty:
        prices_df = _trim_to_lookback(prices_df, config.lookback_years)

    if progress_cb:
        progress_cb(70, "Computing returns…")

    stocks: list[StockItem] = []
    for _, row in sector_df.iterrows():
        ticker = row["ticker"]
        name   = row["name"]
        sub    = row.get("sub_industry", "")

        tr = ytd = 0.0
        if not prices_df.empty and ticker in prices_df.columns:
            col = prices_df[ticker].dropna()
            if not col.empty:
                tr  = m.total_return(col)
                ytd = m.ytd_return(col)

        stocks.append(StockItem(
            ticker=ticker,
            name=name,
            sub_industry=sub,
            market_cap_b=0.0,   # filled in below
            total_return=round(tr, 4),
            ytd_return=round(ytd, 4),
            pe_ratio=0.0,
            revenue_growth=0.0,
        ))

    # Sort by total return first so we only fetch fundamentals for the top stocks
    stocks.sort(key=lambda s: s.total_return, reverse=True)
    top = stocks[:max(n * 2, 20)]   # fetch fundamentals for 2× buffer to allow mcap filter

    if progress_cb:
        progress_cb(80, "Fetching fundamentals for top performers…")

    enriched: list[StockItem] = []
    for s in top:
        try:
            fund = dc.get_stock_fundamentals(s.ticker)
        except Exception:
            fund = {}
        mcap = fund.get("market_cap_b", 0.0)
        if mcap < config.min_market_cap_b and config.min_market_cap_b > 0:
            continue
        enriched.append(StockItem(
            ticker=s.ticker,
            name=fund.get("short_name") or s.name,
            sub_industry=s.sub_industry,
            market_cap_b=mcap,
            total_return=s.total_return,
            ytd_return=s.ytd_return,
            pe_ratio=fund.get("pe_ratio", 0.0),
            revenue_growth=fund.get("revenue_growth", 0.0),
        ))

    # Final sort by total return (enriched preserves order but mcap filter may shift)
    enriched.sort(key=lambda s: s.total_return, reverse=True)

    if progress_cb:
        progress_cb(100, "Done")

    cache.set(cache_key, _PSEUDO, [s.to_dict() for s in enriched], ttl=_TTL_SUBSECTOR)
    return enriched[:n]
