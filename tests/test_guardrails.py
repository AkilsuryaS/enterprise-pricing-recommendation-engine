from __future__ import annotations

import pandas as pd

from pricing_engine.guardrails import ApprovalCalibration, apply_price_policy, finalize_decisions


CONFIG = {
    "min_margin_by_tier": {"strategic": 0.10, "enterprise": 0.14, "mid_market": 0.18, "channel": 0.12},
    "max_discount_by_tier": {"strategic": 0.32, "enterprise": 0.25, "mid_market": 0.18, "channel": 0.28},
    "max_quote_value_for_auto_approval_usd": 250_000,
    "max_cost_change_pct": 0.18,
    "min_inventory_weeks": 1.5,
    "min_history_count": 3,
    "max_normalized_interval_width": 0.35,
}


def quote_row(**overrides: object) -> dict[str, object]:
    row = {
        "list_price_usd": 100.0,
        "unit_cost_usd": 60.0,
        "quantity": 10,
        "market": "DE",
        "customer_tier": "enterprise",
        "cost_change_pct": 0.02,
        "inventory_weeks": 5.0,
        "sku_history_count": 15,
        "is_strategic": False,
        "accepted_unit_price_usd": 82.0,
    }
    row.update(overrides)
    return row


def test_margin_floor_overrides_unsafe_model_price() -> None:
    quotes = pd.DataFrame([quote_row()])
    predictions = pd.DataFrame([{"pred_q10": 65.0, "pred_q50": 68.0, "pred_q90": 90.0}])
    scored = apply_price_policy(quotes, predictions, CONFIG)
    expected_floor = 60 / (1 - 0.14)
    assert scored.loc[0, "recommended_unit_price"] >= round(expected_floor, 2)
    assert scored.loc[0, "financial_policy_pass"]


def test_strategic_account_is_never_auto_approved() -> None:
    quotes = pd.DataFrame([quote_row(customer_tier="strategic", is_strategic=True)])
    predictions = pd.DataFrame([{"pred_q10": 78.0, "pred_q50": 82.0, "pred_q90": 86.0}])
    scored = apply_price_policy(quotes, predictions, CONFIG)
    decision = finalize_decisions(scored, ApprovalCalibration(0.0, 0.0, 0.0), CONFIG)
    assert decision.loc[0, "decision"] == "MANUAL_REVIEW"
    assert "STRATEGIC_ACCOUNT" in decision.loc[0, "reason_codes"]


def test_wide_interval_routes_to_review() -> None:
    quotes = pd.DataFrame([quote_row()])
    predictions = pd.DataFrame([{"pred_q10": 50.0, "pred_q50": 80.0, "pred_q90": 115.0}])
    scored = apply_price_policy(quotes, predictions, CONFIG)
    decision = finalize_decisions(scored, ApprovalCalibration(0.2, 0.0, 0.0), CONFIG)
    assert not decision.loc[0, "auto_approved"]

