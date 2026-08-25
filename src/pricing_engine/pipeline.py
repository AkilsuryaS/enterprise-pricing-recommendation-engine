from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from pricing_engine.data_pipeline import prepare_case_study_data
from pricing_engine.evaluation import (
    decision_metrics,
    regression_metrics,
    save_evaluation_charts,
    slice_metrics,
    write_json,
)
from pricing_engine.guardrails import (
    apply_price_policy,
    calibrate_approval_threshold,
    finalize_decisions,
)
from pricing_engine.modeling import (
    feature_importance,
    fit_quantile_models,
    predict_quantiles,
    temporal_split,
)
from pricing_engine.segmentation import fit_segmentation


def run_pipeline(config: dict[str, Any], root: Path) -> dict[str, Any]:
    seed = int(config["project"]["seed"])
    data = prepare_case_study_data(config, root)
    catalog = data["catalog"]
    quotes = data["quotes"]
    markets = data["markets"]

    train, validation, test, cutoffs = temporal_split(quotes)
    segmentation = fit_segmentation(catalog, train, config["segmentation"], seed)
    cluster_map = segmentation.sku_assignments[["sku_id", "cluster_id"]]
    train = train.merge(cluster_map, on="sku_id", how="left", validate="many_to_one")
    validation = validation.merge(cluster_map, on="sku_id", how="left", validate="many_to_one")
    test = test.merge(cluster_map, on="sku_id", how="left", validate="many_to_one")

    model_bundle = fit_quantile_models(train, config["model"], seed)
    validation_predictions = predict_quantiles(model_bundle, validation)
    test_predictions = predict_quantiles(model_bundle, test)
    validation_scored = apply_price_policy(validation, validation_predictions, config["guardrails"])
    test_scored = apply_price_policy(test, test_predictions, config["guardrails"])

    calibration = calibrate_approval_threshold(
        validation_scored,
        target_rate=float(config["project"]["target_auto_approval_rate"]),
        max_p90_ape=float(config["guardrails"]["max_validation_p90_ape"]),
    )
    validation_scored = finalize_decisions(validation_scored, calibration, config["guardrails"])
    test_scored = finalize_decisions(test_scored, calibration, config["guardrails"])

    importance = feature_importance(model_bundle)
    test_market_metrics = slice_metrics(test_scored, "market")
    test_cluster_metrics = slice_metrics(test_scored, "cluster_id")
    test_family_metrics = slice_metrics(test_scored, "product_family")

    artifacts = root / "artifacts"
    model_dir = artifacts / "models"
    report_dir = artifacts / "reports"
    chart_dir = artifacts / "charts"
    model_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    chart_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(model_bundle, model_dir / "quantile_model_bundle.joblib", compress=3)
    joblib.dump(segmentation, model_dir / "segmentation_bundle.joblib", compress=3)
    joblib.dump(asdict(calibration), model_dir / "approval_calibration.joblib")
    segmentation.sku_assignments.to_parquet(model_dir / "sku_cluster_assignments.parquet", index=False)

    importance.to_csv(report_dir / "feature_importance.csv", index=False)
    segmentation.cluster_profiles.to_csv(report_dir / "cluster_profiles.csv", index=False)
    test_market_metrics.to_csv(report_dir / "metrics_by_market.csv", index=False)
    test_cluster_metrics.to_csv(report_dir / "metrics_by_cluster.csv", index=False)
    test_family_metrics.to_csv(report_dir / "metrics_by_product_family.csv", index=False)
    decision_columns = [
        "quote_id", "quote_date", "sku_id", "title", "market", "customer_tier", "quantity",
        "list_price_usd", "unit_cost_usd", "pred_q10", "pred_q50", "pred_q90",
        "recommended_unit_price", "expected_margin_pct", "confidence_score", "decision",
        "reason_codes", "accepted_unit_price_usd", "quote_won", "cluster_id",
    ]
    test_scored[decision_columns].sample(
        min(2_000, len(test_scored)), random_state=seed
    ).sort_values("quote_date").to_csv(report_dir / "sample_quote_decisions.csv", index=False)

    metrics = {
        "scope": {
            "catalog_skus": int(catalog["sku_id"].nunique()),
            "markets": int(quotes["market"].nunique()),
            "quote_rows": int(len(quotes)),
            "won_quote_rate": float(quotes["quote_won"].mean()),
            "source_transaction_rows": 1_067_371,
        },
        "temporal_split": {
            **cutoffs,
            "train_rows": int(len(train)),
            "validation_rows": int(len(validation)),
            "test_rows": int(len(test)),
        },
        "segmentation": {
            "selected_k": int(segmentation.selected_k),
            "silhouette_scores": segmentation.selection_scores,
        },
        "approval_calibration": asdict(calibration),
        "test_regression": regression_metrics(test_scored),
        "test_decisions": decision_metrics(test_scored, config["operations"]),
        "market_mix": markets[["market", "transaction_share", "cancellation_rate"]].to_dict("records"),
    }
    write_json(report_dir / "metrics.json", metrics)
    save_evaluation_charts(test_scored, importance, segmentation.cluster_profiles, chart_dir)
    return metrics
