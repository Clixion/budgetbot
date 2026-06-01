"""
db.py (imported as sheets) — Supabase database layer.
Replaces Google Sheets. Uses Supabase REST API directly via requests.
No extra SDK needed beyond what's already installed.
"""

import os
import requests
from datetime import datetime, timedelta

# ── Supabase config ────────────────────────────────────────────────────────────

def _headers():
    key = os.environ["SUPABASE_KEY"]
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }

def _url(table: str) -> str:
    base = os.environ["SUPABASE_URL"].rstrip("/")
    return f"{base}/rest/v1/{table}"


# ── Date helpers ───────────────────────────────────────────────────────────────

def _date_range(period: str):
    today = datetime.today().date()
    if period == "today":
        return str(today), str(today)
    elif period == "this_week":
        start = today - timedelta(days=today.weekday())
        return str(start), str(today)
    elif period == "last_month":
        first_this = today.replace(day=1)
        end = first_this - timedelta(days=1)
        start = end.replace(day=1)
        return str(start), str(end)
    else:  # this_month
        return str(today.replace(day=1)), str(today)


# ── Expenses ───────────────────────────────────────────────────────────────────

def append_expense(row: dict):
    payload = {
        "date": row.get("date"),
        "time": row.get("time"),
        "amount": float(row.get("amount", 0)),
        "category": row.get("category", "Other"),
        "description": row.get("description", ""),
        "location": row.get("location", ""),
    }
    r = requests.post(_url("expenses"), json=payload, headers=_headers())
    r.raise_for_status()


def get_expenses(period: str = "this_month", category: str = None) -> list[dict]:
    start, end = _date_range(period)
    params = {
        "date": f"gte.{start}",
        "date": f"lte.{end}",
        "order": "date.desc,time.desc",
    }
    # Build query string manually to support multiple filters on same field
    qs = f"date=gte.{start}&date=lte.{end}&order=date.desc,time.desc"
    if category:
        qs += f"&category=ilike.{category}"

    r = requests.get(f"{_url('expenses')}?{qs}", headers=_headers())
    r.raise_for_status()
    rows = r.json()
    for row in rows:
        row["amount"] = float(row.get("amount", 0))
    return rows


# ── Income ─────────────────────────────────────────────────────────────────────

def append_income(row: dict):
    payload = {
        "date": row.get("date"),
        "time": row.get("time"),
        "amount": float(row.get("amount", 0)),
        "source": row.get("source", ""),
        "category": row.get("category", "Other"),
        "description": row.get("description", ""),
    }
    r = requests.post(_url("income"), json=payload, headers=_headers())
    r.raise_for_status()


def get_income(period: str = "this_month", category: str = None) -> list[dict]:
    start, end = _date_range(period)
    qs = f"date=gte.{start}&date=lte.{end}&order=date.desc,time.desc"
    if category:
        qs += f"&category=ilike.{category}"
    r = requests.get(f"{_url('income')}?{qs}", headers=_headers())
    r.raise_for_status()
    rows = r.json()
    for row in rows:
        row["amount"] = float(row.get("amount", 0))
    return rows


# ── Assets ─────────────────────────────────────────────────────────────────────

def upsert_asset(row: dict):
    payload = {
        "ticker": row["ticker"].upper(),
        "name": row.get("name", row["ticker"]),
        "type": row.get("type", "stock"),
        "units": float(row.get("units", 0)),
        "price": float(row.get("price", 0)),
        "value": float(row.get("value", 0)),
        "updated": row.get("updated", datetime.now().strftime("%Y-%m-%d %H:%M")),
    }
    headers = {**_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"}
    r = requests.post(_url("assets"), json=payload, headers=headers)
    r.raise_for_status()


def get_assets() -> list[dict]:
    r = requests.get(f"{_url('assets')}?order=type.asc,ticker.asc", headers=_headers())
    r.raise_for_status()
    return r.json()


# ── Categories ─────────────────────────────────────────────────────────────────

DEFAULT_EXPENSE_CATS = [
    "Food", "Transport", "Shopping", "Entertainment",
    "Health", "Travel", "Utilities", "Other"
]
DEFAULT_INCOME_CATS = ["Salary", "Freelance", "Business", "Investment", "Other"]


def _seed_categories():
    """Insert default categories if table is empty."""
    r = requests.get(f"{_url('categories')}?limit=1", headers=_headers())
    if r.ok and len(r.json()) == 0:
        defaults = (
            [{"name": c, "type": "expense"} for c in DEFAULT_EXPENSE_CATS] +
            [{"name": c, "type": "income"} for c in DEFAULT_INCOME_CATS]
        )
        requests.post(_url("categories"), json=defaults, headers=_headers())


def get_categories(cat_type: str = None) -> list[dict]:
    _seed_categories()
    qs = "order=name.asc"
    if cat_type:
        qs += f"&type=in.({cat_type},both)"
    r = requests.get(f"{_url('categories')}?{qs}", headers=_headers())
    r.raise_for_status()
    return r.json()


def add_category(name: str, cat_type: str = "expense") -> bool:
    # Check if exists
    r = requests.get(f"{_url('categories')}?name=ilike.{name}", headers=_headers())
    if r.ok and len(r.json()) > 0:
        return False
    payload = {"name": name.title(), "type": cat_type}
    r = requests.post(_url("categories"), json=payload, headers=_headers())
    r.raise_for_status()
    return True


def remove_category(name: str) -> bool:
    r = requests.delete(
        f"{_url('categories')}?name=ilike.{name}",
        headers={**_headers(), "Prefer": "return=representation"}
    )
    r.raise_for_status()
    return len(r.json()) > 0
