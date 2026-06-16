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


def get_expenses(period: str = "this_month", category: str = None,
                  start_date: str = None, end_date: str = None) -> list[dict]:
    if start_date and end_date:
        start, end = start_date, end_date
    else:
        start, end = _date_range(period)
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


def get_income(period: str = "this_month", category: str = None,
               start_date: str = None, end_date: str = None) -> list[dict]:
    if start_date and end_date:
        start, end = start_date, end_date
    else:
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
    # Check if exists (case-insensitive)
    name_clean = name.strip()
    r = requests.get(f"{_url('categories')}?name=ilike.{name_clean}", headers=_headers())
    if r.ok and len(r.json()) > 0:
        return False
    payload = {"name": name_clean.title(), "type": cat_type}
    r = requests.post(_url("categories"), json=payload, headers=_headers())
    r.raise_for_status()
    return True


def remove_category(name: str) -> bool:
    """Remove a category by name, case-insensitive, trimmed."""
    name_clean = name.strip()
    if not name_clean:
        return False
    # Use ilike with wildcards to be forgiving of minor casing/spacing differences
    r = requests.delete(
        f"{_url('categories')}?name=ilike.*{name_clean}*",
        headers={**_headers(), "Prefer": "return=representation"}
    )
    r.raise_for_status()
    deleted = r.json()
    return len(deleted) > 0


# ── Delete transactions ─────────────────────────────────────────────────────────

def delete_last_expenses(count: int = 1) -> list[dict]:
    """Delete the most recent N expense rows. Returns deleted rows."""
    r = requests.get(
        f"{_url('expenses')}?order=created_at.desc&limit={count}",
        headers=_headers()
    )
    r.raise_for_status()
    rows = r.json()
    if not rows:
        return []
    ids = [str(row["id"]) for row in rows]
    id_filter = "id=in.(" + ",".join(ids) + ")"
    del_headers = {**_headers(), "Prefer": "return=representation"}
    requests.delete(f"{_url('expenses')}?{id_filter}", headers=del_headers)
    return rows


def delete_last_income(count: int = 1) -> list[dict]:
    """Delete the most recent N income rows. Returns deleted rows."""
    r = requests.get(
        f"{_url('income')}?order=created_at.desc&limit={count}",
        headers=_headers()
    )
    r.raise_for_status()
    rows = r.json()
    if not rows:
        return []
    ids = [str(row["id"]) for row in rows]
    id_filter = "id=in.(" + ",".join(ids) + ")"
    del_headers = {**_headers(), "Prefer": "return=representation"}
    requests.delete(f"{_url('income')}?{id_filter}", headers=del_headers)
    return rows


# ── Edit transactions ────────────────────────────────────────────────────────────

def _do_edit(table: str, row_id: int, field: str, value) -> dict:
    """Apply patch to a row and return updated record."""
    if field == "amount":
        value = float(value)
    patch_headers = {**_headers(), "Prefer": "return=representation"}
    pr = requests.patch(
        f"{_url(table)}?id=eq.{row_id}",
        json={field: value},
        headers=patch_headers
    )
    pr.raise_for_status()
    result = pr.json()
    return result[0] if result else {}


def _search_table(table: str, search: str, search_fields: list) -> dict | None:
    """Find most recent row matching search keyword across multiple fields."""
    search = search.strip()
    if search.lower() in ("terakhir", "last", "latest"):
        r = requests.get(
            f"{_url(table)}?order=created_at.desc&limit=1",
            headers=_headers()
        )
        r.raise_for_status()
        rows = r.json()
        return rows[0] if rows else None

    # Try exact phrase first
    conditions = ",".join(f"{f}.ilike.*{search}*" for f in search_fields)
    r = requests.get(
        f"{_url(table)}?or=({conditions})&order=created_at.desc&limit=5",
        headers=_headers()
    )
    r.raise_for_status()
    rows = r.json()
    if rows:
        return rows[0]

    # Fall back to individual words (handles multi-word search like "gaji pegawai")
    words = [w for w in search.split() if len(w) > 2]
    for word in words:
        conditions = ",".join(f"{f}.ilike.*{word}*" for f in search_fields)
        r = requests.get(
            f"{_url(table)}?or=({conditions})&order=created_at.desc&limit=1",
            headers=_headers()
        )
        r.raise_for_status()
        rows = r.json()
        if rows:
            return rows[0]

    return None


def find_and_edit_expense(search: str, field: str, value) -> dict | None:
    """Find most recent expense matching search keyword and edit a field."""
    row = _search_table("expenses", search, ["description", "category", "location"])
    if not row:
        return None
    updated = _do_edit("expenses", row["id"], field, value)
    return updated or {**row, field: value}


def find_and_edit_income(search: str, field: str, value) -> dict | None:
    """Find most recent income matching search keyword and edit a field."""
    row = _search_table("income", search, ["description", "category", "source"])
    if not row:
        return None
    updated = _do_edit("income", row["id"], field, value)
    return updated or {**row, field: value}
