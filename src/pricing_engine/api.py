from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Literal

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from pricing_engine.config import load_config
from pricing_engine.guardrails import ApprovalCalibration, apply_price_policy, finalize_decisions
from pricing_engine.modeling import predict_quantiles


ROOT = Path(__file__).resolve().parents[2]


class QuoteRequest(BaseModel):
    sku_id: str
    market: Literal["UK", "IE", "DE", "FR", "NL", "ES", "BE", "CH", "PT"]
    quantity: int = Field(ge=1, le=2_500)
    customer_tier: Literal["channel", "mid_market", "enterprise", "strategic"]
    is_contract_customer: bool = False
    inventory_weeks: float = Field(default=4.0, ge=0, le=52)
    cost_change_pct: float = Field(default=0.0, ge=-0.50, le=1.0)
    contract_discount_pct: float = Field(default=0.0, ge=0, le=0.50)
    customer_revenue_gbp: float = Field(default=100_000, ge=0)
    customer_orders: int = Field(default=12, ge=0)
    customer_tenure_months: float = Field(default=24, ge=0)


class QuoteResponse(BaseModel):
    quote_timestamp: datetime
    sku_id: str
    market: str
    quantity: int
    lower_price: float
    recommended_unit_price: float
    upper_price: float
    recommended_quote_value: float
    expected_margin_pct: float
    confidence_score: float
    decision: str
    reason_codes: list[str]
    model_version: str


@lru_cache(maxsize=1)
def load_artifacts() -> dict[str, object]:
    model_dir = ROOT / "artifacts/models"
    config = load_config(ROOT / "configs/base.yaml")
    model = joblib.load(model_dir / "quantile_model_bundle.joblib")
    calibration_dict = joblib.load(model_dir / "approval_calibration.joblib")
    calibration = ApprovalCalibration(**calibration_dict)
    catalog = pd.read_parquet(ROOT / config["data"]["catalog_path"]).set_index("sku_id")
    assignments = pd.read_parquet(model_dir / "sku_cluster_assignments.parquet").set_index("sku_id")
    seasonality = pd.read_csv(ROOT / "data/processed/seasonality.csv").set_index("month")
    return {
        "config": config,
        "model": model,
        "calibration": calibration,
        "catalog": catalog,
        "assignments": assignments,
        "seasonality": seasonality,
    }


def _feature_row(request: QuoteRequest, artifacts: dict[str, object]) -> pd.DataFrame:
    catalog: pd.DataFrame = artifacts["catalog"]  # type: ignore[assignment]
    assignments: pd.DataFrame = artifacts["assignments"]  # type: ignore[assignment]
    seasonality: pd.DataFrame = artifacts["seasonality"]  # type: ignore[assignment]
    if request.sku_id not in catalog.index:
        raise HTTPException(status_code=404, detail="Unknown SKU")

    sku = catalog.loc[request.sku_id]
    assignment = assignments.loc[request.sku_id]
    now = datetime.now(timezone.utc)
    cost_ratio = {
        "GPU_AND_GRAPHICS": 0.58,
        "CPU_AND_PROCESSOR": 0.54,
        "SERVER_AND_ACCELERATOR": 0.49,
        "MOTHERBOARD": 0.63,
        "MEMORY_AND_STORAGE": 0.66,
        "NETWORKING": 0.61,
        "WORKSTATION_AND_PC": 0.70,
        "THERMAL_AND_POWER": 0.64,
        "OTHER_COMPUTE": 0.65,
    }[sku["product_family"]]
    base_cost = float(sku["list_price_usd"]) * cost_ratio
    history_count = int(assignment["historical_quote_count"])
    demand = float(seasonality.loc[now.month, "demand_index"])
    row = {
        **sku.to_dict(),
        "quote_id": "API-PREVIEW",
        "quote_date": pd.Timestamp(now.replace(tzinfo=None)),
        "market": request.market,
        "quantity": request.quantity,
        "log_quantity": np.log1p(request.quantity),
        "log_rating_count": np.log1p(float(sku["rating_count"])),
        "customer_tier": request.customer_tier,
        "is_contract_customer": request.is_contract_customer,
        "is_strategic": request.customer_tier == "strategic",
        "inventory_weeks": request.inventory_weeks,
        "cost_change_pct": request.cost_change_pct,
        "unit_cost_usd": base_cost * (1 + request.cost_change_pct),
        "contract_discount_pct": request.contract_discount_pct,
        "customer_revenue_gbp": request.customer_revenue_gbp,
        "customer_orders": request.customer_orders,
        "customer_lines": max(request.customer_orders, 1),
        "customer_tenure_months": request.customer_tenure_months,
        "market_demand_index": demand,
        "sku_history_count": history_count,
        "customer_history_count": request.customer_orders,
        "sku_prior_mean_price": float(sku["list_price_usd"]) * float(assignment["historical_price_ratio"]),
        "customer_prior_win_rate": float(assignment["historical_win_rate"]),
        "days_since_launch": 900,
        "quote_month": now.month,
        "quote_quarter": (now.month - 1) // 3 + 1,
        "quote_year": 2025,
        "cluster_id": int(assignment["cluster_id"]),
        "quote_won": False,
        "accepted_unit_price_usd": np.nan,
    }
    return pd.DataFrame([row])


app = FastAPI(
    title="Enterprise Pricing Recommendation API",
    version="0.1.0",
    description="Reproducible public-data pricing recommendation case study.",
)


@app.get("/health")
def health() -> dict[str, object]:
    artifacts = load_artifacts()
    catalog: pd.DataFrame = artifacts["catalog"]  # type: ignore[assignment]
    return {"status": "ok", "model_version": "0.1.0", "catalog_skus": len(catalog)}


@app.post("/v1/recommend", response_model=QuoteResponse)
def recommend(request: QuoteRequest) -> QuoteResponse:
    artifacts = load_artifacts()
    frame = _feature_row(request, artifacts)
    predictions = predict_quantiles(artifacts["model"], frame)  # type: ignore[arg-type]
    config = artifacts["config"]  # type: ignore[assignment]
    scored = apply_price_policy(frame, predictions, config["guardrails"])
    decided = finalize_decisions(scored, artifacts["calibration"], config["guardrails"])  # type: ignore[arg-type]
    row = decided.iloc[0]
    return QuoteResponse(
        quote_timestamp=datetime.now(timezone.utc),
        sku_id=request.sku_id,
        market=request.market,
        quantity=request.quantity,
        lower_price=round(float(row["pred_q10"]), 2),
        recommended_unit_price=round(float(row["recommended_unit_price"]), 2),
        upper_price=round(float(row["pred_q90"]), 2),
        recommended_quote_value=round(float(row["recommended_quote_value"]), 2),
        expected_margin_pct=round(float(row["expected_margin_pct"]), 4),
        confidence_score=round(float(row["confidence_score"]), 4),
        decision=str(row["decision"]),
        reason_codes=str(row["reason_codes"]).split("|"),
        model_version="0.1.0",
    )
