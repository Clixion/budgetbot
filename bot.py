"""
bot.py — Telegram Budget Bot (python-telegram-bot + Claude API)
Supports: expense logging, income logging, custom categories,
          asset tracking, dashboard, and receipt image scanning.
"""

import os
import json
import re
import base64
import requests as req_lib
from datetime import datetime
from flask import Flask, request, Response, jsonify
import anthropic
import sheets
import assets

app = Flask(__name__)
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


# ── Telegram helpers ───────────────────────────────────────────────────────────

def send_message(chat_id: int, text: str):
    req_lib.post(f"{TELEGRAM_API}/sendMessage", json={
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    })


def download_image(file_id: str) -> tuple[bytes, str]:
    """Download image from Telegram servers."""
    # Get file path
    r = req_lib.get(f"{TELEGRAM_API}/getFile", params={"file_id": file_id})
    file_path = r.json()["result"]["file_path"]
    # Download file
    url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
    img_r = req_lib.get(url, timeout=15)
    img_r.raise_for_status()
    ext = file_path.split(".")[-1].lower()
    media_type = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
    return img_r.content, media_type


# ── Claude prompts ─────────────────────────────────────────────────────────────

def build_system_prompt() -> str:
    try:
        exp_cats = [r["name"] for r in sheets.get_categories("expense")]
        inc_cats = [r["name"] for r in sheets.get_categories("income")]
    except Exception:
        exp_cats = ["Food", "Transport", "Shopping", "Entertainment", "Health", "Travel", "Utilities", "Other"]
        inc_cats = ["Salary", "Freelance", "Business", "Investment", "Other"]

    return f"""You are a personal finance assistant in a Telegram bot for an Indonesian user.
Parse the user's message and return ONLY a JSON object (no markdown, no explanation).
The user may write in English, Indonesian, or a mix of both.

Classify into one of these intents:
- "log_expense": user spent money
- "log_income": user received money
- "query_expenses": user wants spending summary
- "query_income": user wants income summary
- "query_cashflow": user wants income vs expenses
- "update_asset": user updating a holding
- "query_assets": user wants portfolio
- "query_networth": user wants total net worth
- "add_category": user wants to add a category
- "remove_category": user wants to remove a category
- "list_categories": user wants to see categories
- "unknown": doesn't fit

Current expense categories: {exp_cats}
Current income categories: {inc_cats}

Indonesian amounts: ribu/rb/k = thousands, juta/jt/m = millions.
85 ribu = 85000, 5 juta = 5000000, 1.5jt = 1500000.

For "log_expense":
{{"intent":"log_expense","amount":<IDR number>,"category":<from expense list>,"description":<short>,"location":<or null>}}

For "log_income":
{{"intent":"log_income","amount":<IDR number>,"source":<who paid>,"category":<from income list>,"description":<short or null>}}

For "query_expenses" or "query_income":
{{"intent":"query_expenses","period":<"today"|"this_week"|"this_month"|"last_month">,"category":<or null>}}

For "query_cashflow":
{{"intent":"query_cashflow","period":<"today"|"this_week"|"this_month"|"last_month">}}

For "update_asset":
{{"intent":"update_asset","ticker":<UPPERCASE>,"units":<number>,"asset_type":<"stock"|"crypto"|"bond"|"cash">,"name":<friendly name>}}

For "query_assets" or "query_networth":
{{"intent":"query_assets"}} or {{"intent":"query_networth"}}

For "add_category":
{{"intent":"add_category","name":<name>,"cat_type":<"expense"|"income"|"both">}}

For "remove_category":
{{"intent":"remove_category","name":<name>}}

For "list_categories":
{{"intent":"list_categories","cat_type":<"expense"|"income"|null>}}

Examples:
- "Habis 85rb makan siang di warung" → log_expense, 85000, Food, location=warung
- "Tadi naik grab 45 ribu" → log_expense, 45000, Transport
- "Masuk gaji 10 juta" → log_income, 10000000, Salary
- "Dapat bayaran client ABC 5jt" → log_income, 5000000, Freelance
- "Pengeluaran minggu ini?" → query_expenses, this_week
- "Cashflow bulan ini?" → query_cashflow, this_month
- "I have 3 shares of VOO" → update_asset, VOO, 3, stock
- "Show portfolio" → query_assets
"""


RECEIPT_PROMPT = """You are a receipt scanner for a personal finance app.
Extract details from this receipt photo and return ONLY a JSON object (no markdown).

Return:
{{
  "merchant": <store/restaurant name or null>,
  "amount": <total amount as IDR number — if USD, multiply by 16000>,
  "category": <best match from: {exp_cats}>,
  "description": <short e.g. "Dinner at Sushi Tei">,
  "location": <merchant name or null>,
  "confidence": <"high"|"medium"|"low">
}}

If total amount is unreadable:
{{"error": "Cannot read receipt amount"}}

Tips:
- Look for: Total, Grand Total, Jumlah, Bayar, Amount Due
- Indonesian format: 85.000 = 85000 (dots are thousand separators)
"""


def ask_claude(message: str) -> dict:
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system=build_system_prompt(),
        messages=[{"role": "user", "content": message}]
    )
    raw = re.sub(r"```json|```", "", response.content[0].text.strip()).strip()
    return json.loads(raw)


def scan_receipt(image_bytes: bytes, media_type: str, caption: str = "") -> dict:
    try:
        exp_cats = [r["name"] for r in sheets.get_categories("expense")]
    except Exception:
        exp_cats = ["Food", "Transport", "Shopping", "Entertainment", "Health", "Travel", "Utilities", "Other"]

    image_data = base64.standard_b64encode(image_bytes).decode("utf-8")
    prompt = RECEIPT_PROMPT.format(exp_cats=exp_cats)
    if caption:
        prompt += f'\n\nUser caption: "{caption}" — use it to help with category/description.'

    result = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
                {"type": "text", "text": prompt}
            ]
        }]
    )
    raw = re.sub(r"```json|```", "", result.content[0].text.strip()).strip()
    return json.loads(raw)


def fmt(amount: float) -> str:
    return "Rp" + f"{amount:,.0f}".replace(",", ".")


# ── Handlers ───────────────────────────────────────────────────────────────────

def handle_receipt(image_bytes: bytes, media_type: str, caption: str = "") -> str:
    try:
        data = scan_receipt(image_bytes, media_type, caption)
    except Exception as e:
        return f"⚠️ Could not process image: {str(e)}"

    if "error" in data:
        return (
            f"⚠️ {data['error']}\n\n"
            "Try a clearer photo, or log manually:\n"
            "_\"Habis 85rb makan siang\"_"
        )

    amount = float(data.get("amount", 0))
    if amount <= 0:
        return "⚠️ Could not read the total. Try a clearer photo or log manually."

    now = datetime.now()
    sheets.append_expense({
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "amount": amount,
        "category": data.get("category", "Other"),
        "description": data.get("description", ""),
        "location": data.get("location", ""),
    })

    confidence = data.get("confidence", "medium")
    confidence_note = "" if confidence == "high" else f"\n⚠️ _Confidence: {confidence} — double check amount_"

    return (
        f"🧾 *Receipt scanned!*\n"
        f"💸 {fmt(amount)}\n"
        f"📂 {data.get('category', 'Other')}\n"
        f"📝 {data.get('description', '')}\n"
        f"📍 {data.get('location') or '—'}"
        f"{confidence_note}"
    )


def handle_log_expense(data: dict) -> str:
    now = datetime.now()
    sheets.append_expense({
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "amount": data["amount"],
        "category": data.get("category", "Other"),
        "description": data.get("description", ""),
        "location": data.get("location", ""),
    })
    return (
        f"✅ *Expense logged*\n"
        f"💸 {fmt(data['amount'])}\n"
        f"📂 {data.get('category', 'Other')}\n"
        f"📝 {data.get('description', '')}\n"
        f"📍 {data.get('location') or '—'}"
    )


def handle_log_income(data: dict) -> str:
    now = datetime.now()
    sheets.append_income({
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "amount": data["amount"],
        "source": data.get("source", ""),
        "category": data.get("category", "Other"),
        "description": data.get("description", ""),
    })
    return (
        f"✅ *Income logged*\n"
        f"💰 {fmt(data['amount'])}\n"
        f"🏷 {data.get('category', 'Other')}\n"
        f"🏢 {data.get('source') or '—'}"
    )


def handle_query_expenses(data: dict) -> str:
    period = data.get("period", "this_month")
    rows = sheets.get_expenses(period=period, category=data.get("category"))
    if not rows:
        return f"No expenses for *{period.replace('_', ' ')}*."
    total = sum(r["amount"] for r in rows)
    by_cat = {}
    for r in rows:
        by_cat[r["category"]] = by_cat.get(r["category"], 0) + r["amount"]
    lines = [f"📊 *Expenses — {period.replace('_', ' ').title()}*\n"]
    for cat, amt in sorted(by_cat.items(), key=lambda x: -x[1]):
        lines.append(f"  {cat}: {fmt(amt)}")
    lines.append(f"\n💸 *Total: {fmt(total)}*")
    lines.append(f"🔗 {os.environ.get('DASHBOARD_URL', '')}")
    return "\n".join(lines)


def handle_query_income(data: dict) -> str:
    period = data.get("period", "this_month")
    rows = sheets.get_income(period=period, category=data.get("category"))
    if not rows:
        return f"No income for *{period.replace('_', ' ')}*."
    total = sum(r["amount"] for r in rows)
    by_cat = {}
    for r in rows:
        by_cat[r["category"]] = by_cat.get(r["category"], 0) + r["amount"]
    lines = [f"💰 *Income — {period.replace('_', ' ').title()}*\n"]
    for cat, amt in sorted(by_cat.items(), key=lambda x: -x[1]):
        lines.append(f"  {cat}: {fmt(amt)}")
    lines.append(f"\n✅ *Total: {fmt(total)}*")
    lines.append(f"🔗 {os.environ.get('DASHBOARD_URL', '')}")
    return "\n".join(lines)


def handle_query_cashflow(data: dict) -> str:
    period = data.get("period", "this_month")
    total_exp = sum(r["amount"] for r in sheets.get_expenses(period=period))
    total_inc = sum(r["amount"] for r in sheets.get_income(period=period))
    net = total_inc - total_exp
    return (
        f"📈 *Cashflow — {period.replace('_', ' ').title()}*\n\n"
        f"💰 Income:   {fmt(total_inc)}\n"
        f"💸 Expenses: {fmt(total_exp)}\n"
        f"━━━━━━━━━━━━\n"
        f"Net: {'🟢 +' if net >= 0 else '🔴 '}{fmt(abs(net))}\n\n"
        f"🔗 {os.environ.get('DASHBOARD_URL', '')}"
    )


def handle_update_asset(data: dict) -> str:
    ticker = data["ticker"].upper()
    units = float(data["units"])
    asset_type = data.get("asset_type", "stock")
    price = assets.fetch_price(ticker, asset_type)
    value = price * units if price else None
    sheets.upsert_asset({
        "ticker": ticker, "name": data.get("name", ticker),
        "type": asset_type, "units": units,
        "price": price or 0, "value": value or 0,
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    return (
        f"✅ *Asset updated*\n"
        f"📈 {ticker} ({asset_type})\n"
        f"🔢 Units: {units}\n"
        f"💲 Price: {'$'+f'{price:,.2f}' if price else 'unavailable'}\n"
        f"💼 Value: {'$'+f'{value:,.2f}' if value else '—'}"
    )


def handle_query_assets() -> str:
    rows = sheets.get_assets()
    if not rows:
        return "No assets yet.\nTry: _'I have 3 shares of VOO'_"
    total_usd, total_idr = 0, 0
    lines = ["💼 *Portfolio*\n"]
    for row in rows:
        ticker, asset_type = row["ticker"], row["type"]
        units = float(row["units"])
        price = assets.fetch_price(ticker, asset_type)
        value = price * units if price else float(row.get("value", 0))
        if price:
            sheets.upsert_asset({**row, "price": price, "value": value,
                                  "updated": datetime.now().strftime("%Y-%m-%d %H:%M")})
        if asset_type in ("stock", "crypto"):
            total_usd += value
            lines.append(f"  {ticker}: ${value:,.2f} ({units} @ ${price:,.2f})" if price else f"  {ticker}: {units} units")
        else:
            total_idr += value
            lines.append(f"  {ticker}: {fmt(value)}")
    lines.append(f"\n💵 Stocks/Crypto: ${total_usd:,.2f}")
    if total_idr:
        lines.append(f"🏦 IDR Assets: {fmt(total_idr)}")
    lines.append(f"\n🔗 {os.environ.get('DASHBOARD_URL', '')}")
    return "\n".join(lines)


def handle_query_networth() -> str:
    rows = sheets.get_assets()
    usd = sum(float(r.get("value", 0)) for r in rows if r["type"] in ("stock", "crypto"))
    idr = sum(float(r.get("value", 0)) for r in rows if r["type"] in ("bond", "cash"))
    return (
        f"🏆 *Net Worth*\n\n"
        f"📈 Investments: ${usd:,.2f}\n"
        f"🏦 IDR Assets: {fmt(idr)}\n\n"
        f"🔗 {os.environ.get('DASHBOARD_URL', '')}"
    )


def handle_add_category(data: dict) -> str:
    name = data.get("name", "").strip().title()
    cat_type = data.get("cat_type", "expense")
    if not name:
        return "Please provide a category name."
    return f"✅ Added *{name}* to {cat_type} categories." if sheets.add_category(name, cat_type) else f"⚠️ *{name}* already exists."


def handle_remove_category(data: dict) -> str:
    name = data.get("name", "").strip()
    return f"✅ Removed *{name}*" if sheets.remove_category(name) else f"⚠️ *{name}* not found."


def handle_list_categories(data: dict) -> str:
    rows = sheets.get_categories(data.get("cat_type"))
    exp = [r["name"] for r in rows if r["type"] in ("expense", "both")]
    inc = [r["name"] for r in rows if r["type"] in ("income", "both")]
    lines = ["📂 *Your Categories*\n"]
    if exp:
        lines.append("💸 *Expense:*\n  " + ", ".join(exp))
    if inc:
        lines.append("💰 *Income:*\n  " + ", ".join(inc))
    lines.append('\nAdd: "Add category Groceries for expense"')
    lines.append('Remove: "Remove category Shopping"')
    return "\n".join(lines)


# ── Webhook ────────────────────────────────────────────────────────────────────

@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    update = request.get_json()
    if not update:
        return "ok"

    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    if not chat_id:
        return "ok"

    text = message.get("text", "").strip()
    photo = message.get("photo")
    caption = message.get("caption", "").strip()

    try:
        # ── Photo → receipt scanner ───────────────────────────────────────────
        if photo:
            # Use highest resolution photo (last in array)
            file_id = photo[-1]["file_id"]
            image_bytes, media_type = download_image(file_id)
            reply = handle_receipt(image_bytes, media_type, caption)

        # ── Text → intent parser ──────────────────────────────────────────────
        elif text:
            if text.lower() in ("/start", "/help"):
                reply = (
                    "👋 *Budget Bot*\n\n"
                    "Just talk to me naturally:\n\n"
                    "💸 _\"Habis 85rb makan siang\"_\n"
                    "💰 _\"Masuk gaji 10 juta\"_\n"
                    "📊 _\"Cashflow bulan ini?\"_\n"
                    "📈 _\"I have 3 shares of VOO\"_\n"
                    "🧾 Send a receipt photo to auto-log it\n\n"
                    "📂 _\"Show my categories\"_\n"
                    "➕ _\"Add category Groceries\"_\n\n"
                    f"📊 Dashboard: {os.environ.get('DASHBOARD_URL', '')}"
                )
            else:
                parsed = ask_claude(text)
                intent = parsed.get("intent", "unknown")
                handlers = {
                    "log_expense":     lambda: handle_log_expense(parsed),
                    "log_income":      lambda: handle_log_income(parsed),
                    "query_expenses":  lambda: handle_query_expenses(parsed),
                    "query_income":    lambda: handle_query_income(parsed),
                    "query_cashflow":  lambda: handle_query_cashflow(parsed),
                    "update_asset":    lambda: handle_update_asset(parsed),
                    "query_assets":    lambda: handle_query_assets(),
                    "query_networth":  lambda: handle_query_networth(),
                    "add_category":    lambda: handle_add_category(parsed),
                    "remove_category": lambda: handle_remove_category(parsed),
                    "list_categories": lambda: handle_list_categories(parsed),
                }
                reply = handlers.get(intent, lambda: (
                    "I didn't understand that. Try:\n"
                    "• _\"Habis 85rb makan siang\"_\n"
                    "• _\"Masuk gaji 10 juta\"_\n"
                    "• _\"Cashflow bulan ini?\"_\n"
                    "• Send a 📷 receipt photo\n"
                    "• /help for more"
                ))()
        else:
            reply = "Send me a message or a receipt photo 📷"

    except Exception as e:
        reply = f"⚠️ Error: {str(e)}"

    send_message(chat_id, reply)
    return "ok"


@app.route("/dashboard")
def dashboard():
    with open("dashboard/index.html", "r") as f:
        return f.read()


@app.route("/api/expenses")
def api_expenses():
    return jsonify(sheets.get_expenses(period=request.args.get("period", "this_month")))


@app.route("/api/income")
def api_income():
    return jsonify(sheets.get_income(period=request.args.get("period", "this_month")))


@app.route("/api/assets")
def api_assets():
    return jsonify(sheets.get_assets())


@app.route("/api/categories")
def api_categories():
    return jsonify(sheets.get_categories())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
