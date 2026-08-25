# Data Card and Provenance

## Dataset sources

### UCI Online Retail II

- Owner/creator: Daqing Chen
- Records: 1,067,371 transaction lines
- Period: December 2009 through December 2011
- Relevant fields: invoice, product code, description, quantity, timestamp,
  unit price in GBP, anonymized customer ID, country
- License: CC BY 4.0
- DOI: https://doi.org/10.24432/C5CG6D

### Amazon Reviews 2023, Electronics metadata

- Creator: McAuley Lab / Hou et al.
- Relevant fields: parent ASIN, title, store/brand, price, rating, rating count,
  features, product metadata
- Source: https://amazon-reviews-2023.github.io/

Users should review the source terms before redistributing raw data. This project
bundles only the derived deterministic catalog extract and provides a downloader
for reproducibility.

## Field provenance

| Field | Provenance | Available at quote time? |
|---|---|---|
| `sku_id`, `title`, `brand`, `list_price_usd` | Real Amazon metadata | Yes |
| `average_rating`, `rating_count`, `feature_count` | Real Amazon metadata | Yes |
| `product_family` | Deterministic title rules | Yes |
| Market/quantity/customer/seasonality distributions | Derived from real UCI transactions | Yes as aggregates |
| `customer_key` | Hashed UCI customer ID | Yes |
| `customer_tier` | Derived UCI spend percentile | Yes |
| `unit_cost_usd`, `inventory_weeks`, `cost_change_pct` | Simulated | Yes |
| `contract_discount_pct`, `is_contract_customer` | Simulated | Yes |
| `quote_won`, `accepted_unit_price_usd` | Simulated outcome | No; target only |
| `sku_prior_mean_price`, history counts, prior win rate | Shifted prior events | Yes |
| `cluster_id` | Training-period K-Means | Yes after model publication |

## Cleaning decisions

- Exclude non-alphanumeric UCI stock codes from pricing calibration.
- Keep cancellations for market profiling; exclude them from completed-price
  calibration.
- Require positive price, quantity, and customer identifier for completed lines.
- Limit UCI quantity and price at the 99.8th percentile for calibration.
- Require Amazon price between $8 and $6,000 and at least three ratings.
- Filter catalog titles to compute-related terms.
- Use stable BLAKE2 selection for reproducible 17,000-SKU extraction.

## Known limitations

- Amazon page price is consumer list price, not enterprise channel list price.
- Rating count is a demand proxy, not booked units.
- UCI giftware buying behavior is not semiconductor buying behavior.
- Customer tiers and product costs are simulated rather than company economics.
- Market mix is square-root shrunk to improve pilot validation coverage.
- Quote outcomes are simulated and must not be represented as real customer wins.
- Public data cannot validate causal revenue or margin lift.

## Responsible use

This dataset is suitable for architecture, modeling, testing, and interview
demonstration. It is not suitable for live commercial pricing, competitive
price setting, or claims about a company's customers or products.
