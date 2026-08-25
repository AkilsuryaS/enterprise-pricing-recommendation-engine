from __future__ import annotations

from fastapi.testclient import TestClient

from pricing_engine.api import app


client = TestClient(app)


def test_health_reports_full_catalog() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["catalog_skus"] == 17_000


def test_recommendation_contract() -> None:
    sku = client.get("/health")
    assert sku.status_code == 200
    # A catalog identifier bundled in the deterministic public sample.
    response = client.post(
        "/v1/recommend",
        json={
            "sku_id": "B00003G1I1",
            "market": "DE",
            "quantity": 25,
            "customer_tier": "enterprise",
            "is_contract_customer": True,
            "inventory_weeks": 6.0,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["lower_price"] <= payload["upper_price"]
    assert payload["recommended_unit_price"] > 0
    assert payload["decision"] in {"AUTO_APPROVE", "MANUAL_REVIEW"}

