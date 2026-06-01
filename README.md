# 💬 Budget Bot (Telegram)

A personal finance bot on Telegram — log expenses and income in plain Bahasa/English,
track your investment portfolio, scan receipts, and view everything on a web dashboard.

---

## What it does

| Via Telegram | Example |
|---|---|
| Log expense | "Habis 85rb makan siang di warung" |
| Log income | "Masuk gaji 10 juta" |
| Scan receipt | Send a photo 📷 — auto-logged |
| Check cashflow | "Cashflow bulan ini?" |
| Update holdings | "I have 3 shares of VOO" |
| View portfolio | "Show my portfolio" |
| Manage categories | "Add category Groceries for expense" |

---

## Full Setup Guide

### Step 1 — Anthropic API Key
1. Go to https://console.anthropic.com → sign up
2. API Keys → Create Key → copy it

### Step 2 — Telegram Bot
1. Open Telegram → search @BotFather → start chat
2. Send /newbot
3. Give it a name (e.g. "Felix Budget Bot")
4. Give it a username (e.g. felixbudget_bot)
5. BotFather gives you a token like 7123456789:AAFxxx... → copy it

### Step 3 — Supabase (database, free)
1. Go to https://supabase.com → sign up → New project
2. Name it anything, pick any region → Create project → wait ~1 min
3. Go to SQL Editor (left sidebar) → paste the SQL below → click Run:

```sql
create table expenses (
  id bigint generated always as identity primary key,
  date date not null,
  time text,
  amount numeric not null,
  category text default 'Other',
  description text,
  location text,
  created_at timestamptz default now()
);

create table income (
  id bigint generated always as identity primary key,
  date date not null,
  time text,
  amount numeric not null,
  source text,
  category text default 'Other',
  description text,
  created_at timestamptz default now()
);

create table assets (
  id bigint generated always as identity primary key,
  ticker text unique not null,
  name text,
  type text default 'stock',
  units numeric default 0,
  price numeric default 0,
  value numeric default 0,
  updated text
);

create table categories (
  id bigint generated always as identity primary key,
  name text not null,
  type text default 'expense'
);
```

4. Go to Project Settings → API
5. Copy your Project URL and anon/public key

### Step 4 — GitHub
1. Go to https://github.com → sign up → New repository → name it budgetbot → Create
2. Upload files:
   - Drag bot.py, sheets.py, assets.py, requirements.txt, README.md directly
   - For the dashboard folder: click Add file → Create new file
     → type dashboard/index.html in the name box
     → paste the contents of dashboard/index.html → Commit

### Step 5 — Render (hosting, free)
1. Go to https://render.com → sign up
2. New → Web Service → Connect GitHub → select budgetbot repo
3. Settings:
   - Build command: pip install -r requirements.txt
   - Start command: gunicorn bot:app
   - Instance type: Free
4. Go to Environment tab → add these 5 variables:

| Key | Value |
|---|---|
| ANTHROPIC_API_KEY | from Step 1 |
| TELEGRAM_BOT_TOKEN | from Step 2 |
| SUPABASE_URL | from Step 3 (Project URL) |
| SUPABASE_KEY | from Step 3 (anon/public key) |
| DASHBOARD_URL | https://your-app-name.onrender.com/dashboard |

5. Click Deploy — takes 2-3 minutes
6. Note your app URL e.g. https://budgetbot-xxxx.onrender.com

### Step 6 — Connect Telegram webhook
After Render finishes deploying, open this URL in your browser
(replace YOUR_TOKEN and your-app-name with your actual values):

https://api.telegram.org/botYOUR_TOKEN/setWebhook?url=https://your-app-name.onrender.com/telegram

It should return: {"ok":true,"result":true}
That means your bot is live.

### Step 7 — Test it
1. Open Telegram → search your bot by its username → Start
2. Send /start to see the welcome message
3. Try these:
   - "Habis 85rb makan siang"
   - "Masuk gaji 10 juta"
   - "Cashflow bulan ini?"
   - Send a receipt photo 📷
4. Open your dashboard at https://your-app-name.onrender.com/dashboard

---

## File structure

```
budgetbot/
├── bot.py              # Telegram webhook + Claude AI parser
├── sheets.py           # Supabase database layer
├── assets.py           # Yahoo Finance + CoinGecko price fetcher
├── requirements.txt    # Python dependencies
├── dashboard/
│   └── index.html      # Web dashboard (phone + laptop)
└── README.md
```

---

## Supported commands (natural language)

**Expenses**
- "Habis 85rb makan siang di warung"
- "Tadi naik grab 45 ribu"
- "Spent 200k on groceries"

**Income**
- "Masuk gaji 10 juta"
- "Dapat bayaran client ABC 5jt"
- "Received $500 from freelance project"

**Reports**
- "Cashflow bulan ini?"
- "Pengeluaran minggu ini berapa?"
- "How much did I spend on food this month?"

**Assets**
- "I have 3 shares of VOO"
- "Update BTC to 0.05"
- "Show my portfolio"
- "Berapa total kekayaan saya?"

**Categories**
- "Show my categories"
- "Add category Groceries for expense"
- "Tambahin kategori Investasi untuk income"
- "Remove category Shopping"

**Receipt scanning**
- Just send a photo 📷 of any receipt — auto-logged
- Add a caption for extra context e.g. "makan malam sama partner"

---

## Supported assets (auto-priced)

**Stocks/ETFs** (Yahoo Finance): VOO, VTI, SLV, IAU, GLD, QQQ, and any valid ticker

**Crypto** (CoinGecko): BTC, ETH, SOL, BNB, XRP, ADA, DOGE, AVAX, and more

**Bonds/Cash (IDR)**: manual update only — no public API for Indonesian retail bonds

---

## Cost breakdown

| Service | Cost |
|---|---|
| Telegram bot | Free forever |
| Supabase database | Free (500MB, pauses after 90 days inactivity) |
| Render hosting | Free (sleeps after 15min idle, ~30s first response) |
| Yahoo Finance + CoinGecko | Free |
| Anthropic API (Claude Haiku) | ~$1-3/month |

---

## Notes

- Render free tier sleeps after 15 minutes of inactivity — first message after idle
  takes ~30-60 seconds to respond. Subsequent messages are instant.
- To keep it always-on, upgrade Render to the $7/month plan.
- Supabase pauses after 90 days of no activity — just log in and click Restore.
- Amount formats supported: 85000, 85k, 85rb, 1.5jt, 1.5m, 1500000
