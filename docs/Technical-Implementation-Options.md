# Technical Implementation Options — Fisher 15-Point Stock Evaluator

**Date:** 2026-03-20
**Status:** Decision-pending
**Purpose:** Evaluate architecture and technology stack options before committing to implementation. All options target real-time data ingestion for all 15 Fisher checklist points.

---

## Data Requirements Map

Before comparing options, here is what each Fisher point actually needs:

| Point | Primary Signal | Data Type |
|-------|---------------|-----------|
| 1 Growth Potential | Industry TAM, revenue CAGR | Quantitative + Market research |
| 2 Innovation Drive | R&D capex ratio, product pipeline | Quantitative + Qualitative |
| 3 R&D Effectiveness | Patents, new product launches, R&D-to-revenue | Quantitative + Patent DBs |
| 4 Sales Organization | Revenue/employee, churn, NPS signals | Quantitative + Alt data |
| 5 Profit Margin Level | Gross/operating margins vs peers | Quantitative |
| 6 Margin Trend | 5-year margin trajectory | Quantitative |
| 7 Labor Relations | Glassdoor score, turnover, labor disputes | Alt data + News |
| 8 Executive Relations | Exec tenure, promotion patterns, comp ratio | Proxy filings + Alt data |
| 9 Management Depth | Org chart depth, succession disclosures | SEC 10-K + Alt data |
| 10 Cost Controls | Unit economics, SG&A efficiency | Quantitative |
| 11 Industry Characteristics | Network effects, regulatory moats | LLM analysis of filings |
| 12 Long-term Outlook | CapEx/revenue, management commentary tone | Quantitative + NLP |
| 13 Equity Financing | FCF self-funding, dilution history | Quantitative |
| 14 Management Candor | Earnings call tone, 8-K frequency | NLP on SEC filings |
| 15 Management Integrity | Related-party transactions, legal actions | SEC filings + News NLP |

**Key insight:** ~8 of 15 points require NLP/LLM analysis of qualitative text (earnings calls, 10-Ks, news). Pure quantitative APIs are insufficient.

---

## Real-Time Data Sources

| Source | Coverage | Cost | Latency | Best For |
|--------|----------|------|---------|----------|
| **SEC EDGAR API** | 10-K, 10-Q, 8-K, proxy (DEF 14A) | Free | ~1 day (filing lag) | Points 8, 9, 13, 14, 15 |
| **Yahoo Finance (yfinance)** | Prices, financials, analyst estimates | Free (unofficial) | ~15 min delay | Points 1, 5, 6, 10, 13 |
| **Financial Modeling Prep (FMP)** | Financials, ratios, peers, DCF | Free tier / $14-149/mo | Real-time | Points 1-6, 10, 13 |
| **Polygon.io** | Ticks, news, filings | Free tier / $29+/mo | Real-time | Prices, news |
| **Alpha Vantage** | Financials, earnings, sentiment | Free 25/day / $50+/mo | 15-min delay | Points 5, 6 |
| **Glassdoor (scraping / RapidAPI)** | Employee reviews, ratings | RapidAPI $0-30/mo | Days | Point 7 |
| **USPTO Patent API** | Patent filings by assignee | Free | Weekly refresh | Point 3 |
| **NewsAPI / Benzinga** | News articles, press releases | Free tier / $449/mo | Real-time | Points 2, 7, 14, 15 |
| **Anthropic Claude API** | LLM reasoning over text | ~$3-15 per 1M tokens | <1 second | Points 7-15 NLP |
| **OpenAI / Claude Embeddings** | Semantic search in filings | ~$0.02/1M tokens | <1 second | RAG over 10-Ks |

---

## Architecture Options

---

### Option A — Python CLI / Batch Script

**Description:** Single Python script or small package. Accepts a ticker symbol, fetches data from APIs, scores all 15 points, outputs a JSON/text report.

```
CLI: python evaluate.py AAPL
  → fetches APIs → runs scoring logic → prints scorecard
```

**Advantages:**
- Fastest to build (days, not weeks)
- Zero infrastructure — runs locally
- Easy to debug and extend one point at a time
- Full control over data pipeline
- Works well as a foundation before adding UI

**Disadvantages:**
- No real-time UI or streaming updates — blocking execution
- No caching — re-fetches everything on each run (slow and costly)
- No scheduling for portfolio monitoring
- Hard to share with others
- Poor for iterative analyst workflow (no interactivity)

**Best for:** Rapid proof-of-concept, single-user personal use, testing data sources.

---

### Option B — Python Backend (FastAPI) + React Frontend

**Description:** REST/WebSocket API server handles data fetching, scoring, and caching. A React SPA provides an interactive dashboard with real-time score updates.

```
React UI ←→ FastAPI ←→ [FMP, SEC EDGAR, Claude API, ...]
                  ↕
             Redis cache + PostgreSQL (history)
```

**Advantages:**
- Full real-time UX — WebSocket streams progress per Fisher point as it scores
- Shareable: host on Railway, Render, Fly.io
- Separation of concerns: swap UI without touching scoring logic
- Caching layer prevents repeated expensive API calls
- Can store historical evaluations and track score changes over time
- Supports multiple concurrent users / portfolio monitoring

**Disadvantages:**
- Highest build effort (~2-4 weeks for MVP)
- Requires separate frontend and backend work
- Needs hosting, database, Redis — operational overhead
- Overengineered for single-user use

**Best for:** Production tool, team use, portfolio-level monitoring dashboard.

---

### Option C — Streamlit App (Python-only, Rapid UI)

**Description:** Streamlit wraps Python scoring logic in an interactive web UI with minimal code. No separate frontend needed.

```
Browser → Streamlit → Python scoring engine → APIs
```

**Advantages:**
- Single Python codebase — no HTML/CSS/JS
- `st.spinner`, `st.progress`, `st.dataframe` give good UX out of the box
- Deploy to Streamlit Cloud (free tier) in minutes
- Interactive widgets for analyst override of individual scores
- Fast iteration: UI changes are just Python changes
- Excellent for data exploration and visualization (`st.plotly_chart`)

**Disadvantages:**
- Streamlit re-runs the whole script on each interaction — clunky for long-running API calls
- Less control over UI layout vs React
- Not ideal for high-concurrency use
- Streamlit Cloud free tier has resource limits
- Hard to build truly real-time streaming without `st.empty()` hacks

**Best for:** Personal/small-team analyst tool, fast MVP with good-enough UI, solo use with occasional sharing.

---

### Option D — LangChain / LlamaIndex Agentic Pipeline + Streamlit

**Description:** An AI agent orchestrates all 15 evaluations. Each Fisher point becomes a tool/agent node. The LLM (Claude) drives data gathering and reasoning for qualitative points while calling financial API tools for quantitative points.

```
User: "Evaluate NVDA"
  → Agent decomposes into 15 sub-tasks
  → Calls tools: get_financials(), search_sec_filings(), get_news()
  → LLM synthesizes qualitative scores
  → Aggregates and returns decision
```

**Advantages:**
- Handles qualitative points (7-15) far better than rule-based logic
- Agent can "scuttle-butt" — synthesize signals across news, filings, and earnings calls
- LangGraph enables streaming agent progress to UI (real-time token streaming)
- Highly extensible — add new data tools without rewriting core logic
- Claude is particularly strong at evaluating management candor and integrity signals in text

**Disadvantages:**
- LLM outputs are non-deterministic — scores may vary between runs
- Higher per-evaluation cost (~$0.10-0.50 per company with Claude Sonnet)
- Agent reasoning can be slow (30-120 seconds per full evaluation)
- Harder to audit why a specific score was assigned
- Requires careful prompt engineering for consistent scoring rubrics
- LLM hallucination risk on factual claims (patents, legal history) — must ground with retrieved data

**Best for:** Maximizing coverage of all 15 points including hard-to-quantify ones; best final output quality; when analyst time > API cost.

---

### Option E — Serverless (AWS Lambda / Vercel Edge Functions)

**Description:** Each Fisher point evaluation is a separate serverless function triggered on-demand. Results stored in DynamoDB/Vercel KV. Frontend on Next.js.

```
Next.js UI → API Routes (Vercel Edge) → [financial APIs, SEC, Claude]
                                       ↕
                                   Vercel KV (cache)
```

**Advantages:**
- Zero server management — scales to zero when idle (low cost)
- Edge deployment means low latency globally
- Vercel free tier covers low-usage personal tools
- Next.js gives both API routes and frontend in one repo

**Disadvantages:**
- Serverless functions have execution time limits (10-30s on Vercel) — full 15-point evaluation may time out
- Cold starts add latency on first invocation
- DynamoDB/KV adds complexity for relational data (historical scores, peer comparisons)
- Harder to run long-running processes like 10-K document parsing
- More AWS/cloud knowledge required

**Best for:** If you want near-zero hosting cost and are comfortable with Next.js; not ideal given the evaluation's long-running nature.

---

## Comparison Matrix

| Criterion | A: CLI | B: FastAPI+React | C: Streamlit | D: Agentic+LLM | E: Serverless |
|-----------|--------|-----------------|--------------|----------------|---------------|
| Build time | 1-3 days | 3-6 weeks | 1-2 weeks | 2-3 weeks | 3-5 weeks |
| Real-time UX | None | Excellent | Good | Good (streaming) | Good |
| Qualitative point coverage | Poor | Medium | Medium | Excellent | Medium |
| Cost to run | Very low | Low-medium | Low | Medium ($0.10-0.50/eval) | Very low |
| Auditability | High | High | High | Medium | High |
| Hosting complexity | None | Medium | None (Cloud) | Low | Medium |
| Scalability | Single user | Multi-user | Single user | Single/small team | High |
| Iteration speed | Fast | Slow | Fast | Medium | Slow |

---

## Recommended Approach

### Phase 1 — Option C (Streamlit) as MVP

Start with **Streamlit + Python scoring engine** backed by:
- **Financial Modeling Prep API** for points 1, 5, 6, 10, 13 (quantitative financials)
- **SEC EDGAR full-text search API** for filing retrieval
- **Claude API (claude-sonnet-4-6)** for NLP scoring of points 7-15
- **yfinance** as free fallback for financials
- **NewsAPI** for recent news signals

Rationale: Streamlit gives a working, interactive UI in the same Python codebase as the scoring engine. It is the fastest path to a usable tool without compromising the ability to migrate to Option B or D later.

### Phase 2 — Upgrade to Option D (Agentic)

Once the scoring rubrics are validated on real companies, convert qualitative points (7-15) to a **LangGraph agent** with tool-calling. This improves coverage of the Fisher points that resist pure quantitative treatment.

### Phase 3 (Optional) — Option B (FastAPI + React)

If the tool is used by more than one person or needs portfolio-level dashboards, extract the scoring engine into a FastAPI service and build a proper React frontend.

---

## Key Technology Decisions to Finalize

1. **Primary financial data API:** FMP (paid, reliable) vs Alpha Vantage (free, rate-limited) vs yfinance (free, unofficial, fragile)?
2. **LLM strategy:** Claude-only vs Claude for qualitative + rule-based for quantitative?
3. **SEC filing parsing:** EDGAR full-text search API vs direct XBRL data vs third-party (Polygon filings)?
4. **Scoring rubric format:** Hard-coded thresholds vs LLM-judged vs hybrid?
5. **Caching strategy:** Redis (persistent, fast) vs in-memory (simple, non-persistent) vs SQLite (local persistent)?
6. **Deployment target:** Local only vs Streamlit Cloud vs self-hosted?

---

## Proposed Tech Stack (for Phase 1 decision)

```
Language:         Python 3.12
UI:               Streamlit 1.x
Financial data:   Financial Modeling Prep API (primary), yfinance (fallback)
SEC filings:      SEC EDGAR full-text search API (free) + sec-api.io (optional)
NLP/LLM:          Anthropic Claude API (claude-sonnet-4-6)
Embeddings/RAG:   LlamaIndex or LangChain for 10-K/transcript chunking
News:             NewsAPI (free tier) or Benzinga
Patent data:      USPTO Patent Full-Text & Image Database (free)
Alt data:         Glassdoor via RapidAPI (employee reviews for Point 7)
Caching:          Python diskcache or SQLite (local) / Redis (cloud)
Testing:          pytest + responses (HTTP mocking)
Dependency mgmt:  uv or Poetry
Deployment:       Streamlit Community Cloud (free) or Docker + Fly.io
```

---

## Next Steps

- [ ] Agree on Phase 1 tech stack from the options above
- [ ] Sign up for FMP API key (or confirm yfinance is sufficient for MVP)
- [ ] Confirm LLM strategy (Claude API key / budget per evaluation)
- [ ] Define scoring thresholds for quantitative points (what is "strong" vs "average" for margins?)
- [ ] Create project scaffold and implement Point 5 (Profit Margin) as the first end-to-end slice
