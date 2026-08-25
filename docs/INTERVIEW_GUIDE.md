# Interview Guide

## Two-minute explanation

“The problem was that pricing analysts manually reviewed both routine and risky
quote lines. I designed the system as a price-distribution model plus a separate
policy engine. The public implementation covers 17,000 real electronics SKUs and
nine market profiles, with 180,000 reproducible quote events calibrated from over
one million real UCI transaction lines.

I segmented SKUs using training-period behavioral features, then trained three
XGBoost quantile models to predict the 10th, 50th, and 90th percentiles of accepted
unit price. Quantiles mattered because they gave us both a median recommendation
and an uncertainty range. The median prediction could not go directly to a
customer: it passed margin, discount, quote-value, cost-change, inventory,
history, strategic-account, and confidence guardrails.

I used a chronological split and calibrated the confidence threshold on the
validation window to target roughly 45% automation while keeping p90 error under
14%. The untouched test window achieved 46.2% auto-approval and 9.95% p90 error
for auto-approved wins. With documented handling-time assumptions, blended work
fell from 10 minutes to 2.48 minutes per quote line, or 4.03x throughput.

The important design choice was that the model estimated price, while the policy
engine retained authority over financial safety. The main remaining issues are
over-conservative interval coverage, weaker performance on the high-value SKU
cluster, and selection bias from training accepted-price models on won quotes.”

## Questions you should expect

### Why not ordinary XGBoost regression?

It returns one number and makes uncertainty difficult to operationalize.
Quantile models provide a lower, median, and upper conditional estimate. Interval
width is then an auditable confidence input for auto-approval.

### Why use K-Means?

The catalog has sparse and heterogeneous SKU behavior. K-Means provides a coarse
behavioral context for cold-start and monitoring. I selected k using silhouette
score, froze assignments at the train cutoff, and avoided claiming the clusters
were causal product categories.

### How did you avoid leakage?

All prior-price and win-rate features use shifted expanding windows. Clustering
uses only training history. The train/validation/test split is chronological, and
final accepted price and current quote outcome are never features.

### Where does 45% come from?

It is a policy coverage target, not a free model metric. On validation I searched
confidence thresholds and chose the one closest to 45% subject to a p90 APE cap
of 14%. Validation reached 44.95%; the later test window reached 46.20%.

### Where does 4x come from?

The public data has no analyst telemetry, so it is an explicit capacity estimate:
10 minutes manual, 4.4 minutes assisted, and 0.25 minutes allocated oversight for
automated cases. At 46.2% auto-approval, blended handling is 2.48 minutes and
throughput is 10/2.48 = 4.03x. In a company I would replace these assumptions
with event-log measurements.

### What would you change for a real enterprise deployment?

- Use actual distributor/customer quote history and product hierarchy.
- Use point-in-time cost, inventory, FX, contract, and competitor signals.
- Add a win-probability model and optimize expected contribution margin, not
  accepted price alone.
- Calibrate prediction intervals by market and price band.
- Add SHAP-based approved reason codes.
- Run a shadow period and controlled market rollout.
- Measure realized margin, win rate, override behavior, and analyst touch time.

## Accuracy rule for your resume

Describe this as a public-data case study. Do not imply that its simulated
outcomes represent measured impact at a company.
