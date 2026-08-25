from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ApprovalCalibration:
    confidence_threshold: float
    validation_auto_approval_rate: float
    validation_auto_p90_ape: float


def apply_price_policy(
    quotes: pd.DataFrame,
    predictions: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    output = quotes.copy()
    output = output.join(predictions)
    min_margin = output["customer_tier"].map(config["min_margin_by_tier"]).astype(float)
    max_discount = output["customer_tier"].map(config["max_discount_by_tier"]).astype(float)

    output["margin_floor_price"] = output["unit_cost_usd"] / (1 - min_margin)
    output["discount_floor_price"] = output["list_price_usd"] * (1 - max_discount)
    output["policy_floor_price"] = output[["margin_floor_price", "discount_floor_price"]].max(axis=1)
    output["policy_ceiling_price"] = output["list_price_usd"] * 1.12
    output["recommended_unit_price"] = output["pred_q50"].clip(
        lower=output["policy_floor_price"], upper=output["policy_ceiling_price"]
    )
    output["recommended_unit_price"] = output["recommended_unit_price"].round(2)
    output["recommended_quote_value"] = output["recommended_unit_price"] * output["quantity"]
    output["expected_margin_pct"] = (
        output["recommended_unit_price"] - output["unit_cost_usd"]
    ) / output["recommended_unit_price"]
    output["normalized_interval_width"] = (
        (output["pred_q90"] - output["pred_q10"]) / output["pred_q50"].clip(lower=0.01)
    ).clip(lower=0)
    output["confidence_score"] = np.exp(-2.5 * output["normalized_interval_width"]).clip(0, 1)

    output["data_quality_pass"] = (
        output["list_price_usd"].gt(0)
        & output["unit_cost_usd"].gt(0)
        & output["quantity"].between(1, 2_500)
        & output["market"].notna()
    )
    output["financial_policy_pass"] = (
        output["expected_margin_pct"].ge(min_margin - 1e-8)
        & output["recommended_unit_price"].ge(output["discount_floor_price"] - 0.01)
    )
    output["risk_policy_pass"] = (
        output["recommended_quote_value"].le(config["max_quote_value_for_auto_approval_usd"])
        & output["cost_change_pct"].abs().le(config["max_cost_change_pct"])
        & output["inventory_weeks"].ge(config["min_inventory_weeks"])
        & output["sku_history_count"].ge(config["min_history_count"])
        & ~output["is_strategic"]
    )
    output["policy_eligible"] = (
        output["data_quality_pass"]
        & output["financial_policy_pass"]
        & output["risk_policy_pass"]
        & output["normalized_interval_width"].le(config["max_normalized_interval_width"])
    )
    return output


def calibrate_approval_threshold(
    validation: pd.DataFrame,
    target_rate: float,
    max_p90_ape: float,
) -> ApprovalCalibration:
    scored = validation[validation["accepted_unit_price_usd"].notna()].copy()
    scored["ape"] = (
        (scored["recommended_unit_price"] - scored["accepted_unit_price_usd"]).abs()
        / scored["accepted_unit_price_usd"].clip(lower=0.01)
    )
    eligible = scored[scored["policy_eligible"]]
    if eligible.empty:
        return ApprovalCalibration(1.0, 0.0, float("nan"))

    candidates = np.unique(np.quantile(eligible["confidence_score"], np.linspace(0.0, 1.0, 401)))
    best: tuple[float, float, float] | None = None
    for threshold in candidates:
        approved = scored["policy_eligible"] & scored["confidence_score"].ge(threshold)
        rate = float(approved.mean())
        p90 = float(scored.loc[approved, "ape"].quantile(0.90)) if approved.any() else float("nan")
        if approved.any() and p90 <= max_p90_ape:
            candidate = (abs(rate - target_rate), -rate, float(threshold))
            if best is None or candidate < best:
                best = candidate

    if best is None:
        threshold = float(eligible["confidence_score"].quantile(0.95))
    else:
        threshold = best[2]
    approved = scored["policy_eligible"] & scored["confidence_score"].ge(threshold)
    rate = float(approved.mean())
    p90 = float(scored.loc[approved, "ape"].quantile(0.90)) if approved.any() else float("nan")
    return ApprovalCalibration(threshold, rate, p90)


def finalize_decisions(
    scored: pd.DataFrame,
    calibration: ApprovalCalibration,
    config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    output = scored.copy()
    config = config or {
        "max_quote_value_for_auto_approval_usd": 250_000,
        "max_cost_change_pct": 0.18,
        "min_inventory_weeks": 1.5,
        "min_history_count": 3,
    }
    output["auto_approved"] = output["policy_eligible"] & output["confidence_score"].ge(
        calibration.confidence_threshold
    )
    output["decision"] = np.where(output["auto_approved"], "AUTO_APPROVE", "MANUAL_REVIEW")

    def reasons(row: pd.Series) -> str:
        if row["auto_approved"]:
            return "ALL_GUARDRAILS_PASS"
        failures: list[str] = []
        if not row["data_quality_pass"]:
            failures.append("DATA_QUALITY")
        if not row["financial_policy_pass"]:
            failures.append("FINANCIAL_POLICY")
        if row["recommended_quote_value"] > config["max_quote_value_for_auto_approval_usd"]:
            failures.append("HIGH_QUOTE_VALUE")
        if abs(row["cost_change_pct"]) > config["max_cost_change_pct"]:
            failures.append("COST_SHOCK")
        if row["inventory_weeks"] < config["min_inventory_weeks"]:
            failures.append("LOW_INVENTORY")
        if row["sku_history_count"] < config["min_history_count"]:
            failures.append("COLD_START")
        if row["is_strategic"]:
            failures.append("STRATEGIC_ACCOUNT")
        if row["confidence_score"] < calibration.confidence_threshold:
            failures.append("LOW_CONFIDENCE")
        return "|".join(failures or ["POLICY_REVIEW"])

    output["reason_codes"] = output.apply(reasons, axis=1)
    return output
