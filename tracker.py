import streamlit as st
import requests
import time
import pandas as pd
import tweepy
import praw

# Configuration (Replace with your API keys)
ETHERSCAN_API_KEY = "YOUR_ETHERSCAN_API_KEY"
BSCSCAN_API_KEY = "YOUR_BSCSCAN_API_KEY"
ARBISCAN_API_KEY = "YOUR_ARBISCAN_API_KEY"
BASESCAN_API_KEY = "YOUR_BASESCAN_API_KEY"
TWITTER_API_KEY = "YOUR_TWITTER_API_KEY"
TWITTER_API_SECRET = "YOUR_TWITTER_API_SECRET"
TWITTER_ACCESS_TOKEN = "YOUR_TWITTER_ACCESS_TOKEN"
TWITTER_ACCESS_SECRET = "YOUR_TWITTER_ACCESS_SECRET"
REDDIT_CLIENT_ID = "YOUR_REDDIT_CLIENT_ID"
REDDIT_CLIENT_SECRET = "YOUR_REDDIT_CLIENT_SECRET"
REDDIT_USER_AGENT = "YOUR_REDDIT_USER_AGENT"
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID"

# Chain and API mappings
CHAINS = ['ethereum', 'binance', 'arbitrum', 'base', 'solana']
EXPLORER_APIS = {
    'ethereum': {'url': 'https://api.etherscan.io/api', 'key': ETHERSCAN_API_KEY},
    'binance': {'url': 'https://api.bscscan.com/api', 'key': BSCSCAN_API_KEY},
    'arbitrum': {'url': 'https://api.arbiscan.io/api', 'key': ARBISCAN_API_KEY},
    'base': {'url': 'https://api.basescan.org/api', 'key': BASESCAN_API_KEY},
    'solana': {'url': 'https://api.solscan.io', 'key': None}
}

# Thresholds
LIQUIDITY_THRESHOLD = 20000
PRICE_CHANGE_THRESHOLD = 30
HOLDER_THRESHOLD = 200
SOCIAL_MENTIONS_THRESHOLD = 10
WHALE_THRESHOLD_USD = 10000
CREATION_TIME_THRESHOLD = 24 * 3600  # 24 hours in seconds

# Twitter API Setup
auth = tweepy.OAuthHandler(TWITTER_API_KEY, TWITTER_API_SECRET)
auth.set_access_token(TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET)
twitter_api = tweepy.API(auth)

# Reddit API Setup
reddit = praw.Reddit(client_id=REDDIT_CLIENT_ID,
                     client_secret=REDDIT_CLIENT_SECRET,
                     user_agent=REDDIT_USER_AGENT)

# Fetch recent pairs from Dexscreener
def get_recent_pairs():
    pairs = []
    for chain in CHAINS:
        url = f"https://api.dexscreener.com/latest/dex/search?q={chain}"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            for pair in data.get('pairs', []):
                if pair.get('priceUsd') and pair.get('liquidity', {}).get('usd'):
                    pairs.append({
                        'chain': pair['chainId'],
                        'pair_address': pair['pairAddress'],
                        'symbol': pair['baseToken']['symbol'],
                        'address': pair['baseToken']['address'],
                        'price_usd': float(pair['priceUsd']),
                        'price_change_24h': float(pair['priceChange']['h24']),
                        'volume_usd_24h': float(pair['volume']['h24']),
                        'liquidity_usd': float(pair['liquidity']['usd']),
                        'pair_created_at': pair['pairCreatedAt'] / 1000
                    })
        except requests.RequestException as e:
            st.error(f"Error fetching data for {chain}: {e}")
    return pairs

# Get holder count
def get_holder_count(chain, address):
    if chain == 'solana':
        url = f"{EXPLORER_APIS[chain]['url']}/token/holders?tokenAddress={address}"
        try:
            response = requests.get(url)
            data = response.json()
            return data['total'] if 'total' in data else 0
        except Exception as e:
            st.error(f"Error fetching holders for {address} on Solana: {e}")
            return 0
    else:
        explorer = EXPLORER_APIS[chain]
        url = f"{explorer['url']}?module=token&action=tokenholderlist&contractaddress={address}&apikey={explorer['key']}"
        try:
            response = requests.get(url)
            data = response.json()
            return len(data['result']) if data['status'] == '1' else 0
        except Exception as e:
            st.error(f"Error fetching holders for {address} on {chain}: {e}")
            return 0

# Check contract renouncement
def is_contract_renounced(chain, address):
    if chain == 'solana':
        url = f"{EXPLORER_APIS[chain]['url']}/token/meta?tokenAddress={address}"
        try:
            response = requests.get(url)
            data = response.json()
            return data['mintAuthority'] is None
        except Exception as e:
            st.error(f"Error checking mint authority for {address}: {e}")
            return False
    else:
        explorer = EXPLORER_APIS[chain]
        url = f"{explorer['url']}?module=contract&action=getsourcecode&address={address}&apikey={explorer['key']}"
        try:
            response = requests.get(url)
            data = response.json()
            return data['result'][0].get('Owner', '') == '0x0000000000000000000000000000000000000000'
        except Exception as e:
            st.error(f"Error checking contract for {address}: {e}")
            return False

# Get social mentions (Twitter + Reddit)
def get_social_mentions(symbol):
    twitter_mentions = 0
    reddit_mentions = 0
    try:
        tweets = twitter_api.search_tweets(q=symbol, lang='en', count=100)
        twitter_mentions = sum(1 for tweet in tweets if (time.time() - time.mktime(tweet.created_at.timetuple())) < 86400)
    except tweepy.TweepyException as e:
        st.error(f"Twitter error for {symbol}: {e}")
    
    try:
        subreddit = reddit.subreddit('cryptocurrency')
        for submission in subreddit.search(symbol, sort='new', time_filter='day'):
            reddit_mentions += 1
    except Exception as e:
        st.error(f"Reddit error for {symbol}: {e}")
    
    return twitter_mentions + reddit_mentions

# Get whale transactions
def get_whale_transactions(chain, address, price_usd):
    if chain == 'solana':
        url = f"{EXPLORER_APIS[chain]['url']}/account/transactions?account={address}&limit=100"
        try:
            response = requests.get(url)
            data = response.json()
            whales = []
            for tx in data:
                if 'tokenAmount' in tx and tx['tokenAmount']['uiAmount'] * price_usd > WHALE_THRESHOLD_USD:
                    whales.append({'from': tx['owner'], 'to': tx['to'], 'value': tx['tokenAmount']['uiAmount']})
            return whales
        except Exception as e:
            st.error(f"Error fetching Solana transactions: {e}")
            return []
    else:
        explorer = EXPLORER_APIS[chain]
        url = f"{explorer['url']}?module=account&action=tokentx&contractaddress={address}&page=1&offset=100&apikey={explorer['key']}"
        try:
            response = requests.get(url)
            data = response.json()
            whales = []
            for tx in data['result']:
                value = float(tx['value']) / 10**int(tx['tokenDecimal'])
                if value * price_usd > WHALE_THRESHOLD_USD:
                    whales.append({'from': tx['from'], 'to': tx['to'], 'value': value})
            return whales
        except Exception as e:
            st.error(f"Error fetching transactions for {chain}: {e}")
            return []

# Filter pairs
def filter_pairs(pairs, current_time):
    filtered = []
    for pair in pairs:
        holder_count = get_holder_count(pair['chain'], pair['address'])
        is_renounced = is_contract_renounced(pair['chain'], pair['address'])
        social_mentions = get_social_mentions(pair['symbol'])
        if (pair['liquidity_usd'] >= LIQUIDITY_THRESHOLD and
            pair['price_change_24h'] > PRICE_CHANGE_THRESHOLD and
            holder_count >= HOLDER_THRESHOLD and
            is_renounced and
            social_mentions >= SOCIAL_MENTIONS_THRESHOLD and
            pair['pair_created_at'] > current_time - CREATION_TIME_THRESHOLD):
            filtered.append(pair)
    return filtered

# Score pairs
def score_pair(pair, holder_count, social_mentions):
    vol_score = pair['volume_usd_24h'] / 1e5
    liq_score = pair['liquidity_usd'] / 1e5
    holder_score = holder_count / 1000
    social_score = social_mentions / 10
    return (vol_score * 0.3) + (liq_score * 0.2) + (holder_score * 0.3) + (social_score * 0.2)

# Send Telegram alert
def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        st.error(f"Telegram error: {e}")

# Streamlit App
st.set_page_config(page_title="Meme Coin Tracker", layout="wide")
st.title("🚀 Meme Coin Alpha Tracker (Multi-Chain)")

if 'last_run' not in st.session_state:
    st.session_state['last_run'] = 0
if 'alerted_pairs' not in st.session_state:
    st.session_state['alerted_pairs'] = set()
if 'data' not in st.session_state:
    st.session_state['data'] = []

# Fetch data every 5 minutes
current_time = time.time()
if current_time - st.session_state['last_run'] > 300:
    pairs = get_recent_pairs()
    filtered_pairs = filter_pairs(pairs, current_time)
    for pair in filtered_pairs:
        holder_count = get_holder_count(pair['chain'], pair['address'])
        social_mentions = get_social_mentions(pair['symbol'])
        pair['score'] = score_pair(pair, holder_count, social_mentions)
        pair['whales'] = get_whale_transactions(pair['chain'], pair['address'], pair['price_usd'])
        if pair['pair_address'] not in st.session_state['alerted_pairs']:
            message = (f"New coin: {pair['symbol']} on {pair['chain']}\n"
                       f"Liquidity: ${pair['liquidity_usd']:,.2f}\n"
                       f"24h Change: {pair['price_change_24h']}%\n"
                       f"Holders: {holder_count}\n"
                       f"Social: {social_mentions}\n"
                       f"Score: {pair['score']:.2f}")
            send_telegram_alert(message)
            for whale in pair['whales']:
                whale_message = (f"Whale Alert: {pair['symbol']} on {pair['chain']}: "
                                 f"{whale['value']} tokens from {whale['from']} to {whale['to']}")
                send_telegram_alert(whale_message)
            st.session_state['alerted_pairs'].add(pair['pair_address'])
    st.session_state['data'] = filtered_pairs
    st.session_state['last_run'] = current_time

# Display data
if st.session_state['data']:
    df = pd.DataFrame(st.session_state['data'])
    st.dataframe(df[['chain', 'symbol', 'price_usd', 'price_change_24h', 
                     'volume_usd_24h', 'liquidity_usd', 'score']],
                 column_config={
                     'price_usd': st.column_config.NumberColumn(format="$%.6f"),
                     'volume_usd_24h': st.column_config.NumberColumn(format="$%.2f"),
                     'liquidity_usd': st.column_config.NumberColumn(format="$%.2f"),
                     'price_change_24h': st.column_config.NumberColumn(format="%.2f%%")
                 })
    for token in st.session_state['data']:
        if token['whales']:
            st.markdown(f"### 🐋 Whale Alerts for {token['symbol']} ({token['chain']})")
            for whale in token['whales']:
                st.write(f"From: {whale['from']} | To: {whale['to']} | Value: {whale['value']:.2f} tokens")
else:
    st.write("No tokens meet the criteria yet.")
