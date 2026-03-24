# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the app
streamlit run app.py --server.headless true --server.port 8502

# Install dependencies
pip install -r requirements.txt

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_quantitative.py -v

# Run a single test
pytest tests/test_qafp.py::test_score_valuation_strong -v
```

## Environment setup

Copy `.env.example` to `.env` and set:
- `ANTHROPIC_API_KEY` — required for qualitative scoring (Claude AI)
- `EDGAR_USER_AGENT` — required by SEC EDGAR (e.g. `FisherEvaluator/1.0 your@email.com`)

Yahoo Finance and SEC EDGAR require no API keys. FMP_API_KEY is optional (not currently used for a paid tier).

## Pages

The app has two Streamlit pages:
- `app.py` — **Stock Evaluator** (Fisher 15-Point, QAFP, CAN SLIM, Fundamental, Intrinsic Value)
- `pages/sector_analysis.py` — **Sector Analysis** (top-down GICS sector → subsector → stock universe)

Streamlit auto-discovers `pages/` and adds navigation. `app.py` is the default/first page.

## Architecture

The app evaluates stocks against three frameworks: **Fisher 15-Point**, **QAFP**, and **CAN SLIM**. All three share the same data pipeline and SQLite cache.

### Data pipeline (`app.py` orchestrates)

1. **Yahoo Finance** (`data/fmp_client.py`) — fetches income statements, balance sheets, cash flows, ratios, key metrics, peer ratios, price history, institutional holders. Despite the module name, this wraps `yfinance`, not FMP.
2. **SEC EDGAR** (`data/edgar_client.py`) — resolves CIK, fetches 10-K and proxy (DEF 14A) text, XBRL facts, and EDGAR full-text search hit counts.
3. **Quantitative scoring** (`scoring/quantitative.py`) — rule-based scoring for Fisher points 1, 5, 6, 10, 13 using financial ratios and CAGR calculations.
4. **Qualitative scoring** (`scoring/qualitative.py`) — sends 10-K/proxy excerpts to Claude (`claude-sonnet-4-6`) for Fisher points 2, 3, 4, 7–9, 11–12, 14–15. Prompts are in `scoring/prompts.py`.
5. **QAFP engine** (`scoring/qafp.py`) — scores Quality (profitability 30%, cash generation 30%, balance sheet 20%, growth 20%) and Valuation, returns `QAFPResult`.
6. **CAN SLIM engine** (`scoring/canslim.py`) — scores letters C/A/N/S/L/I/M using quarterly financials, price data, and institutional holders, returns `CANSLIMResult`.
7. **Aggregator** (`scoring/aggregator.py`) — sums Fisher point scores, checks critical points (1, 5, 13, 15), returns `EvalSummary` with BUY/WATCHLIST/PASS verdict.
8. **UI** (`ui/components.py`) — Streamlit widgets: verdict banner, scorecard table, radar chart, per-point expanders, QAFP section, CAN SLIM section.

### Caching (`data/cache.py`)

All results are stored in a local SQLite DB at `~/.fisher_cache/cache.db`. Cache keys follow the pattern `"namespace:subkey"` (e.g. `"yf:info"`, `"eval:summary"`, `"qafp:result"`, `"canslim:result"`). TTLs:
- Financial data: 24 hours
- SEC filings: 1 year (immutable)
- Claude qualitative scores: 7 days
- Full evaluation summaries: 30 days

The cache seed for qualitative scoring is `ticker:accession_number` so re-runs against the same filing hit cache without re-calling Claude.

### Configuration (`config/settings.py`)

All scoring thresholds (CAGR cutoffs, margin thresholds, verdict ratios), API endpoints, TTLs, and the Claude model name live here. Change thresholds here, not inline in scoring modules.

### Data models

- `scoring/models.py` — `PointResult` (per Fisher point) and `EvalSummary` (full 15-point result)
- `scoring/qafp_models.py` — `QAFPResult` with `SubScore` sub-pillars
- `scoring/canslim_models.py` — `CANSLIMResult` with `LetterScore` and `BuyPoint`

All models implement `to_dict()` / `from_dict()` for SQLite serialization.

## Key scoring thresholds

Fisher verdict: **BUY** = ratio ≥ 75% AND no critical point (1, 5, 13, 15) is weak; **WATCHLIST** = 50–75%; **PASS** = <50%.

QAFP verdict: **BUY** = Quality ≥ 70 and Valuation ≥ 60; **ACCUMULATE** = Quality ≥ 70 and Valuation 40–60; **WATCHLIST** = Quality 50–70; **AVOID** = Quality < 50.

CAN SLIM: weighted composite of C/A/N/S/L/I (each 0–100); M is a gatekeeper that can downgrade the verdict.
