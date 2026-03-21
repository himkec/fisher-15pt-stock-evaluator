import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── API keys ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
FMP_API_KEY: str = os.getenv("FMP_API_KEY", "")
EDGAR_USER_AGENT: str = os.getenv(
    "EDGAR_USER_AGENT", "FisherEvaluator/1.0 user@example.com"
)

# ── FMP endpoints (free tier) ─────────────────────────────────────────────────
FMP_BASE_URL = "https://financialmodelingprep.com/api/v3"
FMP_DAILY_LIMIT = 240          # buffer below the 250 hard cap
FMP_REQUEST_INTERVAL = 0.5    # seconds between live FMP calls

# ── SEC EDGAR endpoints ───────────────────────────────────────────────────────
EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions"
EDGAR_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts"
EDGAR_BROWSE_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
EFTS_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"
EDGAR_REQUEST_INTERVAL = 0.15  # ~6-7 req/sec, well under 10/sec EDGAR limit

# ── Cache ─────────────────────────────────────────────────────────────────────
CACHE_DB_PATH = Path.home() / ".fisher_cache" / "cache.db"
CACHE_TTL_SECONDS = 86_400        # 24 hours for FMP + EDGAR submissions
CACHE_TTL_FILING = 60 * 60 * 24 * 365  # 1 year — filings are immutable
CACHE_TTL_CLAUDE = 60 * 60 * 24 * 7    # 7 days — re-score weekly

# ── Claude model ──────────────────────────────────────────────────────────────
CLAUDE_MODEL = "claude-sonnet-4-6"
CLAUDE_MAX_TOKENS = 1024
CLAUDE_TEMPERATURE = 0.1

# ── Scoring thresholds (quantitative points) ──────────────────────────────────
# Point 1 — Revenue CAGR (5yr)
REVENUE_CAGR_STRONG = 0.15    # >= 15% = strong
REVENUE_CAGR_AVERAGE = 0.07   # 7-15% = average; <7% = weak

# Point 5 — Gross margin vs sector peers
MARGIN_PREMIUM_STRONG = 0.10  # >=10pp above sector median = strong
MARGIN_PREMIUM_AVERAGE = 0.00 # 0-10pp above = average; below = weak

# Point 6 — Operating margin 5yr trend (slope per year in percentage points)
MARGIN_TREND_STRONG = 0.5     # improving >= 0.5pp/yr = strong
MARGIN_TREND_AVERAGE = -0.5   # stable ±0.5pp = average; deteriorating = weak

# Point 10 — SG&A / Revenue trend (negative slope = improving cost control)
SGNA_TREND_STRONG = -0.005    # improving (falling) by >= 0.5pp/yr
SGNA_TREND_AVERAGE = 0.005    # flat or slightly rising

# Point 13 — Share dilution (annual CAGR of shares outstanding)
DILUTION_STRONG = -0.01       # buyback ≥1%/yr = strong
DILUTION_AVERAGE = 0.02       # issuance ≤2%/yr = average; >2%/yr = weak

# ── Scoring map ───────────────────────────────────────────────────────────────
SCORE_MAP = {"strong": 2, "average": 1, "weak": 0}

# Points where a "weak" score blocks a BUY verdict regardless of total ratio
CRITICAL_POINTS = {1, 5, 13, 15}

# ── Verdict thresholds ────────────────────────────────────────────────────────
INVEST_THRESHOLD = 0.75   # ratio >= 0.75 AND no critical weak → BUY
WATCHLIST_THRESHOLD = 0.50

# ── Filing text limits (characters fed to Claude) ─────────────────────────────
TEN_K_CHAR_LIMIT = 80_000
PROXY_CHAR_LIMIT = 40_000

# ── Sector fallback gross margins (used when FMP peers endpoint returns empty) ─
# Source: approximate S&P 500 medians by GICS sector
SECTOR_FALLBACK_GROSS_MARGINS = {
    "Technology": 0.55,
    "Communication Services": 0.50,
    "Consumer Discretionary": 0.35,
    "Consumer Staples": 0.38,
    "Health Care": 0.55,
    "Financials": 0.60,
    "Industrials": 0.33,
    "Materials": 0.28,
    "Energy": 0.35,
    "Utilities": 0.42,
    "Real Estate": 0.45,
    "default": 0.38,
}
