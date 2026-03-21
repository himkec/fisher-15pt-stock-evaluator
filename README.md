# Fisher 15-Point Stock Evaluator

A practical implementation of Philip Fisher's 15-point checklist for evaluating high-quality growth companies — with real-time data, AI-powered qualitative scoring, and an interactive Streamlit dashboard.

---

## What it does

Enter any US stock ticker and get a full Fisher 15-point evaluation:

| Points | Method | Data source |
|--------|--------|-------------|
| 1, 5, 6, 10, 13 | Rule-based quantitative scoring | Yahoo Finance (free) |
| 2, 3, 4, 7–9, 11–12, 14–15 | Claude AI reads SEC filings | SEC EDGAR (free) + Anthropic Claude API |

Results include a **BUY / WATCHLIST / PASS** verdict, scorecard table, radar chart, per-point rationale, and an AI-generated investment thesis.

Previously analyzed stocks are saved and reloadable from the sidebar at **zero API cost**.

---

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/your-username/fisher-15pt-stock-evaluator.git
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

- **Anthropic API key** — required for qualitative scoring (points 2, 3, 4, 7–9, 11–12, 14–15). Get one at [console.anthropic.com](https://console.anthropic.com).
- **Yahoo Finance** — free, no key needed (quantitative points).
- **SEC EDGAR** — free, no key needed. Just set your email in `EDGAR_USER_AGENT` as required by EDGAR's fair-use policy.

### 3. Run

```bash
streamlit run app.py --server.headless true --server.port 8502
```

Open **http://localhost:8502** in your browser.

---

## Architecture

```
fisher-15pt-stock-evaluator/
├── app.py                     # Streamlit entry point + pipeline orchestration
├── config/
│   └── settings.py            # All constants, thresholds, API URLs
├── data/
│   ├── cache.py               # SQLite cache (24hr TTL, 30-day eval history)
│   ├── fmp_client.py          # Yahoo Finance wrapper (via yfinance)
│   └── edgar_client.py        # SEC EDGAR: CIK, filings, XBRL, full-text search
├── scoring/
│   ├── models.py              # PointResult + EvalSummary dataclasses
│   ├── quantitative.py        # Rule-based scoring for points 1, 5, 6, 10, 13
│   ├── qualitative.py         # Claude AI scoring for points 2, 3, 4, 7–9, 11–12, 14–15
│   ├── prompts.py             # All Claude prompt templates and scoring rubrics
│   └── aggregator.py          # Score aggregation + BUY/WATCHLIST/PASS verdict
├── ui/
│   └── components.py          # Streamlit widgets: scorecard, radar chart, expanders
└── docs/
    ├── Philip-Fisher-15-Point-Checklist-Pseudo-Code.md
    └── Technical-Implementation-Options.md
```

### Data flow

```
User enters ticker
  → Yahoo Finance   → revenue, margins, cash flows, shares (points 1, 5, 6, 10, 13)
  → SEC EDGAR       → 10-K text, proxy (DEF 14A), XBRL facts, full-text search hits
  → Claude API      → reads filings, scores qualitative points 2, 3, 4, 7–9, 11–12, 14–15
  → Aggregator      → total score, ratio, BUY / WATCHLIST / PASS verdict
  → SQLite cache    → saved for 30 days; reload from sidebar at zero cost
```

---

## Caching and costs

| Action | API calls | Claude tokens |
|--------|-----------|---------------|
| First evaluation of a ticker | ~7 Yahoo Finance + ~5 EDGAR | ~10 Claude calls (~$0.05–0.15) |
| Repeat evaluation (within 24hr) | 0 | 0 |
| Load from history (sidebar) | 0 | 0 |

All results are stored in a local SQLite database at `~/.fisher_cache/cache.db`.

---

## The 15 Fisher Points

| # | Point | Scoring method |
|---|-------|---------------|
| 1 | Growth potential of products/services | 5-year revenue CAGR |
| 2 | Ongoing innovation drive | Claude on 10-K + R&D trend |
| 3 | Effectiveness of R&D | Claude on 10-K + XBRL R&D data |
| 4 | Quality of sales organization | Claude on 10-K + revenue/employee |
| 5 | Profit margin level | Gross margin vs sector peers |
| 6 | Margin stability and improvement | 5-year operating margin slope |
| 7 | Labor and personnel relations | Claude on 10-K Human Capital + EDGAR search |
| 8 | Executive relations | Claude on 10-K + proxy + EDGAR 8-K search |
| 9 | Depth of management | Claude on 10-K officers + proxy |
| 10 | Cost analysis and controls | SG&A/Revenue 5-year trend |
| 11 | Industry characteristics | Claude on 10-K Business section |
| 12 | Long-term vs short-term outlook | Claude on MD&A + CapEx trend |
| 13 | Need for equity financing | FCF self-funding + share dilution CAGR |
| 14 | Management candor with investors | Claude on MD&A + restatement search |
| 15 | Management integrity | Claude on proxy + EDGAR investigation search |

Each point returns **strong** (2 pts), **average** (1 pt), or **weak** (0 pts).
Maximum score: **30 points**.

Verdict thresholds:
- **BUY / ACCUMULATE** — score ≥ 75% and no critical point (1, 5, 13, 15) is weak
- **WATCHLIST** — score 50–75%
- **PASS** — score < 50%

---

## Requirements

- Python 3.12+
- `streamlit`, `anthropic`, `yfinance`, `pandas`, `plotly`, `python-dotenv`

Install all with:

```bash
pip install -r requirements.txt
```
