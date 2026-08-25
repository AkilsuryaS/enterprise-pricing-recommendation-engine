from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


MARKET_CODES = {
    "United Kingdom": "UK",
    "EIRE": "IE",
    "Germany": "DE",
    "France": "FR",
    "Netherlands": "NL",
    "Spain": "ES",
    "Belgium": "BE",
    "Switzerland": "CH",
    "Portugal": "PT",
}

TIER_NAMES = ["channel", "mid_market", "enterprise", "strategic"]


def _hash_id(value: object, prefix: str) -> str:
    raw = f"{prefix}:{value}".encode("utf-8")
    return f"{prefix}_{hashlib.blake2b(raw, digest_size=6).hexdigest()}"


def load_and_clean_uci(path: str | Path) -> pd.DataFrame:
    """Read both UCI workbook years and retain analytically valid line items.

    Cancellations remain available through ``is_cancelled`` for market profiling,
    but only positive completed lines are used to calibrate negotiated prices.
    """
    frames: list[pd.DataFrame] = []
    workbook = pd.ExcelFile(path)
    for sheet_name in workbook.sheet_names:
        frame = pd.read_excel(workbook, sheet_name=sheet_name)
        frame["source_sheet"] = sheet_name
        frames.append(frame)

    data = pd.concat(frames, ignore_index=True)
    data = data.rename(
        columns={
            "Invoice": "invoice_id",
            "StockCode": "stock_code",
            "Description": "description",
            "Quantity": "quantity",
            "InvoiceDate": "invoice_date",
            "Price": "unit_price_gbp",
            "Customer ID": "customer_id",
            "Country": "country",
        }
    )
    data["invoice_id"] = data["invoice_id"].astype(str)
    data["stock_code"] = data["stock_code"].astype(str).str.strip()
    data["invoice_date"] = pd.to_datetime(data["invoice_date"], errors="coerce")
    data["is_cancelled"] = data["invoice_id"].str.upper().str.startswith("C") | (data["quantity"] < 0)
    data["line_revenue_gbp"] = data["quantity"] * data["unit_price_gbp"]

    valid_shape = (
        data["invoice_date"].notna()
        & data["country"].notna()
        & data["stock_code"].str.match(r"^[A-Za-z0-9]+$")
        & data["quantity"].between(-50_000, 50_000)
        & data["unit_price_gbp"].between(0, 50_000)
    )
    return data.loc[valid_shape].reset_index(drop=True)


def build_calibration_tables(
    transactions: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Derive nine-market, quantity, customer, and seasonality profiles from UCI."""
    completed = transactions.loc[
        (~transactions["is_cancelled"])
        & (transactions["quantity"] > 0)
        & (transactions["unit_price_gbp"] > 0)
        & transactions["customer_id"].notna()
    ].copy()

    country_counts = completed["country"].value_counts()
    selected = [country for country in MARKET_CODES if country in country_counts.index]
    if len(selected) != 9:
        raise ValueError(f"Expected nine configured UCI countries; found {selected}")
    completed = completed[completed["country"].isin(selected)].copy()

    quantity_cap = completed["quantity"].quantile(0.998)
    price_cap = completed["unit_price_gbp"].quantile(0.998)
    completed = completed[
        completed["quantity"].between(1, max(1, quantity_cap))
        & completed["unit_price_gbp"].between(0.01, max(0.01, price_cap))
    ].copy()

    sku_reference = completed.groupby("stock_code")["unit_price_gbp"].median().rename("sku_median_gbp")
    completed = completed.join(sku_reference, on="stock_code")
    completed["relative_price"] = (
        completed["unit_price_gbp"] / completed["sku_median_gbp"].replace(0, np.nan)
    ).clip(0.35, 2.0)

    all_market_lines = transactions[transactions["country"].isin(selected)]
    cancellation = all_market_lines.groupby("country")["is_cancelled"].mean()
    market_profiles = (
        completed.groupby("country")
        .agg(
            completed_lines=("invoice_id", "size"),
            unique_customers=("customer_id", "nunique"),
            unique_products=("stock_code", "nunique"),
            median_quantity=("quantity", "median"),
            p90_quantity=("quantity", lambda values: values.quantile(0.90)),
            median_relative_price=("relative_price", "median"),
        )
        .reset_index()
    )
    market_profiles["cancellation_rate"] = market_profiles["country"].map(cancellation).fillna(0.0)
    market_profiles["transaction_share"] = (
        market_profiles["completed_lines"] / market_profiles["completed_lines"].sum()
    )
    market_profiles["market"] = market_profiles["country"].map(MARKET_CODES)

    customer_profiles = (
        completed.groupby(["country", "customer_id"])
        .agg(
            customer_revenue_gbp=("line_revenue_gbp", "sum"),
            customer_orders=("invoice_id", "nunique"),
            customer_lines=("invoice_id", "size"),
            first_order=("invoice_date", "min"),
            last_order=("invoice_date", "max"),
            median_quantity=("quantity", "median"),
        )
        .reset_index()
    )
    customer_profiles["customer_tenure_months"] = (
        (customer_profiles["last_order"] - customer_profiles["first_order"]).dt.days / 30.44
    ).clip(lower=0)
    percentile = customer_profiles.groupby("country")["customer_revenue_gbp"].rank(pct=True, method="average")
    customer_profiles["customer_tier"] = pd.cut(
        percentile,
        bins=[0.0, 0.50, 0.80, 0.95, 1.0],
        labels=TIER_NAMES,
        include_lowest=True,
    ).astype(str)
    customer_profiles["market"] = customer_profiles["country"].map(MARKET_CODES)
    customer_profiles["customer_key"] = [
        _hash_id(value, market) for value, market in zip(customer_profiles["customer_id"], customer_profiles["market"])
    ]

    completed["quantity_band"] = pd.cut(
        completed["quantity"],
        bins=[0, 1, 5, 11, 23, 49, 99, np.inf],
        labels=["1", "2_5", "6_11", "12_23", "24_49", "50_99", "100_plus"],
    ).astype(str)
    quantity_profiles = (
        completed.groupby(["country", "quantity_band"], observed=True)
        .agg(
            observations=("invoice_id", "size"),
            median_quantity=("quantity", "median"),
            median_relative_price=("relative_price", "median"),
        )
        .reset_index()
    )
    quantity_profiles["market"] = quantity_profiles["country"].map(MARKET_CODES)
    quantity_profiles["within_market_share"] = quantity_profiles["observations"] / quantity_profiles.groupby(
        "market"
    )["observations"].transform("sum")

    completed["month"] = completed["invoice_date"].dt.month
    seasonality = completed.groupby("month").size().rename("lines").reset_index()
    seasonality["month_share"] = seasonality["lines"] / seasonality["lines"].sum()
    seasonality["demand_index"] = seasonality["month_share"] / (1 / 12)

    keep_customer = [
        "market", "customer_key", "customer_tier", "customer_revenue_gbp",
        "customer_orders", "customer_lines", "customer_tenure_months", "median_quantity",
    ]
    return (
        market_profiles.sort_values("market").reset_index(drop=True),
        customer_profiles[keep_customer].reset_index(drop=True),
        quantity_profiles.reset_index(drop=True),
        seasonality.reset_index(drop=True),
    )


def _deterministic_sku_economics(catalog: pd.DataFrame, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    output = catalog.copy()
    family_cost_ratio = {
        "GPU_AND_GRAPHICS": 0.58,
        "CPU_AND_PROCESSOR": 0.54,
        "SERVER_AND_ACCELERATOR": 0.49,
        "MOTHERBOARD": 0.63,
        "MEMORY_AND_STORAGE": 0.66,
        "NETWORKING": 0.61,
        "WORKSTATION_AND_PC": 0.70,
        "THERMAL_AND_POWER": 0.64,
        "OTHER_COMPUTE": 0.65,
    }
    base_ratio = output["product_family"].map(family_cost_ratio).fillna(0.64).to_numpy(float)
    ratio = np.clip(base_ratio + rng.normal(0, 0.035, len(output)), 0.38, 0.78)
    output["unit_cost_usd"] = (output["list_price_usd"] * ratio).round(2)
    output["launch_age_days"] = rng.integers(60, 2600, len(output))
    output["inventory_weeks_base"] = np.clip(rng.lognormal(1.45, 0.55, len(output)), 0.4, 18.0)
    output["sku_demand_weight"] = np.log1p(output["rating_count"]).clip(upper=10)
    output["sku_demand_weight"] /= output["sku_demand_weight"].sum()
    return output


def generate_quote_events(
    catalog: pd.DataFrame,
    market_profiles: pd.DataFrame,
    customer_profiles: pd.DataFrame,
    quantity_profiles: pd.DataFrame,
    seasonality: pd.DataFrame,
    rows: int,
    seed: int,
) -> pd.DataFrame:
    """Create an enterprise quote table whose public-data provenance is explicit.

    Catalog attributes and calibration distributions are real. Confidential
    quote-only fields and outcomes are simulated because no public enterprise
    quote ledger exists. The simulation is deterministic and parameterized.
    """
    rng = np.random.default_rng(seed)
    catalog = _deterministic_sku_economics(catalog, seed)

    # Preserve the empirical ordering while shrinking the dominant UK share.
    # This is a deliberate pilot-design choice: every market needs enough cases
    # for segmented validation before a production rollout.
    market_weights = np.sqrt(market_profiles["transaction_share"].to_numpy())
    market_weights /= market_weights.sum()
    market_sample = rng.choice(market_profiles["market"], size=rows, p=market_weights)
    month_sample = rng.choice(
        seasonality["month"].astype(int), size=rows, p=seasonality["month_share"].to_numpy()
    )
    year_sample = rng.choice([2024, 2025], size=rows, p=[0.46, 0.54])
    day_sample = rng.integers(1, 27, size=rows)
    quote_dates = pd.to_datetime(
        {"year": year_sample, "month": month_sample, "day": day_sample}
    ) + pd.to_timedelta(rng.integers(0, 24, rows), unit="h")

    if rows < len(catalog):
        raise ValueError("quote_rows must be at least as large as the catalog")
    mandatory_coverage = rng.permutation(len(catalog))
    remaining = rng.choice(
        len(catalog), size=rows - len(catalog), p=catalog["sku_demand_weight"].to_numpy()
    )
    sku_indices = np.concatenate([mandatory_coverage, remaining])
    rng.shuffle(sku_indices)
    quotes = catalog.iloc[sku_indices].reset_index(drop=True)
    quotes["quote_date"] = quote_dates
    quotes["market"] = market_sample

    customer_chunks: list[pd.DataFrame] = []
    for market, count in pd.Series(market_sample).value_counts().items():
        pool = customer_profiles[customer_profiles["market"] == market]
        selected = pool.iloc[rng.integers(0, len(pool), size=int(count))].copy()
        selected["_order"] = np.flatnonzero(market_sample == market)
        customer_chunks.append(selected)
    sampled_customers = pd.concat(customer_chunks).sort_values("_order").reset_index(drop=True)
    for column in [
        "customer_key", "customer_tier", "customer_revenue_gbp", "customer_orders",
        "customer_lines", "customer_tenure_months",
    ]:
        quotes[column] = sampled_customers[column].to_numpy()

    quantity = np.empty(rows, dtype=int)
    quantity_discount = np.empty(rows, dtype=float)
    for market, positions in pd.Series(market_sample).groupby(market_sample).groups.items():
        profiles = quantity_profiles[quantity_profiles["market"] == market]
        choice = rng.choice(len(profiles), size=len(positions), p=profiles["within_market_share"].to_numpy())
        selected = profiles.iloc[choice]
        median_q = selected["median_quantity"].to_numpy(float)
        sampled_q = np.maximum(1, np.rint(median_q * rng.lognormal(0, 0.38, len(positions)))).astype(int)
        quantity[np.asarray(list(positions))] = np.clip(sampled_q, 1, 2_500)
        quantity_discount[np.asarray(list(positions))] = selected["median_relative_price"].to_numpy(float)
    quotes["quantity"] = quantity
    quotes["quantity_calibration_factor"] = np.clip(quantity_discount, 0.72, 1.05)

    market_factor = market_profiles.set_index("market")["median_relative_price"].to_dict()
    demand_index = seasonality.set_index("month")["demand_index"].to_dict()
    quotes["market_factor"] = quotes["market"].map(market_factor).astype(float).clip(0.90, 1.08)
    quotes["market_demand_index"] = quotes["quote_date"].dt.month.map(demand_index).astype(float)
    quotes["inventory_weeks"] = np.clip(
        quotes["inventory_weeks_base"] / np.sqrt(quotes["market_demand_index"]) + rng.normal(0, 0.7, rows),
        0.2,
        24.0,
    )
    quotes["cost_change_pct"] = np.clip(rng.normal(0.015, 0.065, rows), -0.16, 0.35)
    quotes["unit_cost_usd"] = quotes["unit_cost_usd"] * (1 + quotes["cost_change_pct"])

    tier_discount = {
        "channel": 0.88,
        "mid_market": 0.94,
        "enterprise": 0.86,
        "strategic": 0.80,
    }
    quotes["tier_price_factor"] = quotes["customer_tier"].map(tier_discount).astype(float)
    quotes["contract_discount_pct"] = np.clip(
        1 - quotes["tier_price_factor"] + rng.normal(0, 0.025, rows), 0, 0.34
    )
    quotes["is_strategic"] = quotes["customer_tier"].eq("strategic")
    quotes["is_contract_customer"] = rng.random(rows) < quotes["customer_tier"].map(
        {"channel": 0.55, "mid_market": 0.22, "enterprise": 0.68, "strategic": 0.88}
    )

    annual_index = 1 + (quotes["quote_date"].dt.year - 2024) * 0.032
    scarcity = 1 + np.where(quotes["inventory_weeks"] < 2.0, 0.055, 0.0)
    demand_adjustment = 1 + (quotes["market_demand_index"] - 1) * 0.035
    negotiation_noise = rng.lognormal(mean=-0.003, sigma=0.055, size=rows)
    raw_price = (
        quotes["list_price_usd"]
        * quotes["market_factor"]
        * quotes["quantity_calibration_factor"]
        * quotes["tier_price_factor"]
        * annual_index
        * scarcity
        * demand_adjustment
        * negotiation_noise
    )
    economic_floor = quotes["unit_cost_usd"] / (1 - quotes["customer_tier"].map(
        {"channel": 0.10, "mid_market": 0.14, "enterprise": 0.11, "strategic": 0.08}
    ))
    potential_price = np.maximum(raw_price, economic_floor)

    willingness_multiplier = rng.normal(0.92, 0.10, rows)
    price_pressure = potential_price / (quotes["list_price_usd"] * willingness_multiplier).clip(lower=1)
    logit = (
        1.25
        - 3.0 * (price_pressure - 1)
        + 0.20 * np.log1p(quotes["customer_orders"])
        - 0.12 * np.log1p(quotes["quantity"])
        + 0.15 * quotes["is_contract_customer"].astype(int)
    )
    win_probability = 1 / (1 + np.exp(-logit))
    quotes["quote_won"] = rng.random(rows) < np.clip(win_probability, 0.08, 0.95)
    quotes["accepted_unit_price_usd"] = np.where(quotes["quote_won"], potential_price, np.nan)
    quotes["quote_value_usd"] = potential_price * quotes["quantity"]
    quotes["quote_id"] = [f"Q-{value:09d}" for value in range(1, rows + 1)]

    quotes = quotes.sort_values(["quote_date", "quote_id"]).reset_index(drop=True)
    quotes["sku_history_count"] = quotes.groupby("sku_id").cumcount()
    quotes["customer_history_count"] = quotes.groupby("customer_key").cumcount()
    prior_prices = quotes["accepted_unit_price_usd"]
    quotes["sku_prior_mean_price"] = (
        prior_prices.groupby(quotes["sku_id"]).transform(lambda values: values.shift().expanding().mean())
    )
    prior_wins = quotes["quote_won"].astype(float)
    quotes["customer_prior_win_rate"] = (
        prior_wins.groupby(quotes["customer_key"]).transform(lambda values: values.shift().expanding().mean())
    )
    quotes["sku_prior_mean_price"] = quotes["sku_prior_mean_price"].fillna(quotes["list_price_usd"])
    quotes["customer_prior_win_rate"] = quotes["customer_prior_win_rate"].fillna(0.50)
    quotes["log_quantity"] = np.log1p(quotes["quantity"])
    quotes["log_rating_count"] = np.log1p(quotes["rating_count"])
    quotes["quote_month"] = quotes["quote_date"].dt.month
    quotes["quote_quarter"] = quotes["quote_date"].dt.quarter
    quotes["quote_year"] = quotes["quote_date"].dt.year
    quotes["days_since_launch"] = quotes["launch_age_days"] + (
        quotes["quote_date"] - pd.Timestamp("2024-01-01")
    ).dt.days

    drop_columns = [
        "source_line", "source", "sku_demand_weight", "inventory_weeks_base",
        "tier_price_factor", "quantity_calibration_factor", "market_factor",
    ]
    return quotes.drop(columns=drop_columns)


def prepare_case_study_data(config: dict[str, Any], root: Path) -> dict[str, pd.DataFrame]:
    data_config = config["data"]
    uci_path = root / data_config["uci_path"]
    catalog_path = root / data_config["catalog_path"]
    quote_path = root / data_config["quote_events_path"]
    market_path = root / data_config["market_profiles_path"]

    catalog = pd.read_parquet(catalog_path)
    if quote_path.exists() and market_path.exists():
        quotes = pd.read_parquet(quote_path)
        markets = pd.read_csv(market_path)
        return {"catalog": catalog, "quotes": quotes, "markets": markets}

    transactions = load_and_clean_uci(uci_path)
    markets, customers, quantities, seasonality = build_calibration_tables(transactions)
    markets.to_csv(market_path, index=False)
    customers.to_parquet(root / "data/processed/customer_profiles.parquet", index=False)
    quantities.to_csv(root / "data/processed/quantity_profiles.csv", index=False)
    seasonality.to_csv(root / "data/processed/seasonality.csv", index=False)

    quotes = generate_quote_events(
        catalog=catalog,
        market_profiles=markets,
        customer_profiles=customers,
        quantity_profiles=quantities,
        seasonality=seasonality,
        rows=int(config["project"]["quote_rows"]),
        seed=int(config["project"]["seed"]),
    )
    quotes.to_parquet(quote_path, index=False)
    return {"catalog": catalog, "quotes": quotes, "markets": markets}
