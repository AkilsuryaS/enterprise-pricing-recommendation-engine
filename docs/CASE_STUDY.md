# End-to-End Case Study

## 1. Business framing

The commercial pricing team receives large numbers of quote-line requests for
a broad computer and electronics catalog. Analysts need to consider list price,
cost, volume, contract status, customer value, local-market behavior, inventory,
and prior realized prices. A uniform discount table is fast but leaves money on
the table; unrestricted machine learning is risky because an accurate model can
still recommend a price below cost or outside a contract.

The decision was therefore to build a **recommendation plus policy system**, not
an autonomous optimizer. The machine-learning component estimates a defensible
distribution of accepted prices. A deterministic policy layer decides whether
the recommendation is eligible for automation.

### Success criteria

- Cover the full 17,000-SKU catalog and nine configured markets.
- Automate roughly 45% of routine quotes without weakening hard margin rules.
- Keep p90 absolute percentage error below 14% on auto-approved validation wins.
- Provide reason codes for every manual-review decision.
- Improve analyst throughput while preserving an audit trail.
- Validate forward in time and report results by market, SKU cluster, and family.

## 2. Data acquisition and governance

Two public datasets are used because a responsible public project cannot claim
access to a company's confidential negotiated-price ledger.

The McAuley Lab Electronics metadata provides actual product identifiers,
titles, prices, brands, ratings, and rating counts. The extractor keeps records
with valid numeric prices, at least three ratings, and compute-related language.
A stable BLAKE2 hash filter makes the 17,000-row sample deterministic.

UCI Online Retail II supplies two years of genuine transaction-line behavior.
Cancellations are retained for market profiling. Price calibration uses only
completed lines with positive quantity, price, and customer identifier. Extreme
quantity and price values are clipped using empirical 99.8th-percentile limits,
and product codes must be alphanumeric.

Customer identifiers are one-way hashed in derived outputs. Although the UCI
identifiers are already anonymized, the additional transformation demonstrates
the handling expected in a commercial pipeline.

## 3. Building the quote ledger

The quote-event table contains 180,000 rows. All 17,000 SKUs receive at least one
quote, after which SKU sampling is weighted by the logarithm of real rating
count. Market mix starts from observed UCI transaction shares; a square-root
shrinkage is applied so small markets have enough pilot observations for model
validation.

The following signals are calibrated from UCI:

- market transaction and cancellation shares
- empirical quantity bands and relative prices
- customer-spend tiers, order count, and tenure
- monthly seasonality
- product-relative price ratios

Enterprise-only variables are deterministic simulations:

- cost ratios by product family
- inventory weeks and cost changes
- contract participation and discount
- quote win/loss and accepted price
- analyst handling time

This is not hidden. Every field is classified in the data card, and a fixed seed
allows another reviewer to produce the same dataset.

## 4. Preventing leakage

The target is `accepted_unit_price_usd`, populated only for won quotes. Model
features include only information that would be available when a quote is
created.

Historical features use shifted expanding calculations:

- `sku_history_count`
- `sku_prior_mean_price`
- `customer_history_count`
- `customer_prior_win_rate`

The current quote outcome is never included in its own historical feature. SKU
segmentation is also fitted using only the training window; validation and test
quotes inherit that frozen assignment.

The split is chronological. A random split would allow nearly identical future
SKU/customer behavior into training and would materially overstate production
performance.

## 5. SKU segmentation

K-Means operates on standardized SKU features. The candidate cluster count is
selected from k=4...8 by silhouette score. This run selected k=5. The scores are
modest (best 0.1549), which is plausible for noisy commercial behavior and is a
reason not to describe the segments as clean natural classes.

Observed segment examples:

| Cluster | SKUs | Median list price | Historical win rate | Interpretation |
|---:|---:|---:|---:|---|
| 0 | 2,571 | $25.99 | 53.9% | Lower-history, lower-win catalog tail |
| 1 | 5,193 | $25.99 | 79.9% | High-rating-count repeat products |
| 2 | 1,488 | $29.99 | 81.3% | Higher-quantity products |
| 3 | 2,962 | $389.99 | 84.1% | High-value products |
| 4 | 4,786 | $21.00 | 91.6% | High-win, lower-price products |

Cluster 3 has weaker interval coverage (80.6%) than the portfolio average and a
lower auto-approval rate (32.4%). That is exactly why cluster-level monitoring is
needed: the aggregate metric alone would hide the high-value risk slice.

## 6. Quantile price model

Three XGBoost regressors predict log price at alpha 0.10, 0.50, and 0.90 using
the quantile objective. Log transformation reduces the influence of the long
price tail and prevents high-priced products from dominating dollar-error loss.

The main feature groups are:

- economics: list price, cost, contract discount, cost change
- commercial context: quantity, customer tier, revenue, order history
- market context: market, monthly demand index
- product context: family, ratings, feature count, age
- history: prior SKU price, prior customer win rate, history counts
- K-Means cluster

The q50 feature-importance ranking is led by list price, unit cost, and prior SKU
mean price. This is commercially sensible, but feature importance is not a causal
explanation. In a production release, per-quote SHAP reason codes should be
generated from an approved explanation template.

Independently trained quantiles can cross. The scoring code sorts the three raw
predictions row-wise before policy evaluation, guaranteeing q10 <= q50 <= q90.

## 7. Guardrails and decisioning

The q50 prediction is only a candidate price.

### Financial floor

For customer tier `t`:

```text
margin_floor   = unit_cost / (1 - min_margin[t])
discount_floor = list_price * (1 - max_discount[t])
policy_floor   = max(margin_floor, discount_floor)
```

The final recommendation is clipped between this floor and 112% of list price.

### Automation eligibility

A quote must pass all of the following:

- complete and valid price, cost, quantity, and market
- expected margin at or above its tier floor
- discount within its tier limit
- recommended quote value <= $250,000
- absolute cost change <= 18%
- inventory >= 1.5 weeks
- at least three prior SKU quotes
- non-strategic account
- normalized q10-q90 width <= 35%
- confidence above the validation-calibrated threshold

Validation searches candidate confidence thresholds and selects the closest
coverage to the 45% target subject to p90 APE <= 14%. The chosen threshold was
0.5124; validation coverage was 44.95% and validation p90 APE was 9.47%.

## 8. Test results

The untouched test window produced:

- 46.20% auto-approval
- 9.95% p90 APE on the auto-approved subset
- 4.20% median APE across observed wins
- 10.07% p90 APE across observed wins
- 92.06% coverage for the q10-q90 interval
- $7.17 overall MAE
- 24.39% MAE improvement over the prior-SKU-price baseline

The interval is over-conservative relative to its nominal 80% coverage. Before a
real rollout, I would apply conformal calibration by price band and market, then
rerun policy coverage tests.

Market-level results are not uniform. Ireland and the Netherlands auto-approve
less often than most slices because their observed quantity and relative-price
profiles cause more policy or confidence exceptions. A rollout decision should
therefore use per-market risk appetite rather than force exactly 45% everywhere.

## 9. Explaining the 4x efficiency number

The source datasets do not contain analyst time. The project therefore provides
a transparent capacity model rather than mislabeling an estimate as measured
labor telemetry.

Configured assumptions:

- manual baseline: 10.0 minutes per quote line
- analyst-assisted review: 4.4 minutes
- auto-approved oversight allocation: 0.25 minutes

At the test auto-approval rate of 0.4620:

```text
blended_minutes = 0.4620 * 0.25 + (1 - 0.4620) * 4.4
                = 2.4826 minutes

throughput_multiplier = 10.0 / 2.4826
                      = 4.03x
```

In a company, these inputs should come from quote-system event logs: time opened,
decision time, number of analyst touches, and override duration. The formula can
then become a measured KPI rather than an assumption.

## 10. Productionization approach

The included FastAPI service is a working scoring boundary. In a company, the
request would normally contain only quote identifiers. Product cost, contract,
customer, inventory, and historical signals would be retrieved from governed
feature services rather than supplied by a caller.

Production controls should include:

- immutable model, feature, and guardrail version in every response
- request/response audit log with reason codes
- idempotency by quote-line ID
- online/offline feature parity tests
- p50/p95/p99 latency and error-rate dashboards
- drift by market, family, and cluster
- interval coverage and override rate once outcomes arrive
- champion/challenger shadow evaluation
- rollback to the last approved model and independent policy version

## 11. What this project proves—and does not prove

It proves that the project statement can be decomposed into a technically
coherent, executable system and validated at the stated scale with public data.
It does not prove business impact, customer behavior, or margin economics for
any particular company. Present it as a public-data case study.
