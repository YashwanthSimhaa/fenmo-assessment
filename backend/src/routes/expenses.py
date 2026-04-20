"""
Expenses API routes.

Key design decisions:
- POST is idempotent via idempotency_key: if a client retries (network blip,
  double-submit, page reload), we return the *same* stored expense rather than
  creating a duplicate. This is the industry-standard pattern (used by Stripe, etc.)
- Money is stored as INTEGER paise (1 INR = 100 paise) to avoid float precision
  loss. Conversion happens only at the boundary (input → paise, output → rupees).
- UUIDs are generated server-side for IDs; the client only supplies the
  idempotency_key (which can be any unique string — a UUID generated at form-load works well).
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.database import get_db
from src.schemas import ExpenseCreate, ExpenseListResponse, ExpenseResponse

router = APIRouter(prefix="/expenses", tags=["expenses"])


def _row_to_response(row: aiosqlite.Row) -> ExpenseResponse:
    """Convert a DB row to the API response schema, paise → rupees."""
    return ExpenseResponse(
        id=row["id"],
        amount=Decimal(row["amount_paise"]) / 100,
        category=row["category"],
        description=row["description"],
        date=row["date"],
        created_at=row["created_at"],
    )


@router.post(
    "",
    response_model=ExpenseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new expense (idempotent)",
)
async def create_expense(
    payload: ExpenseCreate,
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Idempotency guarantee:
      If a request with the same idempotency_key has already been processed,
      we return the original expense (HTTP 200) instead of creating a duplicate.
      The caller cannot distinguish a first-time create from a retry — which is
      exactly what we want.
    """
    # 1. Check if we've already processed this key
    async with db.execute(
        "SELECT * FROM expenses WHERE idempotency_key = ?",
        (payload.idempotency_key,),
    ) as cursor:
        existing = await cursor.fetchone()

    if existing:
        # Idempotent replay — return the original record unchanged
        return _row_to_response(existing)

    # 2. Convert rupees → paise (integer arithmetic, no float risk)
    amount_paise = int(payload.amount * 100)

    # 3. Insert new record
    expense_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    await db.execute(
        """
        INSERT INTO expenses (id, idempotency_key, amount_paise, category, description, date, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            expense_id,
            payload.idempotency_key,
            amount_paise,
            payload.category,
            payload.description,
            payload.date.isoformat(),
            created_at,
        ),
    )
    await db.commit()

    return ExpenseResponse(
        id=expense_id,
        amount=payload.amount,
        category=payload.category,
        description=payload.description,
        date=payload.date.isoformat(),
        created_at=created_at,
    )


@router.get(
    "",
    response_model=ExpenseListResponse,
    summary="List expenses with optional filter and sort",
)
async def list_expenses(
    category: Optional[str] = Query(None, description="Filter by category (case-insensitive)"),
    sort: Optional[str] = Query(None, description="Use 'date_desc' for newest first"),
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Returns expenses with:
    - Optional category filter (case-insensitive)
    - Optional date_desc sort
    - Running total of the filtered result set
    """
    query = "SELECT * FROM expenses"
    params: list = []

    if category:
        query += " WHERE LOWER(category) = LOWER(?)"
        params.append(category)

    if sort == "date_desc":
        query += " ORDER BY date DESC, created_at DESC"
    else:
        # Default: newest created first
        query += " ORDER BY created_at DESC"

    async with db.execute(query, params) as cursor:
        rows = await cursor.fetchall()

    expenses = [_row_to_response(r) for r in rows]
    total = sum(e.amount for e in expenses)

    return ExpenseListResponse(
        expenses=expenses,
        total=total,
        count=len(expenses),
    )


@router.get(
    "/categories",
    response_model=list[str],
    summary="List all distinct categories in use",
)
async def list_categories(db: aiosqlite.Connection = Depends(get_db)):
    """Convenience endpoint so the frontend can populate the filter dropdown dynamically."""
    async with db.execute(
        "SELECT DISTINCT category FROM expenses ORDER BY category"
    ) as cursor:
        rows = await cursor.fetchall()
    return [r["category"] for r in rows]
