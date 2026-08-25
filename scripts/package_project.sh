#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
delivery_dir="$project_root/deliverables"
archive_path="$delivery_dir/enterprise_pricing_recommendation_engine.zip"

mkdir -p "$delivery_dir"
cd "$project_root"

zip -q -r "$archive_path" . \
  -x '.venv/*' \
  -x '.pytest_cache/*' \
  -x '*/__pycache__/*' \
  -x '*.pyc' \
  -x 'data/raw/*' \
  -x 'data/processed/quote_events_initial.parquet' \
  -x 'data/processed/quote_events_peak_inventory_bug.parquet' \
  -x 'data/processed/quote_events_before_inventory_fix.parquet' \
  -x 'deliverables/*'

printf '%s\n' "$archive_path"
