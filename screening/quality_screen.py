"""
Quality-First Fundamental Screen — engine.

Implements all 5 steps from the requirements doc:
  Step 1: Universe (S&P 500, market cap > $1B)
  Step 2: Profitability filter (ROIC, op margin, FCF margin, FCF positive years)
  Step 3: Balance sheet filter (net debt/EBITDA, interest coverage, dilution)
  Step 4: Earnings quality (EPS volatility, CFO/NI ratio)
  Step 5: Composite quality score (percentile-ranked, weighted)

Each metric is computed from 5 years of yfinance annual statements,
falling back to TTM info-dict values where multi-year data is unavailable.
All per-stock data is cached via the existing SQLite cache (24 h TTL).
"""

import time
import math
from datetime import date

from data import fmp_client, cache as _cache
from sector_analysis.data_client import get_sp500_universe, get_sp500_for_sector
from screening.models import (
    QualityScreenConfig, StockScreenMetrics, QualityScreenResult,
)

_PSEUDO = "SCREEN_QUALITY"
_TTL    = 60 * 60 * 24   # 24 h


# ── Safe helpers ──────────────────────────────────────────────────────────────

def _s(v, d: float = 0.0) -> float:
    """Return float, substituting d on None/NaN."""
    if v is None:
        return d
    try:
        f = float(v)
        return d if math.isnan(f) or math.isinf(f) else f
    except (TypeError, ValueError):
        return d


def _avg(vals: list[float]) -> float:
    clean = [v for v in vals if v is not None and not math.isnan(v)]
    return sum(clean) / len(clean) if clean else 0.0


# ── Metric computations ───────────────────────────────────────────────────────

def _roic_5y(income: list[dict], bs: list[dict]) -> float:
    """
    5-year average ROIC = Operating Income / Invested Capital
    Invested Capital = Total Equity + Total Debt − Cash
    """
    vals = []
    for i, inc in enumerate(income[:5]):
        op = _s(inc.get("operatingIncome"))
        if i >= len(bs):
            continue
        b = bs[i]
        equity = _s(b.get("totalStockholdersEquity"))
        debt   = _s(b.get("totalDebt"))
        cash   = _s(b.get("cashAndCashEquivalents"))
        ic = equity + debt - cash
        if ic > 0:
            vals.append(op / ic)
    return _avg(vals)


def _op_margin_5y(income: list[dict]) -> float:
    vals = []
    for inc in income[:5]:
        rev = _s(inc.get("revenue"))
        op  = _s(inc.get("operatingIncome"))
        if rev > 0:
            vals.append(op / rev)
    return _avg(vals)


def _fcf_margin_5y(income: list[dict], cf: list[dict]) -> float:
    vals = []
    for i, c in enumerate(cf[:5]):
        fcf = _s(c.get("freeCashFlow"))
        if fcf == 0:
            ocf   = _s(c.get("operatingCashFlow"))
            capex = _s(c.get("capitalExpenditure"))   # negative in yfinance
            fcf   = ocf + capex
        rev = _s(income[i].get("revenue")) if i < len(income) else 0
        if rev > 0:
            vals.append(fcf / rev)
    return _avg(vals)


def _fcf_positive_years(cf: list[dict]) -> int:
    count = 0
    for c in cf[:5]:
        fcf = _s(c.get("freeCashFlow"))
        if fcf == 0:
            fcf = _s(c.get("operatingCashFlow")) + _s(c.get("capitalExpenditure"))
        if fcf > 0:
            count += 1
    return count


def _net_debt_ebitda(bs: list[dict], income: list[dict], info: dict) -> float:
    """Net Debt / EBITDA using latest year."""
    b = bs[0] if bs else {}
    net_debt = _s(b.get("totalDebt")) - _s(b.get("cashAndCashEquivalents"))

    ebitda = _s(info.get("ebitda"))
    if ebitda <= 0:
        # Fallback: use operating income as EBIT proxy (ignores D&A)
        ebitda = _s(income[0].get("operatingIncome")) if income else 0

    if ebitda <= 0:
        return 99.0   # can't compute — flag as high leverage
    if net_debt <= 0:
        return 0.0    # net cash position

    return net_debt / ebitda


def _interest_coverage(income: list[dict], info: dict) -> float:
    """
    EBIT / Interest Expense, averaged over available years.
    Interest expense is sourced from yf_info (TTM) and scaled across years
    if per-year data isn't available.
    """
    # Try per-year from income statement (field may not exist in all versions)
    coverages = []
    for inc in income[:5]:
        ebit     = _s(inc.get("ebit") or inc.get("operatingIncome"))
        interest = abs(_s(inc.get("interestExpense")))
        if interest > 0:
            coverages.append(ebit / interest)

    if coverages:
        return _avg(coverages)

    # Fallback: TTM interest expense from info dict
    interest_ttm = abs(_s(info.get("interestExpense")))
    ebit_ttm     = _s(info.get("ebitda")) or _s(income[0].get("operatingIncome") if income else 0)
    if interest_ttm > 0:
        return ebit_ttm / interest_ttm

    return 99.0   # no debt / no interest — assume passes


def _share_dilution_5y(bs: list[dict]) -> float:
    """Total share-count change newest-to-oldest (positive = dilution)."""
    shares = [_s(b.get("commonStockSharesOutstanding")) for b in bs[:5]]
    shares = [s for s in shares if s > 0]
    if len(shares) < 2:
        return 0.0
    return (shares[0] - shares[-1]) / shares[-1]


def _eps_growth_vol(income: list[dict]) -> float:
    """Std dev of year-on-year net-income growth rates (oldest→newest)."""
    nis = [_s(inc.get("netIncome")) for inc in income[:5]]
    nis = list(reversed(nis))   # oldest first
    growths = []
    for i in range(1, len(nis)):
        prev, curr = nis[i - 1], nis[i]
        if prev and prev != 0:
            growths.append((curr - prev) / abs(prev))
    if len(growths) < 2:
        return 0.0
    mu = _avg(growths)
    variance = _avg([(g - mu) ** 2 for g in growths])
    return math.sqrt(variance)


def _cfo_ni_ratio(income: list[dict], cf: list[dict]) -> float:
    """Cumulative operating cash flow / cumulative net income over 5 years."""
    total_cfo = sum(_s(c.get("operatingCashFlow")) for c in cf[:5])
    total_ni  = sum(_s(inc.get("netIncome")) for inc in income[:5])
    if total_ni <= 0:
        return 0.0 if total_ni < 0 else 1.0
    return total_cfo / total_ni


# ── Per-stock fetch + compute ──────────────────────────────────────────────────

def _compute_metrics(
    ticker: str, name: str, sector: str,
) -> tuple[StockScreenMetrics | None, str]:
    """Return (StockScreenMetrics, error_msg).  error_msg="" on success."""
    try:
        info   = fmp_client.get_info(ticker)
        income = fmp_client.get_income_statements(ticker)
        bs     = fmp_client.get_balance_sheets(ticker)
        cf     = fmp_client.get_cash_flow_statements(ticker)
    except Exception as exc:
        return None, str(exc)

    if not income or not bs:
        return None, "no financial statements"

    mcap = _s(info.get("marketCap")) / 1e9

    return StockScreenMetrics(
        ticker=ticker,
        name=info.get("shortName") or info.get("longName") or name,
        sector=sector,
        market_cap_b=mcap,
        roic_5y=_roic_5y(income, bs),
        op_margin_5y=_op_margin_5y(income),
        fcf_margin_5y=_fcf_margin_5y(income, cf),
        fcf_positive_years=_fcf_positive_years(cf),
        net_debt_ebitda=_net_debt_ebitda(bs, income, info),
        interest_coverage=_interest_coverage(income, info),
        share_dilution_5y=_share_dilution_5y(bs),
        eps_growth_vol=_eps_growth_vol(income),
        cfo_ni_ratio=_cfo_ni_ratio(income, cf),
    ), ""


# ── Percentile scoring (Step 5) ───────────────────────────────────────────────

def _pct_rank(values: list[float], v: float, higher_is_better: bool) -> float:
    if not values:
        return 50.0
    rank = sum(1 for x in values if x < v) / len(values) * 100
    return rank if higher_is_better else 100.0 - rank


def _score_survivors(metrics: list[StockScreenMetrics], cfg: QualityScreenConfig) -> None:
    if not metrics:
        return
    roics  = [m.roic_5y for m in metrics]
    fcfs   = [m.fcf_margin_5y for m in metrics]
    ops    = [m.op_margin_5y for m in metrics]
    levs   = [m.net_debt_ebitda for m in metrics]
    vols   = [m.eps_growth_vol for m in metrics]
    cfonis = [m.cfo_ni_ratio for m in metrics]

    for m in metrics:
        m.roic_pct       = _pct_rank(roics,  m.roic_5y,        True)
        m.fcf_margin_pct = _pct_rank(fcfs,   m.fcf_margin_5y,  True)
        m.op_margin_pct  = _pct_rank(ops,    m.op_margin_5y,   True)
        m.leverage_pct   = _pct_rank(levs,   m.net_debt_ebitda, False)
        m.volatility_pct = _pct_rank(vols,   m.eps_growth_vol,  False)
        m.cash_conv_pct  = _pct_rank(cfonis, m.cfo_ni_ratio,    True)
        m.quality_score  = (
            cfg.w_roic       * m.roic_pct +
            cfg.w_fcf_margin * m.fcf_margin_pct +
            cfg.w_op_margin  * m.op_margin_pct +
            cfg.w_leverage   * m.leverage_pct +
            cfg.w_volatility * m.volatility_pct +
            cfg.w_cash_conv  * m.cash_conv_pct
        )


# ── Main runner ────────────────────────────────────────────────────────────────

def run_quality_screen(
    config: QualityScreenConfig | None = None,
    progress_cb=None,
) -> QualityScreenResult:
    """
    Run the Quality-First screen.  Results cached per config for 24 h.
    progress_cb(pct: int, msg: str) is called periodically.
    """
    if config is None:
        config = QualityScreenConfig()

    cache_key = config.cache_key()
    cached = _cache.get(cache_key, _PSEUDO)
    if cached:
        return QualityScreenResult.from_dict(cached)

    t0 = time.time()

    # ── Step 1: Build universe ────────────────────────────────────────────────
    if progress_cb:
        progress_cb(2, "Fetching S&P 500 universe…")

    if config.sector_filter and config.sector_filter != "All Sectors":
        universe_df = get_sp500_for_sector(config.sector_filter)
    else:
        universe_df = get_sp500_universe()

    candidates = universe_df.to_dict("records")
    universe_size = len(candidates)
    n = universe_size

    if progress_cb:
        progress_cb(5, f"Universe: {n} stocks. Fetching financial statements (this takes a while on first run)…")

    # ── Fetch metrics for all stocks ──────────────────────────────────────────
    all_metrics: list[StockScreenMetrics] = []
    errors: list[str] = []

    for i, row in enumerate(candidates):
        ticker = row["ticker"]
        name   = row.get("name", ticker)
        sector = row.get("sector", "")

        if progress_cb and i % 5 == 0:
            pct = 5 + int(60 * i / n)
            progress_cb(pct, f"[{i+1}/{n}] Fetching {ticker}…")

        m, err = _compute_metrics(ticker, name, sector)
        if err:
            errors.append(f"{ticker}: {err}")
        elif m:
            all_metrics.append(m)

    # ── Step 2: Profitability filter ──────────────────────────────────────────
    if progress_cb:
        progress_cb(68, "Applying profitability filter…")

    after_step2: list[StockScreenMetrics] = []
    for m in all_metrics:
        if m.market_cap_b < config.min_market_cap_b:
            m.fail_step   = "profitability"
            m.fail_reason = f"Market cap ${m.market_cap_b:.1f}B < ${config.min_market_cap_b}B threshold"
            continue
        if m.roic_5y < config.min_roic_5y:
            m.fail_step   = "profitability"
            m.fail_reason = f"5Y avg ROIC {m.roic_5y:.1%} < {config.min_roic_5y:.0%}"
            continue
        if m.op_margin_5y < config.min_op_margin_5y:
            m.fail_step   = "profitability"
            m.fail_reason = f"5Y avg op margin {m.op_margin_5y:.1%} < {config.min_op_margin_5y:.0%}"
            continue
        if m.fcf_margin_5y < config.min_fcf_margin_5y:
            m.fail_step   = "profitability"
            m.fail_reason = f"5Y avg FCF margin {m.fcf_margin_5y:.1%} < {config.min_fcf_margin_5y:.0%}"
            continue
        if m.fcf_positive_years < config.min_fcf_positive_years:
            m.fail_step   = "profitability"
            m.fail_reason = (
                f"FCF positive in {m.fcf_positive_years}/5 years "
                f"(need ≥ {config.min_fcf_positive_years})"
            )
            continue
        m.passed = True
        after_step2.append(m)

    # ── Step 3: Balance sheet filter ──────────────────────────────────────────
    if progress_cb:
        progress_cb(75, "Applying balance sheet filter…")

    after_step3: list[StockScreenMetrics] = []
    for m in after_step2:
        if m.net_debt_ebitda > config.max_net_debt_ebitda:
            m.fail_step   = "balance_sheet"
            m.fail_reason = (
                f"Net Debt/EBITDA {m.net_debt_ebitda:.1f}× > {config.max_net_debt_ebitda:.1f}× limit"
            )
            m.passed = False
            continue
        if m.interest_coverage < config.min_interest_coverage:
            m.fail_step   = "balance_sheet"
            m.fail_reason = (
                f"Interest coverage {m.interest_coverage:.1f}× < {config.min_interest_coverage:.1f}× floor"
            )
            m.passed = False
            continue
        if m.share_dilution_5y > config.max_share_dilution_5y:
            m.fail_step   = "balance_sheet"
            m.fail_reason = (
                f"Share dilution {m.share_dilution_5y:.1%} over 5Y > {config.max_share_dilution_5y:.0%} limit"
            )
            m.passed = False
            continue
        after_step3.append(m)

    # ── Step 4: Earnings quality filter ───────────────────────────────────────
    if progress_cb:
        progress_cb(82, "Applying earnings quality filter…")

    # Drop top (1 - max_eps_vol_pct) most volatile names
    if len(after_step3) >= 3:
        sorted_vols = sorted(m.eps_growth_vol for m in after_step3)
        vol_cutoff  = sorted_vols[int(len(sorted_vols) * config.max_eps_vol_pct)]
    else:
        vol_cutoff = float("inf")

    after_step4: list[StockScreenMetrics] = []
    for m in after_step3:
        if m.eps_growth_vol > vol_cutoff:
            m.fail_step   = "earnings_quality"
            m.fail_reason = f"EPS growth std-dev {m.eps_growth_vol:.1%} above volatility cutoff"
            m.passed = False
            continue
        if m.cfo_ni_ratio < config.min_cfo_ni_ratio:
            m.fail_step   = "earnings_quality"
            m.fail_reason = (
                f"5Y CFO/NI ratio {m.cfo_ni_ratio:.2f} < {config.min_cfo_ni_ratio:.0%} floor"
            )
            m.passed = False
            continue
        after_step4.append(m)

    # ── Step 5: Score and rank survivors ──────────────────────────────────────
    if progress_cb:
        progress_cb(90, "Scoring survivors…")

    _score_survivors(after_step4, config)
    after_step4.sort(key=lambda m: m.quality_score, reverse=True)

    result = QualityScreenResult(
        config=config,
        run_date=date.today().isoformat(),
        universe_size=universe_size,
        after_profitability=len(after_step2),
        after_balance_sheet=len(after_step3),
        after_earnings_quality=len(after_step4),
        survivors=after_step4,
        all_metrics=all_metrics,
        run_seconds=round(time.time() - t0, 1),
        errors=errors,
    )

    _cache.set(cache_key, _PSEUDO, result.to_dict(), ttl=_TTL)

    if progress_cb:
        progress_cb(100, "Done")

    return result
