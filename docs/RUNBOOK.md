# Operational Runbook

## Daily checks

- Source freshness: catalog, cost, inventory, contracts, FX, customer history.
- API: availability, error rate, p50/p95/p99 latency.
- Decision mix: auto-approval, manual-review reasons, strategic exceptions.
- Financial safety: no recommendation below margin or contract floor.

## Outcome monitoring

Accepted prices arrive after quote resolution. Join them by quote-line ID and
calculate interval coverage, APE, win rate, realized margin, and analyst override.
Metrics must be sliced by market, product family, cluster, tier, and price band.

## Automatic disable conditions

- Missing or stale unit cost.
- Contract service unavailable.
- Model/feature schema mismatch.
- Any detected recommendation below hard floor.
- Material drift plus insufficient fresh outcome labels.

The fallback is recommendation-only/manual review, not an old unguarded price.

## Retraining

1. Snapshot source tables and policy configuration.
2. Recreate features with point-in-time joins.
3. Fit segmentation only on the training window.
4. Train quantile models.
5. Calibrate intervals and approval threshold on validation.
6. Run temporal test, slice tests, and policy invariants.
7. Shadow challenger in production.
8. Obtain pricing, finance, risk, and model-governance approvals.
9. Promote immutable versions; retain rollback bundle.

## Incident triage

| Symptom | First checks | Immediate action |
|---|---|---|
| Margin-floor violation | Cost freshness, tier map, rounding | Disable auto-approval |
| Coverage collapse | Label delay, drift, quantile crossing | Route affected slice to review |
| Market override spike | FX, contract rules, local campaign | Pause that market only |
| Latency spike | Feature service, model load, concurrency | Cache stable features; scale service |
| Unknown SKU | Catalog sync lag | Manual review and catalog refresh |

