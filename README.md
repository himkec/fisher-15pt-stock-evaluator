# Fisher 15-Point Stock Evaluator

A multi-framework stock analysis platform built with Streamlit. Combines Philip Fisher's 15-point checklist, QAFP quality scoring, CAN SLIM momentum analysis, deep fundamental analysis, intrinsic value models, top-down sector analysis, and a rules-based quality screener — all backed by free data sources (Yahoo Finance, SEC EDGAR) and Claude AI for qualitative scoring.

---

## Pages

### 📊 Stock Evaluator (`app.py`)

Enter any US ticker and run one or more analysis frameworks:

| Framework | What it does | Verdict |
|-----------|-------------|---------|
| **Fisher 15-Point** | AI reads SEC filings + quantitative scoring | BUY / WATCHLIST / PASS |
| **QAFP** | Quality at a Fair Price — profitability, FCF, balance sheet, valuation | BUY / ACCUMULATE / WATCHLIST / AVOID |
| **CAN SLIM** | O'Neil momentum — earnings acceleration, RS, institutional buying | BUY / WATCH / AVOID |
| **Fundamental Analysis** | Deep dive: margins, returns, growth, leverage, efficiency | — |
| **Intrinsic Value** | FCF DCF (Bear/Base/Bull), DDM, Residual Income, Graham Number — football field chart | — |

**Investor style presets** auto-select the right frameworks (Long-Term Growth, QAFP, Momentum, Deep Value, Income, Full Due Diligence). Previously analyzed stocks are saved and reloadable from the sidebar at zero API cost.

---

### 🏭 Sector Analysis (`pages/sector_analysis.py`)

Top-down, single-page drill-down:

1. **All 11 GICS sectors** ranked by annualised return (SPDR ETF proxies) — bar chart + rankings table
2. **Click a sector card** → see top-10 stocks by total return + subsector breakdown below
3. **Click a subsector** → stock universe with scatter plot + fundamentals table
4. **"Analyze →"** on any stock — inline picker with preset bundles (Full DD, Growth, Value, Momentum) → switches to Stock Evaluator with ticker and analyses pre-filled

Configurable: lookback period (3Y / 5Y), top-N sectors and subsectors, minimum market cap. All data cached 24h.

---

### 🔍 Screening (`pages/screening.py`)

Rules-based screens to narrow the investment universe before deep analysis.

#### Quality-First Fundamental Screen *(live)*

Five sequential filter steps per the requirements spec:

| Step | Filter | Default threshold |
|------|--------|-------------------|
| 1 | Universe | S&P 500, market cap ≥ $1B |
| 2 | Profitability | ROIC ≥ 15%, op margin ≥ 10%, FCF margin ≥ 10%, FCF positive ≥ 4/5 years |
| 3 | Balance sheet | Net Debt/EBITDA ≤ 3×, interest coverage ≥ 3.5×, share dilution ≤ 15% over 5Y |
| 4 | Earnings quality | CFO/NI ≥ 70% cumulative, EPS growth volatility in bottom 70% |
| 5 | Scoring | Percentile-ranked composite (ROIC 25%, FCF margin 20%, op margin 15%, leverage 20%, stability 10%, cash conversion 10%) |

Results: funnel chart, step summary, ranked table with quality score bars, one-click "Analyze →" to Stock Evaluator.
All thresholds configurable from the sidebar. Screen results cached 24h. Sector filter reduces runtime from ~20 min (full S&P 500) to 2–5 min.

#### Coming soon
- CAN SLIM Momentum Screen
- Value / Deep-Value Screen
- GARP Screen
- Dividend Growth Screen

---

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/himkec/fisher-15pt-stock-evaluator.git
cd fisher-15pt-stock-evaluator
pip install -r requirements.txt
```

### 2. Configure API keys

```bash
cp .env.example .env
```

Edit `.env`:

```
ANTHROPIC_API_KEY=your_anthropic_key_here
EDGAR_USER_AGENT=FisherEvaluator/1.0 your@email.com
```

- **Anthropic API key** — required for Fisher qualitative scoring (points 2, 3, 4, 7–9, 11–12, 14–15). Get one at [console.anthropic.com](https://console.anthropic.com).
- **Yahoo Finance** — free, no key needed.
- **SEC EDGAR** — free, no key needed. Set your email in `EDGAR_USER_AGENT` per EDGAR's fair-use policy.

### 3. Run

```bash
streamlit run app.py --server.headless true --server.port 8502
```

Open **http://localhost:8502** in your browser. Streamlit auto-discovers `pages/` and adds navigation.

---

## Architecture

```
fisher-15pt-stock-evaluator/
├── app.py                          # Stock Evaluator page + full pipeline
├── pages/
│   ├── sector_analysis.py          # Sector Analysis page (7-epic top-down framework)
│   └── screening.py                # Screening page (multi-strategy screener)
├── config/
│   └── settings.py                 # All thresholds, TTLs, API config
├── data/
│   ├── cache.py                    # SQLite cache with per-entry TTL
│   ├── fmp_client.py               # Yahoo Finance wrapper (via yfinance)
│   └── edgar_client.py             # SEC EDGAR: CIK, filings, XBRL, full-text search
├── scoring/
│   ├── models.py                   # PointResult, EvalSummary
│   ├── quantitative.py             # Fisher points 1, 5, 6, 10, 13 (rule-based)
│   ├── qualitative.py              # Fisher points 2, 3, 4, 7–9, 11–12, 14–15 (Claude AI)
│   ├── prompts.py                  # Claude prompt templates and scoring rubrics
│   ├── aggregator.py               # Score aggregation + verdict
│   ├── qafp.py / qafp_models.py    # QAFP quality + valuation engine
│   ├── canslim.py / canslim_models.py  # CAN SLIM letter scoring
│   ├── fundamental.py / fundamental_models.py  # Deep fundamental analysis
│   └── intrinsic_value.py / intrinsic_value_models.py  # DCF, DDM, RIM, Graham
├── sector_analysis/
│   ├── taxonomy.py                 # GICS sectors, ETF tickers, constants
│   ├── data_client.py              # ETF + stock price downloads, S&P 500 universe
│   ├── engine.py                   # Sector, subsector, and top-stock runners
│   ├── metrics.py                  # Return, volatility, Sharpe, drawdown calculations
│   └── models.py                   # AnalysisConfig, SectorResult, SubsectorResult, StockItem
├── screening/
│   ├── models.py                   # QualityScreenConfig, StockScreenMetrics, QualityScreenResult
│   └── quality_screen.py           # 5-step quality filter + percentile scoring engine
├── ui/
│   └── components.py               # All Streamlit UI components
└── tests/
    ├── test_quantitative.py        # 68 tests — Fisher quantitative scoring
    ├── test_qafp.py                # 67 tests — QAFP engine
    ├── test_canslim.py             # CAN SLIM scoring tests
    └── test_intrinsic_value.py     # 85 tests — all 5 valuation methods
```

### Data flow — Stock Evaluator

```
User enters ticker + selects frameworks
  → Yahoo Finance   → income statements, balance sheets, cash flows, price history
  → SEC EDGAR       → 10-K text, proxy (DEF 14A), XBRL facts, full-text search
  → Claude API      → qualitative scoring for Fisher points 2, 3, 4, 7–9, 11–12, 14–15
  → Scoring engines → Fisher aggregator, QAFP, CAN SLIM, Fundamental, Intrinsic Value
  → SQLite cache    → all results saved; sidebar reload at zero cost
```

### Data flow — Sector Analysis

```
Run Sector Analysis
  → yfinance batch download → 11 SPDR ETF + SPY price history
  → Sector engine           → annualised return, volatility, Sharpe, max DD per sector
  → Click sector            → download all S&P 500 stocks in sector
                            → top-10 by total return (with fundamentals)
                            → equal-weighted subsector performance groups
  → Click subsector         → stock universe with per-stock fundamentals
  → Click Analyze →         → prefills Stock Evaluator with ticker + chosen frameworks
```

### Data flow — Quality Screen

```
Run Quality Screen (sector or full S&P 500)
  → S&P 500 universe (Wikipedia, cached 7 days)
  → Per-stock: income statements + balance sheets + cash flows (cached 24h each)
  → Step 2: profitability filter  (ROIC, op margin, FCF margin, FCF consistency)
  → Step 3: balance sheet filter  (leverage, interest coverage, dilution)
  → Step 4: earnings quality      (CFO/NI ratio, EPS growth volatility)
  → Step 5: percentile scoring    → composite quality score → ranked table
  → Screen result cached 24h per config combination
```

---

## Caching

All results stored in `~/.fisher_cache/cache.db` (SQLite).

| Data type | TTL |
|-----------|-----|
| Yahoo Finance financials | 24 hours |
| SEC filings | 1 year (immutable) |
| Claude qualitative scores | 7 days |
| Full evaluation summaries | 30 days |
| Sector ETF prices | 24 hours |
| S&P 500 constituent list | 7 days |
| Quality screen results | 24 hours |

---

## The 15 Fisher Points

| # | Point | Method |
|---|-------|--------|
| 1 | Growth potential | 5-year revenue CAGR |
| 2 | Innovation drive | Claude on 10-K + R&D trend |
| 3 | R&D effectiveness | Claude on 10-K + XBRL R&D data |
| 4 | Sales organisation | Claude on 10-K + revenue/employee |
| 5 | Profit margin level | Gross margin vs sector peers |
| 6 | Margin stability | 5-year operating margin slope |
| 7 | Labour relations | Claude on 10-K Human Capital + EDGAR search |
| 8 | Executive relations | Claude on 10-K + proxy + EDGAR 8-K search |
| 9 | Depth of management | Claude on 10-K officers + proxy |
| 10 | Cost controls | SG&A/Revenue 5-year trend |
| 11 | Industry characteristics | Claude on 10-K Business section |
| 12 | Long-term outlook | Claude on MD&A + CapEx trend |
| 13 | Equity financing need | FCF self-funding + share dilution CAGR |
| 14 | Management candor | Claude on MD&A + restatement search |
| 15 | Management integrity | Claude on proxy + EDGAR investigation search |

Each point: **strong** (2 pts) / **average** (1 pt) / **weak** (0 pts). Max: **30 pts**.
Verdict: **BUY** ≥ 75% with no critical weak point · **WATCHLIST** 50–75% · **PASS** < 50%.

---

## Tests

```bash
pytest tests/ -v
```

| File | Tests | Covers |
|------|-------|--------|
| `test_quantitative.py` | 68 | Fisher points 1, 5, 6, 10, 13 |
| `test_qafp.py` | 67 | QAFP quality, valuation, verdicts |
| `test_canslim.py` | — | CAN SLIM letter scoring |
| `test_intrinsic_value.py` | 85 | DCF, DDM Gordon, DDM Multi-Period, RIM, Graham Number |

---

## Requirements

- Python 3.12+
- `streamlit`, `anthropic`, `yfinance`, `pandas`, `plotly`, `python-dotenv`, `requests`

```bash
pip install -r requirements.txt
```
