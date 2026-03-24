1. CAN SLIM pipeline (pseudo‑code)
text
function analyze_canslim(ticker, settings):
    data = load_all_data_for_canslim(ticker)

    scores = {}
    scores["C"] = evaluate_current_earnings(data)
    scores["A"] = evaluate_annual_earnings(data)
    scores["N"] = evaluate_new_factor(data)
    scores["S"] = evaluate_supply_demand(data)
    scores["L"] = evaluate_leader_laggard(data)
    scores["I"] = evaluate_institutional_sponsorship(data)
    scores["M"] = evaluate_market_direction(data)

    composite_score = aggregate_canslim_scores(scores)
    buy_point       = detect_buy_point(data.price_series, data.volume_series)
    risk_rules      = define_risk_rules(buy_point)

    profile = classify_investor_fit("CAN_SLIM")

    return {
        "scores": scores,
        "composite": composite_score,
        "buy_point": buy_point,
        "risk_rules": risk_rules,
        "investor_fit": profile
    }
2. Per‑letter logic
C – Current quarterly earnings
text
function evaluate_current_earnings(data):
    q_eps_growth = yoy_eps_growth(latest_quarter, same_quarter_prev_year)
    q_sales_growth = yoy_sales_growth(latest_quarter)

    eps_ok    = q_eps_growth >= 25%   // can raise bar to 30–50% for stricter mode [web:99][web:102][web:115]
    sales_ok  = q_sales_growth > 0    // prefer double‑digit [web:99][web:102]

    quality_check = compare_eps_vs_cashflow_growth(data) // avoid low‑quality EPS [web:115][web:114]

    score = 0
    if eps_ok: score += 60
    if sales_ok: score += 20
    if quality_check == "clean": score += 20

    return clamp(score, 0, 100)
A – Annual earnings growth
text
function evaluate_annual_earnings(data):
    eps_cagr_3y = cagr(annual_eps_last_3y)
    eps_cagr_5y = cagr(annual_eps_last_5y)
    consistency = count_years_positive_eps_growth(last_5y)

    meets_bar = eps_cagr_3y >= 25% and eps_cagr_5y >= 25% [web:99][web:102][web:115][web:118]

    score = 0
    if meets_bar: score += 70
    if consistency >= 4: score += 30

    return clamp(score, 0, 100)
N – New product / management / highs
text
function evaluate_new_factor(data):
    has_new_product    = detect_news_or_filing_keywords(data.news, ["launch", "platform", "version", "breakthrough"])
    has_new_management = detect_management_change(data.filings)
    making_new_highs   = price_near_52w_high(data.price_series, tolerance = 5%) [web:99][web:101][web:102][web:106]

    score = 0
    if has_new_product or has_new_management: score += 60
    if making_new_highs: score += 40

    return clamp(score, 0, 100)
S – Supply and demand
text
function evaluate_supply_demand(data):
    shares_outstanding   = latest_shares_outstanding(data)
    avg_volume           = average_volume(lookback = 50d)
    breakout_volume      = volume_on_recent_breakout_attempt(data)
    volume_spike_ratio   = breakout_volume / avg_volume

    small_float          = shares_outstanding < threshold (e.g. 25–100M) [web:115][web:118]
    strong_demand        = volume_spike_ratio >= 1.5 and price_breaking_out(data) [web:102][web:115][web:120]

    score = 0
    if small_float: score += 40
    if strong_demand: score += 60

    return clamp(score, 0, 100)
L – Leader vs laggard
text
function evaluate_leader_laggard(data):
    rs_percentile = compute_relative_strength_percentile(
        ticker_return = data.price_12m_return,
        universe_returns = market_or_sector_returns
    ) [web:99][web:101][web:118][web:120]

    is_leader = rs_percentile >= 70   // O’Neil often uses 80+ as ideal [web:118]

    if rs_percentile >= 90: score = 100
    else if rs_percentile >= 80: score = 80
    else if rs_percentile >= 70: score = 60
    else: score = 0

    return score
I – Institutional sponsorship
text
function evaluate_institutional_sponsorship(data):
    num_insts           = data.institutional_holders_count
    quality_insts       = count_top_tier_insts(data.holder_quality_ratings)
    inst_ownership_trend= trend(data.institutional_ownership_percent_last_8q) [web:99][web:101][web:102][web:115]

    basic_ok       = num_insts > min_threshold
    quality_ok     = quality_insts >= min_quality
    trend_positive = inst_ownership_trend == "up"

    score = 0
    if basic_ok: score += 40
    if quality_ok: score += 30
    if trend_positive: score += 30

    return clamp(score, 0, 100)
M – Market direction
text
function evaluate_market_direction(global_data):
    // Use major index (e.g. S&P 500 / Nifty / local benchmark). [web:99][web:101][web:115][web:118]

    index_trend      = detect_trend(global_data.index_price_series, lookback = 50–200d)
    distribution_days= count_distribution_days(global_data.index_price_volume, window = 4–5w)
    follow_through   = detect_follow_through_day(global_data.index_price_volume) [web:101][web:115][web:118]

    bull = index_trend == "up" and distribution_days <= threshold and follow_through == true
    bear = index_trend == "down" or distribution_days > high_threshold

    if bull: return "market_uptrend"
    if bear: return "market_correction"
    return "mixed"
3. Composite score, buy logic, and risk rules
text
function aggregate_canslim_scores(scores):
    // Weight fundamentals heavily, technical/market as gatekeepers.
    weighted = (
        0.2 * scores["C"] +
        0.2 * scores["A"] +
        0.15 * scores["N"] +
        0.15 * scores["S"] +
        0.15 * scores["L"] +
        0.15 * scores["I"]
    )
    return round(weighted)

function detect_buy_point(price_series, volume_series):
    base = detect_cup_or_flat_base(price_series)    // ≥ 7 weeks ideal [web:101][web:102][web:106]
    if not base: return null

    pivot_price = base.resistance_level
    confirmation = volume_on_breakout(volume_series, pivot_price) >= 1.5 * avg_volume(50d)

    if confirmation:
        return { "pivot": pivot_price, "valid": true }
    else:
        return { "pivot": pivot_price, "valid": false }

function define_risk_rules(buy_point):
    if buy_point is null or not buy_point.valid:
        return null

    entry_price = buy_point.pivot * (1 + entry_buffer)   // e.g. +0–5%
    stop_loss   = entry_price * 0.93                     // 7% below entry [web:101][web:104][web:113]
    first_target= entry_price * 1.25                     // ~25% profit [web:101][web:110]

    return {
        "entry": entry_price,
        "stop_loss": stop_loss,
        "take_profit": first_target
    }
4. Recommended data sources for CAN SLIM
You need both fundamental and technical data, plus some market/ownership data.

Fundamentals (C, A)
Quarterly and annual EPS and revenue, at least 3–5 years back.

Cash flow (for EPS quality checks).

Sources (free/freemium):

Alpha Vantage – Fundamentals API (EPS, revenue, statements).

Financial Modeling Prep / SimFin (richer history, better fundamentals).

Technicals and price/volume (N, S, L, M)
Daily price/volume series for each stock.

Daily price/volume for major index.

52‑week highs, relative strength vs index, distribution day detection.

Sources:

Yahoo Finance (via yfinance or wrappers) for historical OHLCV and index data.

Alpha Vantage / IEX / Twelve Data as alternative or backup for OHLCV.

Institutional holdings (I)
Number of institutional holders, % of shares held, trends over time.

Sources (often partially free):

Yahoo Finance holdings endpoints (institutions, top holders).

FMP / other paid feeds if you want time‑series of institutional ownership.

Dedicated CAN SLIM style tools (for inspiration, not required)
MarketSmith, TrendSpider, StockRover, etc. implement CAN SLIM‑like screens and can be a reference for filtering logic and UI, but they’re paid.

5. “Who this technique is for” block (for UI)
You can standardize this as a small object returned per method.

text
function classify_investor_fit(method_name):
    if method_name == "CAN_SLIM":
        return {
            "for": [
                "Active traders and aggressive growth investors",
                "Users comfortable with short‑ to medium‑term holding periods",
                "People willing to follow strict buy/sell rules and monitor markets frequently"
            ],
            "not_for": [
                "Classic long‑term buy‑and‑hold investors seeking low turnover",
                "Very risk‑averse investors who dislike frequent stop‑losses",
                "Anyone unable to track market direction and price/volume regularly"
            ],
            "summary": "Aggressive, rules‑based growth system best for high risk tolerance and short‑ to medium‑term horizons, not 'buy forever' investors."
        }