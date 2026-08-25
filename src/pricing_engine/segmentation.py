from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler


SEGMENT_FEATURES = [
    "log_list_price",
    "average_rating",
    "log_rating_count",
    "historical_quote_count",
    "historical_win_rate",
    "historical_avg_quantity",
    "historical_price_ratio",
    "historical_price_volatility",
    "historical_market_count",
]


@dataclass
class SegmentationBundle:
    scaler: StandardScaler
    model: KMeans
    selected_k: int
    selection_scores: dict[int, float]
    cluster_profiles: pd.DataFrame
    sku_assignments: pd.DataFrame


def build_sku_features(catalog: pd.DataFrame, historical_quotes: pd.DataFrame) -> pd.DataFrame:
    won = historical_quotes[historical_quotes["quote_won"]].copy()
    won["price_ratio"] = won["accepted_unit_price_usd"] / won["list_price_usd"]
    history = (
        historical_quotes.groupby("sku_id")
        .agg(
            historical_quote_count=("quote_id", "size"),
            historical_win_rate=("quote_won", "mean"),
            historical_avg_quantity=("quantity", "mean"),
            historical_market_count=("market", "nunique"),
        )
        .join(
            won.groupby("sku_id").agg(
                historical_price_ratio=("price_ratio", "mean"),
                historical_price_volatility=("price_ratio", "std"),
            )
        )
        .reset_index()
    )
    features = catalog.merge(history, on="sku_id", how="left")
    features["log_list_price"] = np.log1p(features["list_price_usd"])
    features["log_rating_count"] = np.log1p(features["rating_count"])
    fill_values = {
        "historical_quote_count": 0,
        "historical_win_rate": historical_quotes["quote_won"].mean(),
        "historical_avg_quantity": historical_quotes["quantity"].median(),
        "historical_price_ratio": 0.90,
        "historical_price_volatility": 0.08,
        "historical_market_count": 0,
    }
    return features.fillna(fill_values)


def fit_segmentation(
    catalog: pd.DataFrame,
    historical_quotes: pd.DataFrame,
    config: dict[str, Any],
    seed: int,
) -> SegmentationBundle:
    sku_features = build_sku_features(catalog, historical_quotes)
    matrix = sku_features[SEGMENT_FEATURES].astype(float).to_numpy()
    scaler = StandardScaler()
    scaled = scaler.fit_transform(matrix)

    sample_size = min(int(config["sample_size_for_selection"]), len(scaled))
    rng = np.random.default_rng(seed)
    sample_indices = rng.choice(len(scaled), size=sample_size, replace=False)
    selection_scores: dict[int, float] = {}
    for k in config["candidate_clusters"]:
        candidate = KMeans(n_clusters=int(k), random_state=seed, n_init=10)
        labels = candidate.fit_predict(scaled)
        selection_scores[int(k)] = float(
            silhouette_score(scaled[sample_indices], labels[sample_indices], sample_size=sample_size)
        )

    selected_k = max(selection_scores, key=selection_scores.get)
    model = KMeans(n_clusters=selected_k, random_state=seed, n_init=20)
    sku_features["cluster_id"] = model.fit_predict(scaled).astype(int)

    cluster_profiles = (
        sku_features.groupby("cluster_id")
        .agg(
            sku_count=("sku_id", "nunique"),
            median_list_price=("list_price_usd", "median"),
            median_rating_count=("rating_count", "median"),
            avg_historical_win_rate=("historical_win_rate", "mean"),
            avg_historical_quantity=("historical_avg_quantity", "mean"),
            avg_historical_price_ratio=("historical_price_ratio", "mean"),
            avg_market_count=("historical_market_count", "mean"),
        )
        .round(4)
        .reset_index()
    )
    sku_assignments = sku_features[["sku_id", "cluster_id"] + SEGMENT_FEATURES].copy()
    return SegmentationBundle(
        scaler=scaler,
        model=model,
        selected_k=selected_k,
        selection_scores=selection_scores,
        cluster_profiles=cluster_profiles,
        sku_assignments=sku_assignments,
    )

