from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBRegressor


NUMERIC_FEATURES = [
    "list_price_usd",
    "unit_cost_usd",
    "quantity",
    "log_quantity",
    "average_rating",
    "log_rating_count",
    "feature_count",
    "inventory_weeks",
    "cost_change_pct",
    "contract_discount_pct",
    "customer_revenue_gbp",
    "customer_orders",
    "customer_tenure_months",
    "market_demand_index",
    "sku_history_count",
    "customer_history_count",
    "sku_prior_mean_price",
    "customer_prior_win_rate",
    "days_since_launch",
    "quote_month",
    "quote_quarter",
    "quote_year",
    "cluster_id",
]

CATEGORICAL_FEATURES = [
    "market",
    "customer_tier",
    "product_family",
    "is_contract_customer",
    "is_strategic",
]

TARGET = "accepted_unit_price_usd"


@dataclass
class QuantileModelBundle:
    preprocessor: ColumnTransformer
    models: dict[float, XGBRegressor]
    feature_names: list[str]


def temporal_split(
    quotes: pd.DataFrame,
    train_fraction: float = 0.70,
    validation_fraction: float = 0.15,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, str]]:
    ordered_dates = quotes["quote_date"].sort_values().reset_index(drop=True)
    train_cutoff = ordered_dates.iloc[int(len(ordered_dates) * train_fraction)]
    validation_cutoff = ordered_dates.iloc[int(len(ordered_dates) * (train_fraction + validation_fraction))]
    train = quotes[quotes["quote_date"] <= train_cutoff].copy()
    validation = quotes[(quotes["quote_date"] > train_cutoff) & (quotes["quote_date"] <= validation_cutoff)].copy()
    test = quotes[quotes["quote_date"] > validation_cutoff].copy()
    cutoffs = {
        "train_end": str(pd.Timestamp(train_cutoff)),
        "validation_end": str(pd.Timestamp(validation_cutoff)),
        "test_end": str(pd.Timestamp(quotes["quote_date"].max())),
    }
    return train, validation, test, cutoffs


def make_preprocessor() -> ColumnTransformer:
    return ColumnTransformer(
        transformers=[
            ("numeric", StandardScaler(), NUMERIC_FEATURES),
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False, min_frequency=5),
                CATEGORICAL_FEATURES,
            ),
        ],
        remainder="drop",
        verbose_feature_names_out=False,
    )


def fit_quantile_models(
    train: pd.DataFrame,
    model_config: dict[str, Any],
    seed: int,
) -> QuantileModelBundle:
    won_train = train[train[TARGET].notna()].copy()
    preprocessor = make_preprocessor()
    transformed = preprocessor.fit_transform(won_train[NUMERIC_FEATURES + CATEGORICAL_FEATURES])
    target_log = np.log1p(won_train[TARGET].to_numpy(float))
    models: dict[float, XGBRegressor] = {}

    shared = {
        "objective": "reg:quantileerror",
        "n_estimators": int(model_config["n_estimators"]),
        "max_depth": int(model_config["max_depth"]),
        "learning_rate": float(model_config["learning_rate"]),
        "min_child_weight": float(model_config["min_child_weight"]),
        "subsample": float(model_config["subsample"]),
        "colsample_bytree": float(model_config["colsample_bytree"]),
        "reg_lambda": float(model_config["reg_lambda"]),
        "tree_method": "hist",
        "n_jobs": int(model_config["n_jobs"]),
        "random_state": seed,
    }
    for quantile in model_config["quantiles"]:
        alpha = float(quantile)
        model = XGBRegressor(quantile_alpha=alpha, **shared)
        model.fit(transformed, target_log, verbose=False)
        models[alpha] = model

    return QuantileModelBundle(
        preprocessor=preprocessor,
        models=models,
        feature_names=list(preprocessor.get_feature_names_out()),
    )


def predict_quantiles(bundle: QuantileModelBundle, frame: pd.DataFrame) -> pd.DataFrame:
    transformed = bundle.preprocessor.transform(frame[NUMERIC_FEATURES + CATEGORICAL_FEATURES])
    raw = np.column_stack(
        [np.expm1(bundle.models[alpha].predict(transformed)) for alpha in sorted(bundle.models)]
    )
    # Independently trained quantiles may cross. Sorting is a conservative,
    # auditable post-processing step that guarantees a valid interval.
    ordered = np.sort(np.maximum(raw, 0.01), axis=1)
    columns = [f"pred_q{int(alpha * 100):02d}" for alpha in sorted(bundle.models)]
    return pd.DataFrame(ordered, columns=columns, index=frame.index)


def feature_importance(bundle: QuantileModelBundle, quantile: float = 0.5) -> pd.DataFrame:
    model = bundle.models[quantile]
    importance = pd.DataFrame(
        {"feature": bundle.feature_names, "importance": model.feature_importances_}
    )
    return importance.sort_values("importance", ascending=False).reset_index(drop=True)

