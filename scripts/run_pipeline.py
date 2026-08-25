#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pricing_engine.config import load_config
from pricing_engine.pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "configs/base.yaml")
    args = parser.parse_args()
    metrics = run_pipeline(load_config(args.config), ROOT)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()

