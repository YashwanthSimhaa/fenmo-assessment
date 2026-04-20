"""
Pydantic schemas for request validation and response serialization.
"""

from pydantic import BaseModel, Field, field_validator
import datetime as dt
from decimal import Decimal


# ── Request ──────────────────────────────────────────────────────────────────

class ExpenseCreate(BaseModel):
    idempotency_key: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Client-generated unique key to make POST idempotent",
    )
    amount: Decimal = Field(..., description="Expense amount in rupees (e.g. 199.50)")
    category: str = Field(..., min_length=1, max_length=64)
    description: str = Field(..., min_length=1, max_length=512)
    date: dt.date = Field(..., description="Date of the expense (YYYY-MM-DD)")

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Amount must be greater than zero")
        # Max 2 decimal places for money
        if v.as_tuple().exponent < -2:
            raise ValueError("Amount must have at most 2 decimal places")
        # Sanity cap — no single expense > ₹10 crore
        if v > Decimal("10000000"):
            raise ValueError("Amount exceeds maximum allowed value")
        return v

    @field_validator("category")
    @classmethod
    def category_clean(cls, v: str) -> str:
        return v.strip()

    @field_validator("description")
    @classmethod
    def description_clean(cls, v: str) -> str:
        return v.strip()

    @field_validator("date")
    @classmethod
    def date_not_too_far_future(cls, v: dt.date) -> dt.date:
        today = dt.date.today()
        if v > today + dt.timedelta(days=1):
            raise ValueError("Expense date cannot be in the future")
        return v


# ── Response ─────────────────────────────────────────────────────────────────

class ExpenseResponse(BaseModel):
    id: str
    amount: Decimal          # rupees with 2dp, for JSON serialization
    category: str
    description: str
    date: str                # ISO date string
    created_at: str          # ISO datetime string

    model_config = {"from_attributes": True}


class ExpenseListResponse(BaseModel):
    expenses: list[ExpenseResponse]
    total: Decimal           # sum of currently visible expenses
    count: int
