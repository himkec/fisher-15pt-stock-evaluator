"""
Epic 1 — GICS sector/subsector taxonomy.

Sectors  → 11 GICS sectors, each mapped to a SPDR ETF proxy.
Subsectors → GICS Sub-Industry names sourced directly from S&P 500 data,
             grouped under their parent sector.

No external DB required: taxonomy is code-defined here and driven by the
live S&P 500 constituent list returned by data_client.get_sp500_universe().
"""

# ── 11 GICS Sectors ──────────────────────────────────────────────────────────
# ETF = SPDR Select Sector ETF used as the performance proxy.

SECTORS: dict[str, dict] = {
    "Information Technology":  {"etf": "XLK",  "icon": "💻"},
    "Health Care":             {"etf": "XLV",  "icon": "🏥"},
    "Financials":              {"etf": "XLF",  "icon": "🏦"},
    "Consumer Discretionary":  {"etf": "XLY",  "icon": "🛍️"},
    "Communication Services":  {"etf": "XLC",  "icon": "📡"},
    "Industrials":             {"etf": "XLI",  "icon": "⚙️"},
    "Consumer Staples":        {"etf": "XLP",  "icon": "🛒"},
    "Energy":                  {"etf": "XLE",  "icon": "⛽"},
    "Utilities":               {"etf": "XLU",  "icon": "⚡"},
    "Real Estate":             {"etf": "XLRE", "icon": "🏢"},
    "Materials":               {"etf": "XLB",  "icon": "🔩"},
}

BENCHMARK_TICKER = "SPY"

SECTOR_ETFS: list[str] = [v["etf"] for v in SECTORS.values()]
ALL_ETFS: list[str]    = SECTOR_ETFS + [BENCHMARK_TICKER]

# ── Lookback options ──────────────────────────────────────────────────────────
LOOKBACK_OPTIONS = {
    "3 Years": 3,
    "5 Years": 5,
}

# ── Default configuration ─────────────────────────────────────────────────────
DEFAULT_LOOKBACK_YEARS   = 3
DEFAULT_TOP_SECTORS_N    = 5
DEFAULT_TOP_SUBSECTORS_N = 4
RISK_FREE_RATE           = 0.045   # for Sharpe calculation
MIN_SUBSECTOR_STOCKS     = 2       # subsectors with fewer stocks are shown but flagged


def sector_for_etf(etf: str) -> str | None:
    for name, meta in SECTORS.items():
        if meta["etf"] == etf:
            return name
    return None
