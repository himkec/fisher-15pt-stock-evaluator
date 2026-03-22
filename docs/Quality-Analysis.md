Quality at a Fair Price (QAFP) Analysis – Requirements
This document describes how an app should analyze a stock or ETF using a Quality at a Fair Price framework when given a ticker. It covers data needs, metrics, steps, and outputs, with an eye toward later automation.

1. Scope and Goals
Input: single ticker (stock or ETF), plus optional settings (region, currency, benchmark, quality/valuation thresholds).

Output: structured QAFP report with:

Quality score and sub-scores.

Valuation assessment vs history and peers.

Simple forward-return heuristic (e.g., FCF yield + est. growth).

Pass/Watch/Fail decision with key drivers and red flags.

Constraints: initial version assumes free or low-cost data sources (e.g., Yahoo/AlphaVantage-style APIs or scraped fundamentals).

2. Data Requirements
2.1 Core identifiers
Ticker, exchange, currency.

Security type:

Common stock

ADR

ETF / mutual fund

2.2 Fundamental time series (stocks)
For at least 5–10 years where available:

Income statement: revenue, operating income, net income, EPS (basic/diluted).

Balance sheet: total assets, total equity, total debt, cash and equivalents.

Cash flow: operating cash flow (CFO), capex, free cash flow (derived).

Shares outstanding per period.

2.3 Market and valuation data
Daily/weekly price history (for charts and basic technical context).

Latest and trailing:

Market cap, enterprise value (EV).

Trailing and forward P/E (if available), EV/EBIT, EV/EBITDA, EV/FCF, P/S.

Dividend yield.

2.4 Estimates and sector context (if available)
Analyst EPS growth estimates, next 1–3 years.

Sector classification (GICS/ICB or equivalent).

Sector medians for key metrics: ROIC/ROE, margins, valuation multiples, leverage.

2.5 ETF-specific data (if ticker is ETF)
Asset class and strategy (broad equity, QARP/quality, sector, factor).

Holdings list with weights (top 10 or full where possible).

Aggregate fundamentals if provided by data source (P/E, P/B, dividend yield, etc.).

3. Quality Analysis Logic
The app should compute a Quality Score composed of multiple sub-pillars. Thresholds should be configurable, but start with QARP-style defaults.

3.1 Profitability and returns
Compute:

ROIC (if data available) and/or ROE: 3–5 year average and trend.

Operating margin and net margin: 3–5 year average and stability.

Implementation requirements:

Define “high quality” thresholds relative to sector:

Example defaults:

ROIC > sector median + X%, or absolute > 12–15%.

Operating margin consistently above sector median.

Score 0–100 based on level and volatility (penalize highly cyclical margins).

3.2 Cash generation
Compute:

Free cash flow (FCF) = CFO – capex for each year.

FCF margin = FCF / revenue.

FCF stability and growth rate (5-year CAGR).

Requirements:

Flag companies with:

Repeatedly negative FCF without credible growth justification.

Large divergence between net income and FCF over multiple years.

Score higher for persistent positive FCF and decent growth (e.g., > 10% CAGR).

3.3 Balance sheet and leverage
Compute:

Debt-to-equity, net debt/EBITDA, interest coverage, and cash ratio where possible.

Requirements:

Define safe default thresholds (sector-tunable):

Debt-to-equity < 0.5–1.0 for many sectors.

Net debt/EBITDA below 3x (or sector median).

Penalize companies with:

Weak interest coverage.

Large, persistent net debt without strong FCF to de-lever.

3.4 Growth profile
Compute:

Revenue CAGR and EPS CAGR over 5 and 10 years (where available).

Volatility of growth: standard deviation of YoY changes.

Requirements:

Baseline thresholds:

EPS growth > 10% and revenue growth > 5–10% over 5 years as “good.”

Quality angle: earnings growth driven by improving margins and returns, not just leverage.

3.5 Sector-relative quality
Requirements:

For each metric (ROIC, margins, growth, leverage), compute z-score or percentile vs sector peers if data available.

Quality Score should emphasize relative outperformance within sector, not absolute numbers only.

3.6 Overall Quality Score
Aggregate sub-scores (profitability, cash, balance sheet, growth, sector-relative) into a 0–100 Quality Score.

Provide a short textual label: “High”, “Above Average”, “Average”, “Low”.

4. Valuation Analysis Logic
The app should compute a Valuation Score that reflects whether current pricing is “fair” given quality and growth.

4.1 Core valuation metrics
Compute:

Current and historical (5–10 year):

P/E (TTM and forward), EV/EBIT, EV/EBITDA, EV/FCF, P/S.

FCF yield = FCF / EV or FCF / market cap.

4.2 Relative valuation
Requirements:

Compare current multiples to:

Company’s own 5–10 year average multiples.

Sector medians (P/E, EV/EBIT, EV/FCF, P/S).

Flag:

“Discount” if below both history and peers.

“Reasonable” if in the band around history/peers.

“Stretched” if at high percentiles of history/peers.

4.3 GARP/QARP alignment
Requirements:

If growth data available, compute PEG or equivalent: P/E ÷ EPS growth (using trailing or blended growth).

Define default “fair” bands:

PEG < 1.0–1.5.

FCF yield > 4–5% for mature quality names.

Integrate into Valuation Score (0–100) and label: “Cheap”, “Fair”, “Expensive”.

4.4 Simple expected-return heuristic
Requirements:

Compute a rough expected nominal return estimate as:

expected_return ≈ current_FCF_yield + sustainable_FCF_growth_rate

using the growth estimate from Quality step.

Compare to user’s required rate (default 8–10%) and flag if below.

5. Decision Engine
The app should combine Quality and Valuation into a clear recommendation tag.

5.1 Scoring grid
Requirements (configurable):

Define zones using Quality Score (Q) and Valuation Score (V):

Buy/Accumulate: Q ≥ 70 and V ≥ 60, expected_return ≥ required_return.

Watchlist:

Q ≥ 70 but V < 60 (great business, too expensive).

Q 50–70 and V ≥ 60 (okay business at good price).

Avoid: Q < 50 or obvious red flags (high leverage, negative FCF, etc.).

5.2 Red-flag checks
Requirements:

Override logic to force “Avoid” or “High Risk” if:

Very high leverage (above a critical threshold).

Repeated negative FCF with no credible growth case.

Massive earnings volatility or frequent large equity dilution.

6. ETF Handling
When ticker is ETF:

Identify underlying strategy: quality, growth, value, QARP, etc., from issuer description.

If holdings data available:

Compute weighted average Quality and Valuation metrics across top holdings, or use available composite metrics (e.g., portfolio P/E, ROE).

Provide:

Quality/valuation snapshot of the portfolio.

Concentration and sector breakdown.

Comparison vs benchmark ETF (e.g., broad market).

7. User-Facing Workflow
7.1 Input step
User enters ticker and optional settings:

Region/market.

Required return (e.g., 8–12%).

Risk preference (more conservative → stricter leverage and quality thresholds).

7.2 Analysis pipeline
High-level sequence the app must implement:

Detect security type (stock vs ETF).

Fetch and cache raw data (fundamentals, prices, sector, estimates).

Run Quality analysis and compute Quality Score.

Run Valuation analysis and compute Valuation Score + expected_return.

Apply decision engine to derive recommendation tag and red-flag indicators.

Generate human-readable report + machine-readable JSON payload.

7.3 Output report
The app should return:

Summary section:

Ticker, name, sector, Quality Score, Valuation Score, expected_return, recommendation tag.

Quality section:

Key metrics table (ROIC/ROE, margins, FCF stats, leverage, growth).

Sector-relative view (e.g., “ROIC in top 20% of sector”).

Valuation section:

Current multiples vs history and peers.

PEG, FCF yield, implied return vs required return.

Risk and red flags:

Bullet list of main concerns.

Optional: charts (time series of ROIC, margins, FCF, and key multiples).

For ETF tickers, the report should emphasize portfolio-level quality and valuation, not single-company metrics.

8. Architecture and Extensibility Notes
Clear separation between:

Data adapters (Yahoo/API connectors).

Metric computation layer.

Scoring and decision logic.

Presentation/reporting layer.
​

All thresholds and weights must be configuration-driven so strategies (pure QARP, stricter value tilt, etc.) can be adjusted without code changes.

Design metrics and outputs so they can be reused for:

Batch screening (multiple tickers).

Periodic monitoring (alert if Quality/Valuation change beyond thresholds).

9. Recommended Data Sources
This section lists practical APIs and feeds for implementing QAFP analysis, starting with free/low‑cost options and leaving room to upgrade later.

9.1 Core market and fundamentals (stocks)
Tier 1: Free / freemium APIs

Alpha Vantage

Provides realtime and historical prices, plus a Fundamentals API (company overview, financial statements, key ratios).

Good fit for: stock quotes, OHLCV history, income statement, balance sheet, cash flow, and basic ratios needed for ROE, margins, leverage, growth.

Yahoo Finance (via wrappers like yfinance or third‑party APIs)

Public endpoints (or scraping/wrappers) can return quotes, historical prices, basic fundamentals, and ETF/fund data.

Good fit for: quick prototyping of price history, simple valuation metrics, and summary statistics; be aware of recent tightening of free downloads.

Finnhub / IEX / Twelve Data (optional alternatives)

Offer free tiers for realtime and historical prices, earnings, and some fundamentals depending on provider.
​

Use as backup or to improve coverage/latency for certain markets.
​

Tier 2: Low‑cost / richer fundamentals

Financial Modeling Prep (FMP)

Provides full financial statements, ratios, price data, and some analytics via API, with paid tiers for broader coverage.

Good fit for: building more robust metrics (ROIC, EV/FCF, historical multiples) and backtests once the prototype works.

SimFin

Focused on fundamentals with up to 20 years of history, indicators, and stock screener features; free tier for a subset of US stocks, paid for more.

Good fit for: long history, sector aggregations, and factor-style quality metrics.

9.2 ETF holdings and portfolio-level data
For ETF‑level QAFP (e.g., portfolio ROE, valuation, sector mix):

ETF holdings APIs (Tradefeeds, Finnworlds, etc.)

Provide current and historical ETF holdings, weights, and basic ETF performance metrics.

Use case: look through ETFs to compute weighted-average quality/valuation of underlying holdings.

Yahoo Finance / Alpha Vantage ETF endpoints

Often expose fund‑level stats (P/E, P/B, yield, sector weights) even without full holdings.

Good for quick ETF‑level QAFP when you don’t need full look‑through.

9.3 Suggested baseline stack (for v1 app)
To keep implementation simple and costs near zero:

Primary data source: Alpha Vantage (fundamentals + price) for stocks and ETFs.

Secondary source: yfinance/Yahoo Finance wrappers for any missing ETF summary stats, sector data, and sanity checks.

Optional upgrade path: SimFin or FMP if you need deeper histories, more stable fundamentals, or large‑scale screening/backtesting.

You can add these as concrete “adapters” in your architecture section, e.g., AlphaVantageAdapter, YahooAdapter, SimFinAdapter, each mapping external fields into your internal metric schema.