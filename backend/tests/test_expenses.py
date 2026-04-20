"""
Integration tests for the Expense Tracker API.

Run with:  pytest tests/ -v
"""

import pytest
import pytest_asyncio
import os
import tempfile
from decimal import Decimal
from httpx import AsyncClient, ASGITransport

@pytest_asyncio.fixture
async def client():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["DB_PATH"] = db_path

    from main import app
    from src.database import init_db
    await init_db()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    os.unlink(db_path)


@pytest.mark.asyncio
async def test_create_expense(client):
    payload = {"idempotency_key": "test-key-001", "amount": "199.50",
               "category": "Food", "description": "Lunch", "date": "2024-04-01"}
    resp = await client.post("/expenses", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert Decimal(data["amount"]) == Decimal("199.50")
    assert data["category"] == "Food"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_expense_idempotent(client):
    """Submitting the same idempotency_key twice must return identical records."""
    payload = {"idempotency_key": "idem-key-xyz", "amount": "500.00",
               "category": "Transport", "description": "Uber", "date": "2024-04-02"}
    resp1 = await client.post("/expenses", json=payload)
    resp2 = await client.post("/expenses", json=payload)
    assert resp1.status_code == 201
    assert resp1.json()["id"] == resp2.json()["id"]


@pytest.mark.asyncio
async def test_negative_amount_rejected(client):
    payload = {"idempotency_key": "neg", "amount": "-50.00",
               "category": "Food", "description": "Bad", "date": "2024-04-01"}
    assert (await client.post("/expenses", json=payload)).status_code == 422


@pytest.mark.asyncio
async def test_zero_amount_rejected(client):
    payload = {"idempotency_key": "zero", "amount": "0.00",
               "category": "Food", "description": "Nope", "date": "2024-04-01"}
    assert (await client.post("/expenses", json=payload)).status_code == 422


@pytest.mark.asyncio
async def test_missing_fields_rejected(client):
    assert (await client.post("/expenses", json={"amount": "100"})).status_code == 422


@pytest.mark.asyncio
async def test_list_expenses(client):
    for i, cat in enumerate(["Food", "Travel"]):
        await client.post("/expenses", json={"idempotency_key": f"list-{i}", "amount": "100.00",
                                             "category": cat, "description": f"E{i}", "date": "2024-04-01"})
    data = (await client.get("/expenses")).json()
    assert data["count"] == 2
    assert "total" in data


@pytest.mark.asyncio
async def test_filter_by_category(client):
    await client.post("/expenses", json={"idempotency_key": "g1", "amount": "80.00",
                                         "category": "Groceries", "description": "Vegs", "date": "2024-04-01"})
    await client.post("/expenses", json={"idempotency_key": "r1", "amount": "15000.00",
                                         "category": "Rent", "description": "Rent", "date": "2024-04-01"})
    data = (await client.get("/expenses?category=Groceries")).json()
    assert data["count"] == 1
    assert all(e["category"] == "Groceries" for e in data["expenses"])


@pytest.mark.asyncio
async def test_sort_date_desc(client):
    for date_str, key in [("2024-01-01", "s-a"), ("2024-03-01", "s-b"), ("2024-02-01", "s-c")]:
        await client.post("/expenses", json={"idempotency_key": key, "amount": "10.00",
                                             "category": "Misc", "description": "x", "date": date_str})
    dates = [e["date"] for e in (await client.get("/expenses?sort=date_desc")).json()["expenses"]]
    assert dates == sorted(dates, reverse=True)


@pytest.mark.asyncio
async def test_total_is_correct(client):
    for key, amt in [("t-a", "100.00"), ("t-b", "250.75")]:
        await client.post("/expenses", json={"idempotency_key": key, "amount": amt,
                                             "category": "Food", "description": "x", "date": "2024-04-01"})
    data = (await client.get("/expenses")).json()
    computed = sum(Decimal(e["amount"]) for e in data["expenses"])
    assert Decimal(data["total"]) == computed


@pytest.mark.asyncio
async def test_categories_endpoint(client):
    await client.post("/expenses", json={"idempotency_key": "ce1", "amount": "50.00",
                                         "category": "Entertainment", "description": "Movie", "date": "2024-04-01"})
    resp = await client.get("/expenses/categories")
    assert resp.status_code == 200
    assert "Entertainment" in resp.json()
