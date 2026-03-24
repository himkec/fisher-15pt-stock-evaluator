1. Intrinsic Value Module – Overview
Goal: Given a ticker and assumptions, compute an intrinsic value range and margin of safety using one or more valuation methods:

Free‑cash‑flow DCF

Dividend Discount Model (DDM; Gordon / multi‑period)

Residual Income Model (RIM)

Graham‑style formulas (Graham Number and related checks)

The app should:

Expose each method as a selectable sub‑analysis.

Share core data (statements, price, shares).

Output method‑specific values plus a combined “football field” band.

2. Common Data Requirements
For each stock:

Income statement history (ideally 5–10 years):

Revenue, operating income, net income, EPS (basic/diluted).

Balance sheet:

Total assets, total liabilities, shareholders’ equity, book value per share.

Cash flow:

CFO, capex, dividends paid (per share and total).

Market data:

Current price, market cap, shares outstanding, beta (if using CAPM), risk‑free rate (from macro feed), equity risk premium assumption.

Configuration:

Default discount/required return (e.g., 8–12%).

Default long‑run growth bounds (e.g., 0–3% real plus inflation).

3. FCF Discounted Cash Flow (DCF) Sub‑Module
3.1 Purpose
Estimate equity value by discounting future free cash flows to equity or firm plus a terminal value.

3.2 Steps
Normalize base year cash flow

Compute free cash flow (FCF) = CFO − capex (or unlevered FCF depending on convention).

Adjust for one‑offs (non‑recurring items, huge working capital swings).

Use last year, average of last 3 years, or a “normalized” figure as FCF₀.

Derive explicit forecast assumptions

Project revenue growth and margins (or directly FCF growth) over 5–10 years.

Options:

User‑entered growth rates.

Blend of historical CAGR and analyst estimates, capped at sensible levels.

Compute annual FCF forecasts

For year t in 1…N: forecast FCFₜ using chosen growth/margin profile.

Set discount rate and terminal growth

Use WACC or cost of equity; default from CAPM (risk‑free + beta × equity risk premium).

Set long‑run terminal growth g (e.g., 1–3% nominal or slightly above inflation).

Calculate terminal value

Terminal FCF = FCF in final forecast year × (1 + g).

Terminal Value = Terminal FCF / (r − g), where r is discount rate.

Discount and sum

Discount each FCFₜ and terminal value back to present at r.

Sum to get enterprise or equity value, then:

If EV: subtract net debt and divide by shares.

If equity FCF: divide directly by shares.

Scenario analysis

At minimum: Bear / Base / Bull with different growth and margins.

Output intrinsic value range across scenarios.

3.3 Outputs
Per‑share intrinsic values (Bear/Base/Bull).

Implied upside/downside vs current price.

Margin of safety for each scenario.

Key assumptions panel (growth, discount rate, terminal growth).

4. Dividend Discount Model (DDM) Sub‑Module
4.1 Purpose
Value dividend‑paying stocks as the present value of all future dividends per share, using Gordon Growth (stable) or multi‑period variants.

4.2 Steps
Identify dividend profile

Determine if company has stable, growing, or irregular dividends.

Compute current dividend per share and 5‑year dividend CAGR.

Choose DDM variant

Gordon Growth Model for stable, mature dividend growers:

Inputs: next‑year dividend D₁, required return r, perpetual growth g.

Multi‑period DDM for finite holding period: forecast dividends for N years plus a terminal selling price or terminal DDM.

Parameter selection

D₁: last dividend × (1 + near‑term growth estimate).

r: cost of equity / required return (user configurable).

g: sustainable long‑term dividend growth, typically ≤ nominal GDP growth.

Valuation formulas (conceptual)

Gordon: intrinsic value ≈ D₁ ÷ (r − g).

Multi‑period: intrinsic value = discounted sum of D₁..Dₙ + discounted terminal value (e.g., sale price or Gordon formula at year N).

Safety checks

Validate that r > g; otherwise flag model as invalid.

Compare implied return roughly to dividend yield + dividend growth.
​

4.3 Outputs
DDM fair value per share (Base, optional Bear/Bull by varying g and r).

Comparison with current price (undervalued / fair / overvalued).

Yield + growth heuristic: approximate long‑term expected return.
​

5. Residual Income Model (RIM) Sub‑Module
5.1 Purpose
Value equity as book value plus present value of future residual income, where residual income = net income − equity charge.

5.2 Key definitions
Equity charge = book value of equity × cost of equity.

Residual income = net income − equity charge.

Intrinsic equity value = current book value + PV of all future residual incomes.

5.3 Steps
Gather inputs

Current book value of equity (BV₀) and BV per share.

Forecast net income (or EPS) for each year in explicit forecast period.

Cost of equity rₑ (e.g., via CAPM).

Set forecast horizon & terminal assumption

Explicit residual income forecasts for 3–10 years.

Terminal period assumption: constant growth in residual income, or convergence to zero over time.
​

Calculate annual residual income

For each year t:

Equity chargeₜ = BVₜ₋₁ × rₑ.

Residual incomeₜ = Net incomeₜ − Equity chargeₜ.

Update BVₜ each year: BVₜ = BVₜ₋₁ + Net incomeₜ − Dividendsₜ.

Discount residual incomes

Discount each residual incomeₜ by (1 + rₑ)ᵗ.

Terminal residual value

If using constant‑growth terminal residual income, compute terminal value as the PV of a growing perpetuity of residual income starting at year T+1, or use a simplified residual value formula.

Compute intrinsic equity value

Intrinsic equity value ≈ BV₀ + sum of discounted residual incomes (explicit period + terminal).

Divide by shares for per‑share intrinsic value.

5.4 Outputs
Residual‑income intrinsic value per share (Base scenario, optional Bear/Bull).

Contribution breakdown: current BV vs PV of residuals.

Comparison vs price and other methods.

6. Graham‑Style Formulas Sub‑Module (including Graham Number)
6.1 Purpose
Provide simple, conservative fair‑value checks based on Graham’s defensive investing criteria; much lighter‑weight than full DCF/RIM.

6.2 Graham Number
Inputs

Earnings per share (EPS), typically trailing 12‑month or average EPS over 3 years.

Book value per share (BVPS).

Formula (conceptual)

Graham Number ≈ square root of (22.5 × EPS × BVPS).

The constant 22.5 = 15 (max P/E Graham liked) × 1.5 (max P/B).

Interpretation

If Price < Graham Number → potentially undervalued.

Price ≈ Graham Number → roughly fairly valued.

Price > Graham Number → above Graham’s conservative ceiling.

Price‑to‑Graham‑Number ratio

Ratio = Price / Graham Number.
​

Use thresholds:

< 1.0: discount vs Graham ceiling.

≈ 1.0: at ceiling.

1.0: premium to ceiling.

6.3 Optional broader Graham checks
If you want to align more with Graham’s original defensive criteria, add optional filters:
​

Size: minimum sales/assets.

Financial condition: current ratio, debt vs working capital / equity.

Earnings stability: positive EPS over last 10 years.

Dividend record: uninterrupted dividends for 20+ years.

Earnings growth: growth in EPS over a decade.

P/E and P/B caps consistent with Graham Number logic.

The app can show which of these conditions the stock passes/fails.

6.4 Outputs
Graham Number per share and Price / Graham Number.

Pass/fail flags for optional Graham criteria.

Simple label: “Below Graham ceiling / At Graham ceiling / Above Graham ceiling”.

7. Aggregation & App Integration
7.1 Module configuration
For the Intrinsic Value family, define:

method_id: DCF_FCF, DDM_Gordon, DDM_MultiPeriod, RIM, GRAHAM_NUMBER.

Required input fields (so you can show “data available / missing”).

Tunable parameters (growth bands, discount rate, horizon).

7.2 Combined “football field” view
When multiple sub‑modules run:

Collect per‑share fair values from each method.

Show them as a horizontal band/range chart with current price.

Optionally show a “consensus” midpoint or median.

7.3 “Who this method is for” (short UI text)
For the whole intrinsic value family:

For:

Long‑term investors and analysts who think in cash flows and required returns.

People comfortable with assumption‑driven models and scenario analysis.

Not for:

Day traders and very short‑term momentum players.

Users looking for purely mechanical yes/no outputs without understanding assumptions.