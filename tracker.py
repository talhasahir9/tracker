import requests
import time
import pandas as pd
import streamlit as st

# CONFIG (Use Streamlit secrets or environment variables)
DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/tokens"
SOLSCAN_API = "https://public-api.solscan.io/account/tokens?account="
COINGECKO_SOL_PRICE = "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"

TELEGRAM_BOT_TOKEN = st.secrets.get("TELEGRAM_BOT_TOKEN", "7449572257:AAFH3SycivPA_68vhvbCJsxB2gH93jiqMqA")
TELEGRAM_CHAT_ID = st.secrets.get("TELEGRAM_CHAT_ID", "1073449470")
WHLE_THRESHOLD_USD = 10000

# CACHING
@st.cache_data(ttl=300)
def get_sol_price():
    try:
        response = requests.get(COINGECKO_SOL_PRICE, timeout=10)
        response.raise_for_status()
        return response.json()['solana']['usd']
    except Exception as e:
        st.warning(f"Failed to fetch SOL price: {e}")
        return 0

@st.cache_data(ttl=60)
def get_new_tokens():
    try:
        response = requests.get(DEXSCREENER_API, timeout=10)
        response.raise_for_status()
        data = response.json()
        tokens = []
        for pair in data['pairs']:
            if pair.get('priceUsd') and pair.get('liquidity', {}).get('usd'):
                tokens.append({
                    'chain': pair['chainId'],
                    'symbol': pair['baseToken']['symbol'],
                    'address': pair['baseToken']['address'],
                    'price_usd': float(pair['priceUsd']),
                    'volume_usd': float(pair['volume']['h24']),
                    'liquidity_usd': float(pair['liquidity']['usd']),
                    'holders': pair.get('holders', 0),
                    'pair_created_at': pair['pairCreatedAt']
                })
        return tokens
    except Exception as e:
        st.error(f"Failed to fetch token data: {e}")
        return []

def filter_tokens(tokens):
    return [
        t for t in tokens
        if t['volume_usd'] > 20000 and t['liquidity_usd'] >= 20000 and t['holders'] >= 200
    ]

def score_token(token):
    social_sentiment = 50  # Placeholder
    volume_score = token['volume_usd'] / 1000
    holder_score = token['holders'] / 10
    return (volume_score * 0.4) + (holder_score * 0.3) + (social_sentiment * 0.3)

def get_sol_whale_transactions(token_address, sol_price):
    try:
        response = requests.get(f"{SOLSCAN_API}{token_address}", timeout=10)
        response.raise_for_status()
        data = response.json()
        whales = []
        for tx in data:
            amount = float(tx.get('tokenAmount', {}).get('uiAmount', 0))
            value_usd = amount * sol_price
            if value_usd >= WHLE_THRESHOLD_USD:
                whales.append({'from': tx.get('owner'), 'to': token_address, 'value_usd': value_usd})
        return whales
    except Exception as e:
        st.warning(f"Failed to fetch SOL whale data: {e}")
        return []

def get_evm_whale_transactions(chain, pair_address):
    return [{'from': '0xABC...', 'to': pair_address, 'value_usd': 15000}]

def send_telegram_alert(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message}
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        st.warning(f"Failed to send Telegram alert: {e}")

def run_backtest(historical_data):
    results = []
    for token in historical_data:
        if token['volume_usd'] > 20000 and token['liquidity_usd'] >= 20000 and token['holders'] >= 200:
            score = score_token(token)
            results.append({
                'symbol': token['symbol'],
                'score': score,
                'price_after_24h': token.get('price_after_24h', token['price_usd'] * 1.1),
                'would_alert': score > 75
            })
    df = pd.DataFrame(results)
    hit_rate = df[df['would_alert'] & (df['price_after_24h'] > df['price_usd'] * 1.3)].shape[0] / max(df.shape[0], 1)
    return df, hit_rate

# STREAMLIT DASHBOARD
st.set_page_config(page_title="Multi-chain Meme Coin Tracker", layout="wide")
st.title("🚀 Multi-chain Meme Coin Alpha Tracker")

sol_price = get_sol_price()
tokens = get_new_tokens()
filtered = filter_tokens(tokens)
for t in filtered:
    t['score'] = score_token(t)
    if t['chain'] == 'sol':
        t['whales'] = get_sol_whale_transactions(t['address'], sol_price)
    else:
        t['whales'] = get_evm_whale_transactions(t['chain'], t['address'])

df = pd.DataFrame(filtered)
selected_chain = st.selectbox("Select Chain", options=['all'] + list(df['chain'].unique()))
if selected_chain != 'all':
    df = df[df['chain'] == selected_chain]

st.dataframe(df[['chain', 'symbol', 'address', 'score', 'volume_usd', 'liquidity_usd', 'holders']])

for token in filtered:
    if token['whales']:
        st.markdown(f"### 🐋 Whale Alerts for {token['symbol']} ({token['chain']})")
        for whale in token['whales']:
            st.write(f"From: {whale['from']} | To: {whale['to']} | Value: ${whale['value_usd']:.2f}")

# Backtesting
st.markdown("### 📊 Backtesting Results")
historical_data = [
    {'symbol': 'TEST1', 'volume_usd': 25000, 'liquidity_usd': 30000, 'holders': 300, 'price_usd': 1.0, 'price_after_24h': 1.5},
    {'symbol': 'TEST2', 'volume_usd': 15000, 'liquidity_usd': 25000, 'holders': 250, 'price_usd': 0.5, 'price_after_24h': 0.6},
    {'symbol': 'TEST3', 'volume_usd': 40000, 'liquidity_usd': 50000, 'holders': 500, 'price_usd': 2.0, 'price_after_24h': 3.0}
]
bt_df, hit_rate = run_backtest(historical_data)
st.dataframe(bt_df)
st.write(f"Backtest Hit Rate (>30% gain): {hit_rate * 100:.2f}%")
