#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd


AMAZON_META_URL = (
    "https://mcauleylab.ucsd.edu/public_datasets/data/amazon_2023/"
    "raw/meta_categories/meta_Electronics.jsonl.gz"
)
UCI_ZIP_URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"

COMPUTE_TERMS = (
    "processor", " cpu ", "gpu", "graphics", "motherboard", "server", "workstation",
    "computer", "laptop", "desktop", "memory", "ram ", "ssd", "nvme", "pcie",
    "chipset", "ethernet", "network adapter", "mini pc", "cooler", "power supply",
)


def _download_file(url: str, target: Path) -> None:
    if target.exists() and target.stat().st_size > 0:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as response, target.open("wb") as output:
        shutil.copyfileobj(response, output)


def download_uci(target_xlsx: Path) -> None:
    if target_xlsx.exists():
        return
    zip_path = target_xlsx.parent / "online_retail_ii.zip"
    _download_file(UCI_ZIP_URL, zip_path)
    with zipfile.ZipFile(zip_path) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith(".xlsx")]
        if len(members) != 1:
            raise RuntimeError(f"Expected one xlsx file in UCI archive, found {members}")
        with archive.open(members[0]) as source, target_xlsx.open("wb") as output:
            shutil.copyfileobj(source, output)


def _stable_accept(identifier: str, rate: int = 35) -> bool:
    digest = hashlib.blake2b(identifier.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big") % 100 < rate


def _product_family(title: str) -> str:
    text = f" {title.lower()} "
    rules = [
        ("GPU_AND_GRAPHICS", ("gpu", "graphics card", "video card")),
        ("CPU_AND_PROCESSOR", ("processor", " cpu ", "ryzen", "xeon")),
        ("SERVER_AND_ACCELERATOR", ("server", "accelerator", "data center")),
        ("MOTHERBOARD", ("motherboard", "mainboard", "chipset")),
        ("MEMORY_AND_STORAGE", ("memory", " ram ", "ssd", "nvme", "hard drive")),
        ("NETWORKING", ("ethernet", "network adapter", "router", "switch")),
        ("WORKSTATION_AND_PC", ("workstation", "desktop", "mini pc", "computer")),
        ("THERMAL_AND_POWER", ("cooler", "heatsink", "power supply", "fan")),
    ]
    for family, terms in rules:
        if any(term in text for term in terms):
            return family
    return "OTHER_COMPUTE"


def stream_amazon_catalog(target: Path, catalog_size: int) -> None:
    if target.exists() and len(pd.read_parquet(target)) >= catalog_size:
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    request = urllib.request.Request(AMAZON_META_URL, headers={"User-Agent": "pricing-case-study/0.1"})

    with urllib.request.urlopen(request, timeout=180) as response:
        with gzip.GzipFile(fileobj=response) as gz_stream:
            text_stream = io.TextIOWrapper(gz_stream, encoding="utf-8")
            for line_number, line in enumerate(text_stream, start=1):
                record = json.loads(line)
                sku_id = str(record.get("parent_asin") or "")
                title = str(record.get("title") or "")
                price = record.get("price")
                rating_count = int(record.get("rating_number") or 0)
                searchable = f" {title.lower()} "

                if not sku_id or sku_id in seen or not isinstance(price, (int, float)):
                    continue
                if not 8.0 <= float(price) <= 6000.0 or rating_count < 3:
                    continue
                if not any(term in searchable for term in COMPUTE_TERMS):
                    continue
                if not _stable_accept(sku_id):
                    continue

                details = record.get("details") or {}
                brand = details.get("Brand") or record.get("store") or "UNKNOWN"
                rows.append(
                    {
                        "sku_id": sku_id,
                        "title": title[:300],
                        "brand": str(brand)[:120],
                        "product_family": _product_family(title),
                        "list_price_usd": round(float(price), 2),
                        "average_rating": float(record.get("average_rating") or 0.0),
                        "rating_count": rating_count,
                        "feature_count": len(record.get("features") or []),
                        "source_line": line_number,
                        "source": "McAuley-Lab Amazon Reviews 2023/Electronics metadata",
                    }
                )
                seen.add(sku_id)
                if len(rows) >= catalog_size:
                    break

    if len(rows) < catalog_size:
        raise RuntimeError(f"Only found {len(rows):,} eligible electronics SKUs")
    pd.DataFrame(rows).sort_values("sku_id").reset_index(drop=True).to_parquet(target, index=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog-size", type=int, default=17_000)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()

    raw_dir = args.root / "data" / "raw"
    processed_dir = args.root / "data" / "processed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    uci_xlsx = raw_dir / "online_retail_II.xlsx"
    catalog = processed_dir / "electronics_catalog.parquet"
    print("Downloading UCI Online Retail II ...", flush=True)
    download_uci(uci_xlsx)
    print("Streaming a deterministic 17K computer/electronics catalog sample ...", flush=True)
    stream_amazon_catalog(catalog, args.catalog_size)
    print(f"Saved: {uci_xlsx}", flush=True)
    print(f"Saved: {catalog}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Data download failed: {exc}", file=sys.stderr)
        raise

