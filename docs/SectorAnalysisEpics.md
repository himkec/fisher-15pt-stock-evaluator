Epic 1 – Define sector/universe framework
Goal: Standardize how sectors, subsectors and stocks are represented (GICS-based), so all analysis uses a consistent taxonomy.

Story 1.1 – Define sector and subsector taxonomy
As a product owner, I want a standardized sector/subsector taxonomy, so the engine can consistently group securities for analysis.

Acceptance criteria:

Sector levels documented (e.g., GICS sectors, industry groups, industries) with IDs and names.

Clear mapping rules: 1 stock → 1 primary sector and subsector.
​

Decision document on which level is “sector” and which is “subsector” for the app.

Story 1.2 – Data model for sectors and subsectors
As a developer, I want a normalized schema for sectors and subsectors, so queries and ranking can be efficient.

Acceptance criteria:

DB entities/tables for Sector, Subsector, Security with referential integrity.

Ability to fetch all subsectors for a sector, and all securities for a subsector, via joins.

Migration script and ER diagram checked in to repo.

Story 1.3 – Map external classifications to internal model
As a data engineer, I want a mapping pipeline from external GICS data to our internal IDs, so updates can be automated.

Acceptance criteria:

Ingestion job that reads sector/industry data from chosen provider (e.g., S&P, broker API or CSV).
​

Mapping table from provider codes → internal sector/subsector IDs.

Basic monitoring/alert if mapping fails or classification is missing.

Epic 2 – Market data ingestion (3–5 year history)
Goal: Store clean, queryable total-return data for sectors and stocks over a 3–5 year window.

Story 2.1 – Define data sources and schemas
As a product owner, I want agreed data sources for prices and sector performance, so backtests are consistent.

Acceptance criteria:

Chosen data source(s) for: index/sector-level history, stock OHLCV, dividends/total return documented.

JSON/CSV schemas documented (fields, frequencies, adjustments).

Latency and licensing constraints captured in a short design doc.

Story 2.2 – Implement historical daily price ingestion
As a data engineer, I want to ingest daily price data for all securities in the universe for at least 5 years, so I can compute performance metrics.

Acceptance criteria:

ETL job to pull daily price (and ideally total return) for all listed tickers in the target universe.

Data stored partitioned by date and symbol, with basic quality checks (missing days, splits, outliers).

Backfill for at least 3–5 full years.

Story 2.3 – Sector index/ETF history ingestion
As a data engineer, I want historical performance series for each sector, so I can validate sector-level results.

Acceptance criteria:

Sector benchmark time series (index or ETF) ingested for each defined sector for 3–5 years.
​

Data linked to internal Sector IDs.

Simple check comparing computed sector performance vs. provider dashboards.
​

Epic 3 – Sector performance engine (top 5 sectors)
Goal: Compute and rank sectors by multi-year performance (and possibly risk/volatility), then expose “Top 5” for a chosen window.

Story 3.1 – Define performance metrics and lookback
As a quant/product owner, I want clear metrics for sector performance, so rankings are reproducible and explainable.

Acceptance criteria:

Documented definitions for: total return over 3Y and 5Y, annualized return, max drawdown and volatility.

Chosen default lookback (e.g., last 3 years rolling) and optional 5-year mode.
​

Simple formula sheet checked into repo.

Story 3.2 – Implement sector return calculation
As a developer, I want a service that calculates sector-level performance metrics from underlying stock data, so I can rank sectors.

Acceptance criteria:

Sector returns computed either as cap-weighted or equal-weighted aggregates of member stocks (documented choice).
​

Functions to compute total and annualized return, volatility, drawdown over a configurable period.

Unit tests validating calculations against example sectors from a public dashboard or ETF.

Story 3.3 – Sector ranking API (Top N sectors)
As a user of the system, I want an endpoint to fetch top-performing sectors, so I can drive UI and downstream analysis.

Acceptance criteria:

API to return ranked list of sectors for a given date and lookback (parameters: lookback years, N, weighting scheme).

Response includes sector ID, name, returns, and key stats.

Performance tests to ensure query completes within acceptable latency for typical universe size.

Epic 4 – Subsector ranking within top sectors
Goal: For each top sector, identify and rank subsectors by performance over the same horizon.

Story 4.1 – Subsector performance computation
As a developer, I want to compute subsector-level performance, so I can drill down within each sector.

Acceptance criteria:

Functions to compute subsector metrics (same definitions as sector-level) using member stocks.

Support for filters: minimum number of stocks, minimum total market cap or volume per subsector.
​

Unit tests with a few subsectors cross-checked against external data or ETF proxies.

Story 4.2 – Identify top subsectors inside a sector
As an analyst user, I want to see the best-performing subsectors for each top sector, so I can focus on the strongest themes.

Acceptance criteria:

API that, given a sector ID and lookback, returns sorted subsectors with metrics.

Configurable cap on number of subsectors per sector (e.g., top 3–5).

Filters for excluding tiny or illiquid subsectors (config via settings).

Story 4.3 – Multi-sector subsector ranking (optional)
As an advanced user, I want to see a cross-sector ranking of all subsectors, so I can compare themes across sectors.

Acceptance criteria:

Endpoint returning all subsectors across the universe ranked by chosen metric (e.g., 3Y return).

Ability to filter by parent sector, region, or market cap bucket.

Pagination and ordering validated via tests.

Epic 5 – Stock universe builder per subsector
Goal: Build and expose the list of all stocks in each subsector, to serve as the raw universe for later growth filters.

Story 5.1 – Stock membership queries by subsector
As a user, I want to list all stocks in a given subsector, so I can examine candidates.
​

Acceptance criteria:

DB query/API endpoint that returns all stocks for a subsector ID with basic metadata (ticker, name, market cap, country).

Response filtered for active, listed securities only.

Tests covering subsector with many names and with very few names.

Story 5.2 – Historical performance per stock within subsector
As an analyst, I want to see each stock’s performance metrics within a subsector, so I can later filter on growth characteristics.

Acceptance criteria:

Compute basic metrics per stock over the same lookback (total return, annualized return, volatility).

API that returns, for a subsector, a list of stocks with these metrics attached.

Validation that stock-level metrics aggregate back to subsector/sector numbers within tolerance.

Story 5.3 – Basic stock screener fields (scaffolding)
As a product owner, I want the core fields required for future growth/value filters to be present, so we can later add filter logic with minimal rework.

Acceptance criteria:

Store or ingest core fundamentals: market cap, average daily dollar volume, P/E, revenue and EPS growth (3–5y where available).

Endpoint returns these fields for all stocks in a subsector.

Fields documented as “available but not yet filtered on”.

Epic 6 – Orchestration workflow and configuration
Goal: Provide a single workflow/API to go from “run analysis” → “Top sectors → Top subsectors → Stocks”, with configurable parameters.

Story 6.1 – Analysis configuration model
As a user, I want to configure lookback horizon, number of sectors, and ranking metric, so the pipeline fits my strategy.

Acceptance criteria:

Config model with fields: lookback_years, top_sectors_n, top_subsectors_per_sector, weighting_method, filters (min market cap/volume).

Defaults defined and documented (e.g., 3-year lookback, top 5 sectors).

Configurable via JSON file or DB table.

Story 6.2 – Orchestrator service for full pipeline
As a user, I want a single endpoint that returns top sectors, their top subsectors, and stock lists, so I can consume it from UI or other services.

Acceptance criteria:

Endpoint: /analysis/top-sectors-subsectors-stocks (or similar) that runs the pipeline end-to-end.

Response structure:

sectors: [ { sector, metrics, subsectors: [ { subsector, metrics, stocks: [...] } ] } ].

Timeouts and error handling defined (e.g., partial failure behavior).

Story 6.3 – Batch job / scheduled refresh
As an operator, I want the system to refresh the rankings periodically, so the UI can read precomputed results.

Acceptance criteria:

Scheduled job (e.g., daily or weekly) that recomputes rankings and caches results.

Status and last-run timestamp stored and exposed.

Alerting if job fails or data is stale beyond threshold.

Epic 7 – Basic analytical UI (if applicable)
Goal: Provide a simple interface for viewing and validating the pipeline results.

Story 7.1 – Sector overview page
As a user, I want to see the ranked list of sectors and their 3–5 year performance, so I can quickly understand leadership.

Acceptance criteria:

Page with table or chart showing top N sectors, returns and key stats.

Ability to change lookback (3 vs 5 years) from the UI.

Clicking a sector drills into subsectors.

Story 7.2 – Subsector and stock drill-down page
As a user, I want to see subsectors within a sector and the list of stocks in a chosen subsector, so I can explore candidates.

Acceptance criteria:

Subsector ranking table with metrics for a chosen sector.

On subsector click, show stock table with core metrics (performance, market cap, liquidity).