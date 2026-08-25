from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.metrics import mean_absolute_error, mean_pinball_loss


def regression_metrics(scored: pd.DataFrame) -> dict[str, float]:
    observed = scored[scored["accepted_unit_price_usd"].notna()].copy()
    actual = observed["accepted_unit_price_usd"]
    recommendation = observed["recommended_unit_price"]
    ape = (recommendation - actual).abs() / actual.clip(lower=0.01)
    baseline = observed["sku_prior_mean_price"].clip(lower=observed["policy_floor_price"])
    return {
        "won_quote_rows": int(len(observed)),
        "mae_usd": float(mean_absolute_error(actual, recommendation)),
        "median_ape": float(ape.median()),
        "p90_ape": float(ape.quantile(0.90)),
        "q10_pinball_loss": float(mean_pinball_loss(actual, observed["pred_q10"], alpha=0.10)),
        "q50_pinball_loss": float(mean_pinball_loss(actual, observed["pred_q50"], alpha=0.50)),
        "q90_pinball_loss": float(mean_pinball_loss(actual, observed["pred_q90"], alpha=0.90)),
        "q10_q90_coverage": float(
            ((actual >= observed["pred_q10"]) & (actual <= observed["pred_q90"])).mean()
        ),
        "baseline_mae_usd": float(mean_absolute_error(actual, baseline)),
        "mae_improvement_vs_prior_price": float(
            1 - mean_absolute_error(actual, recommendation) / mean_absolute_error(actual, baseline)
        ),
    }


def decision_metrics(
    scored: pd.DataFrame,
    operations: dict[str, Any],
) -> dict[str, float]:
    observed = scored[scored["accepted_unit_price_usd"].notna()].copy()
    auto = observed["auto_approved"]
    auto_ape = (
        (observed.loc[auto, "recommended_unit_price"] - observed.loc[auto, "accepted_unit_price_usd"]).abs()
        / observed.loc[auto, "accepted_unit_price_usd"].clip(lower=0.01)
    )
    rate = float(auto.mean())
    baseline_minutes = float(operations["baseline_manual_minutes"])
    blended_minutes = (
        rate * float(operations["automated_oversight_minutes"])
        + (1 - rate) * float(operations["assisted_review_minutes"])
    )
    return {
        "auto_approval_rate": rate,
        "auto_approved_rows": int(auto.sum()),
        "manual_review_rows": int((~auto).sum()),
        "auto_subset_median_ape": float(auto_ape.median()) if len(auto_ape) else float("nan"),
        "auto_subset_p90_ape": float(auto_ape.quantile(0.90)) if len(auto_ape) else float("nan"),
        "baseline_minutes_per_quote": baseline_minutes,
        "blended_minutes_per_quote": blended_minutes,
        "estimated_throughput_multiplier": baseline_minutes / blended_minutes,
    }


def slice_metrics(scored: pd.DataFrame, column: str) -> pd.DataFrame:
    observed = scored[scored["accepted_unit_price_usd"].notna()].copy()
    observed["ape"] = (
        (observed["recommended_unit_price"] - observed["accepted_unit_price_usd"]).abs()
        / observed["accepted_unit_price_usd"].clip(lower=0.01)
    )
    return (
        observed.groupby(column, dropna=False)
        .agg(
            rows=("quote_id", "size"),
            auto_approval_rate=("auto_approved", "mean"),
            median_ape=("ape", "median"),
            p90_ape=("ape", lambda values: values.quantile(0.90)),
            interval_coverage=(
                "accepted_unit_price_usd",
                lambda values: float(
                    (
                        (values >= observed.loc[values.index, "pred_q10"])
                        & (values <= observed.loc[values.index, "pred_q90"])
                    ).mean()
                ),
            ),
        )
        .reset_index()
        .round(5)
    )


def save_evaluation_charts(
    scored: pd.DataFrame,
    feature_importance: pd.DataFrame,
    cluster_profiles: pd.DataFrame,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid", context="notebook")
    observed = scored[scored["accepted_unit_price_usd"].notna()].copy()
    observed["ape"] = (
        (observed["recommended_unit_price"] - observed["accepted_unit_price_usd"]).abs()
        / observed["accepted_unit_price_usd"].clip(lower=0.01)
    )

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    sample = observed.sample(min(8_000, len(observed)), random_state=42)
    axes[0].scatter(
        sample["accepted_unit_price_usd"], sample["recommended_unit_price"],
        alpha=0.22, s=10, color="#0066cc",
    )
    upper = float(np.quantile(sample[["accepted_unit_price_usd", "recommended_unit_price"]].to_numpy(), 0.98))
    axes[0].plot([0, upper], [0, upper], linestyle="--", color="#d62728")
    axes[0].set(xlim=(0, upper), ylim=(0, upper), xlabel="Observed accepted price (USD)",
                ylabel="Recommended price (USD)", title="Temporal holdout: recommendation vs. outcome")

    market = slice_metrics(observed.assign(auto_approved=observed["auto_approved"]), "market")
    market = market.sort_values("auto_approval_rate", ascending=False)
    sns.barplot(data=market, x="market", y="auto_approval_rate", ax=axes[1], color="#0055a4")
    axes[1].axhline(observed["auto_approved"].mean(), linestyle="--", color="#d62728")
    axes[1].set(title="Auto-approval by market", xlabel="Market", ylabel="Auto-approval rate", ylim=(0, 1))
    fig.tight_layout()
    fig.savefig(output_dir / "holdout_performance.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    top = feature_importance.head(16).sort_values("importance")
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.barh(top["feature"], top["importance"], color="#3a86ff")
    ax.set(title="Median quantile model: top feature importance", xlabel="XGBoost gain proxy")
    fig.tight_layout()
    fig.savefig(output_dir / "feature_importance.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5))
    sns.scatterplot(
        data=cluster_profiles,
        x="median_list_price",
        y="avg_historical_quantity",
        size="sku_count",
        hue="cluster_id",
        palette="tab10",
        sizes=(120, 700),
        ax=ax,
    )
    ax.set(xscale="log", title="SKU behavioral segments", xlabel="Median list price (log USD)",
           ylabel="Average historical quote quantity")
    fig.tight_layout()
    fig.savefig(output_dir / "sku_segments.png", dpi=170, bbox_inches="tight")
    plt.close(fig)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    def convert(value: Any) -> Any:
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating,)):
            return None if np.isnan(value) else float(value)
        if isinstance(value, dict):
            return {str(key): convert(item) for key, item in value.items()}
        if isinstance(value, list):
            return [convert(item) for item in value]
        return value

    with path.open("w", encoding="utf-8") as handle:
        json.dump(convert(payload), handle, indent=2, allow_nan=False)

