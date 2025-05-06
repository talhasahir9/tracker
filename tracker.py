import requests
import time
import pandas as pd
import streamlit as st

# CONFIG
DEXSCREENER_API = "https://api.dexscreener.com/token-profiles/latest/v1"
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID"
WHLE_THRESHOLD_USD = 10000

# HELPER FUNCTIONS

def infer_chain_from_links(links):
    if not links:
        return 'unknown'
    for link in links:
        if 'solscan' in link:
            return 'sol'
        elif 'etherscan' in link:
            return 'eth'
        elif 'bscscan' in link:
            return 'bsc'
        elif 'arbiscan' in link:
            return 'arbi'
        elif 'basescan' in link:
            return 'base'
    return 'unknown'

# MAIN FUNCTIONS

def get_new_tokens():
    try:
        response = requests.get(DEXSCREENER_API)
        response.raise_for_status()
        data = response.json()
        tokens = []
        for token in data:
            chain = token.get('chainId') or infer_chain_from_links(token.get('links', []))
            tokens.append({
                'chain': chain,
                'symbol': token.get('symbol', 'N/A'),
                'address': token.get('tokenAddress'),
                'description': token.get('description', ''),
                'icon': token.get('icon', ''),
                'links': token.get('links', []),
                'volume_usd': 30000,  # placeholder
                'liquidity_usd': 50000,  # placeholder
                'holders': 500,  # placeholder
                'price_usd': 1.0  # placeholder
            })
        return tokens
    except requests.exceptions.RequestException as e:
        print(f"Error fetching token data: {e}")
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

def get_sol_whale_transactions(token_address):
    return []  # placeholder, no live Solscan integration

def get_evm_whale_transactions(chain, pair_address):
    return [{'from': '0xABC...', 'to': pair_address, 'value_usd': 15000}]

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message}
    try:
        requests.post(url, data=payload)
    except requests.exceptions.RequestException as e:
        print(f"Failed to send Telegram alert: {e}")

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

if 'last_run' not in st.session_state or time.time() - st.session_state['last_run'] > 60:
    tokens = get_new_tokens()
    filtered = filter_tokens(tokens)
    for t in filtered:
        t['score'] = score_token(t)
        if t['chain'] == 'sol':
            t['whales'] = get_sol_whale_transactions(t['address'])
        else:
            t['whales'] = get_evm_whale_transactions(t['chain'], t['address'])
    st.session_state['data'] = filtered
    st.session_state['last_run'] = time.time()

if st.session_state.get('data'):
    df = pd.DataFrame(st.session_state['data'])
    if 'chain' in df.columns:
        chain_options = ['all'] + sorted(df['chain'].unique().tolist())
        selected_chain = st.selectbox("Select Chain", options=chain_options)
        if selected_chain != 'all':
            df = df[df['chain'] == selected_chain]
        st.dataframe(df[['chain', 'symbol', 'address', 'description', 'score', 'volume_usd', 'liquidity_usd', 'holders']])
    else:
        st.warning("No 'chain' column found in data.")
else:
    st.error("Failed to load token data. Please check the API or try again later.")

if st.session_state.get('data'):
    for token in st.session_state['data']:
        if token.get('whales'):
            st.markdown(f"### 🐋 Whale Alerts for {token['symbol']} ({token['chain']})")
            for whale in token['whales']:
                st.write(f"From: {whale['from']} | To: {whale['to']} | Value: ${whale['value_usd']:.2f}")

# Backtesting
st.markdown("### 📊 Backtesting Results")
historical_data = [
    {'symbol': 'TEST1', 'volume_usd': 25000, 'liquidity_usd': 30000, 'holders': 300, 'price_usd': 1.0, 'price_after_24h':1.5},
    {'symbol': 'TEST2', 'volume_usd': 15000, 'liquidity_usd': 25000, 'holders': 250, 'price_usd': 0.5, 'price_after_24h':0.6},
    {'symbol': 'TEST3', 'volume_usd': 40000, 'liquidity_usd': 50000, 'holders': 500, 'price_usd': 2.0, 'price_after_24h':3.0}
]
bt_df, hit_rate = run_backtest(historical_data)
st.dataframe(bt_df)
st.write(f"Backtest Hit Rate (>30% gain): {hit_rate*100:.2f}%")
