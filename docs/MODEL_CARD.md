# Model Card

## Intended use

Recommend a price interval and median price for a quote line, then support a
separate deterministic decision layer. This is a public-data case study only.

## Model

- Algorithm: three XGBoost regressors
- Objective: `reg:quantileerror`
- Quantiles: 0.10, 0.50, 0.90
- Target transform: `log1p(accepted_unit_price_usd)`
- Trees: 260 per quantile
- Maximum depth: 7
- Learning rate: 0.055
- Training rows: won quotes within the 126,011-row chronological train window
- SKU segmentation: K-Means, selected k=5

## Test performance

| Measure | Result |
|---|---:|
| MAE | $7.17 |
| Median APE | 4.20% |
| P90 APE | 10.07% |
| q10-q90 coverage | 92.06% |
| Improvement vs prior-price MAE | 24.39% |
| Auto-approval | 46.20% |
| Auto-approved subset p90 APE | 9.95% |

## Limitations and risks

- Outcome labels are simulated; public data is used for calibration and catalog
  realism, not as a confidential company quote ledger.
- The 92.06% interval coverage indicates an over-wide nominal 80% interval.
- High-value cluster 3 has only 80.60% interval coverage.
- Training only on wins can create selection bias. A real deployment should
  jointly model acceptance probability and price or use causal/uplift methods.
- Feature importance is not causal and must not be used as a fairness argument.
- Customer tier and market can encode commercial policy differences; legal and
  compliance review is required before live use.
- Model outputs must never bypass contractual or cost guardrails.

## Monitoring thresholds

- Alert if p90 APE exceeds 14% for two completed weekly windows.
- Alert if interval coverage leaves 75%-95% overall or falls below 70% in a
  market/cluster slice with at least 200 outcomes.
- Alert if analyst override rate increases by 10 percentage points week over week.
- Alert if any required feature has >1% missingness.
- Alert if PSI exceeds 0.20 for list price, quantity, cost change, or interval width.
- Disable auto-approval if cost feed or contract-policy version is unavailable.

## Approval and rollback

Model and policy versions should be approved independently. Rollback must restore
both the scoring bundle and the compatible feature schema; a policy-only rollback
must remain possible without retraining the model.
