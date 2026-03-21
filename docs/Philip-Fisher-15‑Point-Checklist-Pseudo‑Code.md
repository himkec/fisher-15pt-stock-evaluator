Philip Fisher 15‑Point Checklist (Pseudo‑Code)
Overview
text
function evaluate_company_for_investment(company):
    scorecard = {}

    scorecard["1_growth_potential"]          = check_growth_potential(company)
    scorecard["2_innovation_drive"]          = check_innovation_drive(company)
    scorecard["3_RnD_effectiveness"]         = check_RnD_effectiveness(company)
    scorecard["4_sales_organization"]        = check_sales_organization(company)
    scorecard["5_profit_margin_level"]       = check_profit_margin_level(company)
    scorecard["6_profit_margin_trend"]       = check_profit_margin_trend(company)
    scorecard["7_labor_relations"]           = check_labor_relations(company)
    scorecard["8_executive_relations"]       = check_executive_relations(company)
    scorecard["9_management_depth"]          = check_management_depth(company)
    scorecard["10_cost_controls"]            = check_cost_controls(company)
    scorecard["11_industry_characteristics"] = check_industry_characteristics(company)
    scorecard["12_long_term_outlook"]        = check_long_term_outlook(company)
    scorecard["13_equity_financing_needs"]   = check_equity_financing_needs(company)
    scorecard["14_management_candor"]        = check_management_candor(company)
    scorecard["15_management_integrity"]     = check_management_integrity(company)

    overall_rating = aggregate_scores(scorecard)
    decision       = decide_invest_or_pass(overall_rating, scorecard)

    return decision, scorecard
1. Growth potential of products/services
text
function check_growth_potential(company):
    // Question: "Does the company have products or services with sufficient market potential to make possible a sizable increase in sales for at least several years?" [web:16][web:18][web:19][web:26][web:27]

    market_is_growing      = assess_industry_growth(company.industry)
    product_fit_is_strong  = assess_product_market_fit(company.products)
    runway_is_long         = estimate_sales_runway(years_forward = 5+)

    if market_is_growing and product_fit_is_strong and runway_is_long:
        return "strong"
    else if some_factors_positive:
        return "average"
    else:
        return "weak"
2. Ongoing innovation drive
text
function check_innovation_drive(company):
    // Question: "Does management have a determination to continue to develop products or processes that will still further increase total sales potential once current lines mature?" [web:16][web:18][web:19][web:26][web:27]

    has_clear_product_pipeline   = review_product_pipeline(company)
    reinvests_in_innovation      = inspect_capex_and_RnD_allocations(company)
    culture_supports_experiment  = analyze_culture_for_innovation_signals(company)

    if has_clear_product_pipeline and reinvests_in_innovation and culture_supports_experiment:
        return "strong"
    else if at_least_one_positive:
        return "average"
    else:
        return "weak"
3. Effectiveness of R&D
text
function check_RnD_effectiveness(company):
    // Question: "How effective are the company's research and development efforts in relation to its size?" [web:16][web:18][web:19][web:22][web:26][web:27]

    RnD_spend_vs_peers        = compare_RnD_intensity(company, peers)
    RnD_output_quality        = track_RnD_outcomes(new_products, patents, process_improvements)
    commercial_success_rate   = evaluate_product_success_rate_from_RnD(company)

    if RnD_spend_vs_peers is "rational_or_above" and RnD_output_quality is "high" and commercial_success_rate is "high":
        return "strong"
    else if mixed_results:
        return "average"
    else:
        return "weak"
4. Quality of sales organization
text
function check_sales_organization(company):
    // Question: "Does the company have an above‑average sales organization?" [web:16][web:18][web:19][web:22][web:27]

    sales_force_capability     = assess_sales_force_training_and_experience(company)
    distribution_efficiency    = assess_distribution_channels(company)
    sales_metrics_trend        = review_sales_conversion_and_retention_metrics(company)

    if sales_force_capability is "above_average" and distribution_efficiency is "high" and sales_metrics_trend is "improving":
        return "strong"
    else if some_strengths:
        return "average"
    else:
        return "weak"
5. Profit margin level
text
function check_profit_margin_level(company):
    // Question: "Does the company have a worthwhile profit margin?" [web:16][web:18][web:19][web:26][web:27]

    gross_margin_vs_peers      = compare_margin(company.gross_margin, peers)
    operating_margin_vs_peers  = compare_margin(company.operating_margin, peers)
    structural_moat_signals    = look_for_pricing_power_and_cost_advantages(company)

    if margins_consistently_above_peers and structural_moat_signals:
        return "strong"
    else if margins_around_peer_average:
        return "average"
    else:
        return "weak"
6. Margin stability and improvement
text
function check_profit_margin_trend(company):
    // Question: "What is the company doing to maintain or improve profit margins?" [web:16][web:18][web:19][web:26][web:27]

    margin_trend              = analyze_margin_trend(company, years = 5)
    cost_efficiency_programs  = evaluate_cost_reduction_and_process_improvement_plans(company)
    value_add_initiatives     = review_initiatives_to_increase_pricing_power(company)

    if margin_trend is "stable_or_rising" and (cost_efficiency_programs or value_add_initiatives):
        return "strong"
    else if plan_exists_but_execution_mixed:
        return "average"
    else:
        return "weak"
7. Labor and personnel relations
text
function check_labor_relations(company):
    // Question: "Does the company have outstanding labor and personnel relations?" [web:16][web:18][web:19][web:22][web:27]

    employee_turnover_rate     = measure_employee_turnover(company)
    employee_engagement        = infer_from_surveys_reviews_and_reputation(company)
    labor_disputes_history     = check_history_of_strikes_or_conflicts(company)

    if low_turnover and high_engagement and minimal_labor_disputes:
        return "strong"
    else if mixed_signals:
        return "average"
    else:
        return "weak"
8. Executive relations
text
function check_executive_relations(company):
    // Question: "Does the company have outstanding executive relations?" [web:16][web:18][web:19][web:22][web:27]

    leadership_cohesion         = evaluate_cohesion_of_top_team(company)
    internal_promotion_record   = see_if_management_promotes_from_within(company)
    compensation_fairness       = review_executive_compensation_vs_results(company)

    if leadership_cohesion is "high" and internal_promotion_record is "strong" and compensation_fairness is "reasonable":
        return "strong"
    else if acceptable_but_not_exemplary:
        return "average"
    else:
        return "weak"
9. Depth of management
text
function check_management_depth(company):
    // Question: "Does the company have depth to its management?" [web:16][web:18][web:19][web:22][web:27]

    key_person_risk            = estimate_dependency_on_few_individuals(company)
    succession_plans_quality   = evaluate_succession_plans(company)
    delegation_and_autonomy    = assess_delegation_structure(company)

    if key_person_risk is "low" and succession_plans_quality is "credible" and delegation_and_autonomy is "healthy":
        return "strong"
    else if some_depth_but_key_risks_present:
        return "average"
    else:
        return "weak"
10. Cost analysis and controls
text
function check_cost_controls(company):
    // Question: "How good are the company’s cost analysis and accounting controls?" [web:16][web:18][web:19][web:22][web:27][web:29]

    quality_of_reporting       = evaluate_internal_reporting_detail_and_timeliness(company)
    unit_cost_visibility       = determine_if_management_knows_unit_economics_well(company)
    evidence_of_cost_discipline= look_for_cost_control_actions_and_track_record(company)

    if reporting_is_high_quality and unit_cost_visibility and strong_cost_discipline:
        return "strong"
    else if adequate_but_improvable:
        return "average"
    else:
        return "weak"
11. Industry characteristics
text
function check_industry_characteristics(company):
    // Question: "Are there other aspects of the business, somewhat peculiar to the industry, which will give the company an important competitive edge?" [web:18][web:19][web:22][web:27][web:29]

    network_effects_or_scale   = analyze_scale_economies_and_network_effects(company.industry)
    regulatory_position        = assess_regulatory_environment_and_company_standing(company)
    structural_advantages      = identify_industry_specific_edges(company)

    if structural_advantages_present and durable:
        return "strong"
    else if some_edges_but_not_durable:
        return "average"
    else:
        return "weak"
12. Long‑term vs short‑term outlook
text
function check_long_term_outlook(company):
    // Question: "Does the company have a short‑range or long‑range outlook in regard to profits?" [web:18][web:19][web:22][web:27][web:29]

    capex_vs_short_term_profit = compare_investment_horizon_to_quarterly_focus(company)
    treatment_of_stakeholders  = examine_treatment_of_customers_suppliers_employees(company)
    commentary_time_horizon    = review_management_discussion_for_time_horizon(company)

    if decisions_prioritize_long_term_value and stakeholder_relations_are_investment_like:
        return "strong"
    else if mixed_signals_between_short_and_long_term:
        return "average"
    else:
        return "weak"
13. Need for equity financing
text
function check_equity_financing_needs(company):
    // Question: "In the foreseeable future, will the growth of the company require sufficient equity financing so that the larger number of shares
    // then outstanding will largely cancel the existing stockholders’ benefit from this anticipated growth?" [web:18][web:19][web:22][web:27][web:29]

    internal_funding_capacity  = estimate_free_cash_flow_and_reinvestment_capability(company)
    historical_dilution        = analyze_past_equity_issuance_and_dilution(company)
    projected_dilution         = model_future_equity_needs_under_growth_plans(company)

    if growth_can_be_funded_with_minimal_dilution:
        return "strong"
    else if some_dilution_but_acceptable_relative_to_growth:
        return "average"
    else:
        return "weak"
14. Management candor with investors
text
function check_management_candor(company):
    // Question: "Does management talk freely to investors about its affairs when times are good AND when they are bad?" [web:18][web:19][web:22][web:27][web:29]

    transparency_in_reporting   = evaluate_clarity_of_annual_reports_and_calls(company)
    handling_of_mistakes        = review_past_crises_for_admission_and_learning(company)
    consistency_of_narrative    = compare_words_to_subsequent_actions(company)

    if reporting_is_clear and mistakes_are_acknowledged and words_align_with_actions:
        return "strong"
    else if somewhat_transparent_but_spin_heavy:
        return "average"
    else:
        return "weak"
15. Management integrity
text
function check_management_integrity(company):
    // Question: "Does the company have a management of unquestionable integrity?" [web:18][web:19][web:22][web:27][web:29]

    related_party_practices      = examine_related_party_transactions_and_perks(company)
    compensation_and_options     = assess_fairness_of_compensation_and_option_grants(company)
    legal_and_ethical_record     = review_legal_issues_regulatory_actions_and_reputation(company)

    if no_material_red_flags and incentives_aligned_with_shareholders and ethical_record_clean:
        return "strong"
    else if minor_issues_but_generally_sound:
        return "average"
    else:
        return "weak"
Aggregation and decision
text
function aggregate_scores(scorecard):
    // Map qualitative ratings to numeric values
    // e.g., "strong" = 2, "average" = 1, "weak" = 0

    numeric_scores = map_ratings_to_numbers(scorecard)
    total_score    = sum(numeric_scores.values)
    max_score      = 2 * number_of_points
    score_ratio    = total_score / max_score

    return { "total": total_score, "ratio": score_ratio }

function decide_invest_or_pass(overall_rating, scorecard):
    if overall_rating.ratio >= 0.75 and no_critical_point_is_weak(scorecard):
        return "buy_or_accumulate"
    else if overall_rating.ratio between 0.5 and 0.75:
        return "watchlist_and_monitor"
    else:
        return "pass"