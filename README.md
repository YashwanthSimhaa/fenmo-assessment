# Expense Tracker

A minimal full-stack expense tracker built with **FastAPI** (Python) and **vanilla HTML/JS**, designed for correctness under real-world conditions: network retries, double-submits, and browser refreshes.

**Live app:** `<frontend-url>`  
**API docs:** `<backend-url>/docs`

---

## Quick Start (local)

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
# → http://localhost:8000
# → http://localhost:8000/docs  (Swagger UI)

# Frontend
# Open frontend/index.html in a browser, or serve it:
cd frontend
python -m http.server 3000
# → http://localhost:3000

# Tests
cd backend
pytest tests/ -v
```

---

## Architecture

```
expense-tracker/
├── backend/
│   ├── main.py                  # FastAPI app, CORS, lifespan
│   ├── src/
│   │   ├── database.py          # SQLite setup, table & index creation
│   │   ├── schemas.py           # Pydantic models (request + response)
│   │   └── routes/
│   │       └── expenses.py      # POST /expenses, GET /expenses, GET /expenses/categories
│   ├── tests/
│   │   └── test_expenses.py     # 10 integration tests
│   ├── requirements.txt
│   ├── Procfile                 # Railway deployment
│   └── railway.toml
└── frontend/
    └── index.html               # Single-file UI (HTML + CSS + JS, no build step)
```

---

## Key Design Decisions

### 1. Idempotent POST via `idempotency_key`

The spec explicitly calls out unreliable networks and users clicking submit multiple times. The solution is the industry-standard **idempotency key** pattern (used by Stripe, etc.):

- The frontend generates a `UUID` when the form loads (`crypto.randomUUID()`).
- Every submission sends this key in the request body.
- The backend checks for an existing row with that key **before** inserting.
- If found, it returns the original record unchanged — no duplicate is created.
- Only on a _successful_ submission does the frontend generate a fresh key for the next expense.

This means a user can click "Add Expense" 5 times due to a slow connection and end up with exactly 1 record. The frontend also sets `disabled` on the button during the in-flight request as a secondary UX guard.

### 2. Money as integers (paise)

Storing money as `FLOAT` is wrong — IEEE-754 cannot represent many decimal values exactly, leading to rounding errors that compound over time (e.g. `0.1 + 0.2 !== 0.3`).

Strategy:
- **API input:** accepts `Decimal` via Pydantic, validated to ≤ 2 decimal places.
- **Storage:** `INTEGER` column `amount_paise` (1 INR = 100 paise). Conversion: `paise = int(amount * 100)`.
- **API output:** `Decimal` with 2dp serialised to JSON string (no float loss).
- **Frontend:** reads the string, uses `toLocaleString` for display only.

### 3. Persistence: SQLite + aiosqlite

**Why SQLite?**
- Zero infrastructure — no separate DB server to provision, configure, or secure.
- File-based → easy to inspect, back up, and migrate.
- Perfectly appropriate for a single-user personal finance tool.
- `aiosqlite` wraps it in an async interface compatible with FastAPI's async request handlers.

**Trade-off:** SQLite's write concurrency is limited (one writer at a time). For a multi-user SaaS this would need PostgreSQL. For a personal tool, it's the right call.

**Indexes created:**
- `idx_expenses_category` — fast `WHERE category = ?` filter
- `idx_expenses_date` — fast `ORDER BY date DESC` sort
- `idx_expenses_idempotency` (UNIQUE) — fast idempotency lookup + DB-level duplicate prevention

### 4. Single-file frontend

No build step, no bundler, no framework — just one `index.html`. Rationale:
- Deployable to GitHub Pages, Netlify, S3, or any static host with zero configuration.
- Zero dependency-update surface area.
- The feature set doesn't warrant the overhead of a framework.

The UI still implements all required production patterns: loading skeletons, error states, toast notifications, disabled-button during submission, and form validation before the network call.

### 5. Validation layers

Both layers validate independently — the frontend for fast UX feedback, the backend as the source of truth:

| Rule | Frontend | Backend |
|---|---|---|
| Amount > 0 | ✅ | ✅ Pydantic `field_validator` |
| Amount ≤ 2dp | — | ✅ |
| Amount ≤ ₹1 crore | — | ✅ sanity cap |
| Date not in future | — | ✅ (1-day tolerance for timezones) |
| Required fields present | ✅ | ✅ Pydantic `Field(...)` |
| Category / description non-empty | ✅ | ✅ `min_length=1` |

---

## API Reference

### `POST /expenses`
Create a new expense. Idempotent — safe to retry.

```json
{
  "idempotency_key": "550e8400-e29b-41d4-a716-446655440000",
  "amount": "199.50",
  "category": "Food & Dining",
  "description": "Lunch at MTR",
  "date": "2024-04-20"
}
```

Returns `201 Created` (first call) or the original record (retry). Returns `422` for validation errors.

### `GET /expenses`
List expenses. Optional query parameters:
- `category` — filter by category (case-insensitive)
- `sort=date_desc` — sort newest first

Response includes `expenses[]`, `total` (sum of visible expenses), and `count`.

### `GET /expenses/categories`
Returns an array of all distinct categories in the database. Used to populate the filter dropdown dynamically.

### `GET /health`
Returns `{"status": "ok"}`. Used for uptime checks.

---

## Tests

10 integration tests using `pytest` + `httpx` (ASGI transport, no real HTTP needed):

```
tests/test_expenses.py::test_create_expense              PASSED
tests/test_expenses.py::test_create_expense_idempotent   PASSED  ← key test
tests/test_expenses.py::test_negative_amount_rejected    PASSED
tests/test_expenses.py::test_zero_amount_rejected        PASSED
tests/test_expenses.py::test_missing_fields_rejected     PASSED
tests/test_expenses.py::test_list_expenses               PASSED
tests/test_expenses.py::test_filter_by_category          PASSED
tests/test_expenses.py::test_sort_date_desc              PASSED
tests/test_expenses.py::test_total_is_correct            PASSED
tests/test_expenses.py::test_categories_endpoint         PASSED
```

Each test gets a fresh, isolated SQLite file via the `client` fixture.

---

## Deployment

### Backend → Railway

1. Push `backend/` to a GitHub repo.
2. Create a new Railway project → "Deploy from GitHub repo".
3. Railway auto-detects Python via `Procfile` / `requirements.txt`.
4. Set env var `DB_PATH=/data/expenses.db` (optional, defaults to `expenses.db` in working dir).
5. Copy the Railway public URL.

### Frontend → GitHub Pages

1. In `frontend/index.html`, set `window.ENV_API_BASE` to your Railway URL, or just edit the `API_BASE` constant.
2. Push `frontend/` to `gh-pages` branch or `docs/` folder.
3. Enable GitHub Pages in repo settings.

---

## Trade-offs & Intentional Omissions

| Decision | Reason |
|---|---|
| No authentication | Out of scope for a personal tool in a timebox. In production, add OAuth or API key middleware. |
| No DELETE / PATCH endpoints | Not in acceptance criteria. Easy to add — the DB schema supports it. |
| SQLite instead of Postgres | Right-sized for this use case. Swap `aiosqlite` for `asyncpg` + `SQLAlchemy` to scale. |
| No migrations tooling | With one table and a timebox, `CREATE TABLE IF NOT EXISTS` is sufficient. Would use Alembic in a long-lived project. |
| Totals computed in Python | The result set is small; a `SELECT SUM()` query would also work and be marginally faster at scale. |
| Frontend is vanilla JS | No React/Vue overhead for a feature set this small. Would reconsider if state grew. |
| No edit history / audit log | `created_at` is stored; adding an `updated_at` and a changelog table would be straightforward. |

---

## What I'd do next (given more time)

- **Auth:** JWT or session-based, so the tracker can be safely hosted publicly.
- **Soft deletes:** `deleted_at` timestamp instead of hard `DELETE`.
- **Alembic migrations:** for safe schema evolution.
- **Pagination:** `GET /expenses?page=1&limit=50` for large datasets.
- **CSV export:** one endpoint, trivially useful.
- **OpenTelemetry:** structured logging + tracing for production observability.
