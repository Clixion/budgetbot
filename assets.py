"""
assets.py — Auto-fetch asset prices.
Stocks/ETFs: Yahoo Finance (yfinance)
Crypto: CoinGecko API (free, no key)
Bonds/Cash: manual only (returns None)
"""

import requests

# CoinGecko ticker → CoinGecko ID mapping (extend as needed)
CRYPTO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "binancecoin",
    "USDT": "tether",
    "USDC": "usd-coin",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "AVAX": "avalanche-2",
    "DOT": "polkadot",
    "MATIC": "matic-network",
    "LINK": "chainlink",
    "UNI": "uniswap",
}


def fetch_stock_price(ticker: str) -> float | None:
    """Fetch stock/ETF price from Yahoo Finance."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        hist = t.history(period="1d")
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception as e:
        print(f"[assets] yfinance error for {ticker}: {e}")
        return None


def fetch_crypto_price(ticker: str) -> float | None:
    """Fetch crypto price from CoinGecko (USD)."""
    coin_id = CRYPTO_IDS.get(ticker.upper())
    if not coin_id:
        # Try lowercase ticker as fallback
        coin_id = ticker.lower()

    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if coin_id in data:
            return float(data[coin_id]["usd"])
        return None
    except Exception as e:
        print(f"[assets] CoinGecko error for {ticker}: {e}")
        return None


def fetch_price(ticker: str, asset_type: str) -> float | None:
    """
    Main dispatcher. Returns price in USD for stocks/crypto,
    None for bonds/cash (manual only).
    """
    ticker = ticker.upper()

    if asset_type == "stock":
        return fetch_stock_price(ticker)
    elif asset_type == "crypto":
        return fetch_crypto_price(ticker)
    else:
        # bonds, cash — no auto-fetch
        return None
