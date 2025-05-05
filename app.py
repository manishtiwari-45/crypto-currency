from flask import Flask, render_template, request, jsonify
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import feedparser
import pandas as pd
import numpy as np
import logging

app = Flask(__name__)
API_URL = "https://api.coingecko.com/api/v3/"
API_KEY = "CG-4XuW8PMezjUirbVrSiZ7RK5Z"

HEADERS = {
    'x-cg-demo-api-key': API_KEY,
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

CSV_DATA_FILE = 'top10_crypto_1hr_1year11.csv'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    csv_data = pd.read_csv(CSV_DATA_FILE)
    csv_data['timestamp'] = pd.to_datetime(csv_data['timestamp'])
except FileNotFoundError:
    csv_data = pd.DataFrame()
    logger.warning(f"CSV file {CSV_DATA_FILE} not found. Falling back to API.")

COIN_ID_MAPPING = {
    "bitcoin": "bitcoin",
    "ethereum": "ethereum",
    "toncoin": "the-open-network",
    "ton": "the-open-network",
    "avalanche": "avalanche-2",
    "binancecoin": "binancecoin",
    "cardano": "cardano",
    "solana": "solana",
    "ripple": "ripple",
    "dogecoin": "dogecoin",
    "tether": "tether"
}

def get_coin_id_from_symbol(symbol):
    try:
        resp = requests.get(f"{API_URL}coins/list", headers=HEADERS)
        resp.raise_for_status()
        coins = resp.json()
        for coin in coins:
            if coin['symbol'].upper() == symbol.upper():
                return coin['id']
        logger.warning(f"No CoinGecko ID found for symbol {symbol}")
        return None
    except Exception as e:
        logger.error(f"Error fetching coin ID for symbol {symbol}: {e}")
        return None

def get_scraped_data():
    try:
        resp = requests.get(f"{API_URL}coins/markets", params={'vs_currency': 'usd', 'order': 'market_cap_desc', 'per_page': 10, 'page': 1, 'sparkline': 'true'}, headers=HEADERS)
        resp.raise_for_status()
        coins = resp.json()
        df = pd.DataFrame([{
            'Name': coin['name'],
            'Symbol': coin['symbol'].upper(),
            'Price': f"${coin['current_price']:.2f}",
            'Market Cap': f"${coin['market_cap']:,}",
            '24h %': f"{coin['price_change_percentage_24h']:.2f}%",
            'Sparkline': coin['sparkline_in_7d']['price'],
            'Image': coin['image'],
            'Id': coin['id']
        } for coin in coins])
        return df
    except Exception as e:
        logger.error(f"Error fetching top 10 coins: {e}")
        return None

def get_coin_data(coin_name):
    try:
        resp = requests.get(f"{API_URL}coins/{coin_name.lower()}", headers=HEADERS)
        resp.raise_for_status()
        j = resp.json()
        return {
            'id': j['id'],
            'name': j['name'],
            'symbol': j['symbol'].upper(),
            'price': j['market_data']['current_price']['usd'],
            'market_cap': j['market_data']['market_cap']['usd'],
            'change_24h': j['market_data']['price_change_percentage_24h'],
            'high_24h': j['market_data']['high_24h']['usd'],
            'low_24h': j['market_data']['low_24h']['usd'],
            'tags': j.get('categories', [])[:5],
            'website': j.get('links', {}).get('homepage', [''])[0],
            'description': (j.get('description', {}).get('en') or "")[:300] + "..."
        }
    except Exception as e:
        logger.error(f"Error fetching coin data for {coin_name}: {e}")
        return None

def get_historical_data(coin_id, days=365):
    try:
        resp = requests.get(f"{API_URL}coins/{coin_id.lower()}/market_chart",
                          params={'vs_currency': 'usd', 'days': days, 'interval': 'daily'},
                          headers=HEADERS)
        resp.raise_for_status()
        hist = resp.json()['prices']
        labels = [datetime.fromtimestamp(ts/1000).strftime('%b %d') for ts, _ in hist]
        values = [price for _, price in hist]
        logger.info(f"Fetched API data for {coin_id}, {days} days: {len(labels)} points")
        return labels, values
    except Exception as e:
        logger.error(f"Error fetching historical data for {coin_id}, {days} days: {e}")
        return [], []

def get_historical_data_from_csv(symbol, days=365):
    if not csv_data.empty:
        symbol_data = csv_data[csv_data['symbol'] == symbol.upper()]
        if not symbol_data.empty:
            end_date = symbol_data['timestamp'].max()
            start_date = end_date - timedelta(days=days)
            filtered_data = symbol_data[(symbol_data['timestamp'] >= start_date) & (symbol_data['timestamp'] <= end_date)]
            labels = filtered_data['timestamp'].dt.strftime('%b %d').tolist()
            values = filtered_data['price'].tolist()
            if labels and values:
                logger.info(f"Fetched CSV data for {symbol}, {days} days: {len(labels)} points")
                return labels, values
            else:
                logger.warning(f"No sufficient CSV data for {symbol}, {days} days")
        else:
            logger.warning(f"Symbol {symbol} not found in CSV")
    else:
        logger.warning("CSV data is empty")
    return [], []

def calculate_ier(values, initial_investment=1000):
    try:
        if not values or len(values) < 2:
            return 0, 0, 0, "Insufficient data for IER calculation"

        # Calculate portfolio value over time based on initial investment
        initial_price = values[0]
        shares = initial_investment / initial_price
        portfolio_values = [price * shares for price in values]
        final_portfolio_value = portfolio_values[-1]

        # Calculate max drawdown
        peak = portfolio_values[0]
        trough = portfolio_values[0]
        max_drawdown = 0
        for value in portfolio_values:
            if value > peak:
                peak = value
            if value < trough:
                trough = value
            drawdown = peak - trough
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        # Avoid division by zero
        if max_drawdown == 0:
            return final_portfolio_value, max_drawdown, float('inf'), "No drawdown detected"

        ier = final_portfolio_value / max_drawdown
        return final_portfolio_value, max_drawdown, ier, None
    except Exception as e:
        logger.error(f"Error calculating IER: {e}")
        return 0, 0, 0, "Error calculating IER"

def get_correlation_data(coin_id, days=365):
    try:
        top_10_df = get_scraped_data()
        if top_10_df is None:
            return [], [], "Failed to fetch top 10 coins"
        top_10_ids = top_10_df['Id'].tolist()
        symbols = top_10_df['Symbol'].tolist()
        
        if coin_id not in top_10_ids:
            coin_data = get_coin_data(coin_id)
            if coin_data:
                top_10_ids.append(coin_id)
                symbols.append(coin_data['symbol'].upper())
        
        price_df = pd.DataFrame()
        
        for cid, symbol in zip(top_10_ids, symbols):
            if not csv_data.empty and symbol in csv_data['symbol'].values:
                symbol_data = csv_data[csv_data['symbol'] == symbol]
                end_date = symbol_data['timestamp'].max()
                start_date = end_date - timedelta(days=days)
                filtered_data = symbol_data[(symbol_data['timestamp'] >= start_date) & (symbol_data['timestamp'] <= end_date)]
                if not filtered_data.empty:
                    daily_data = filtered_data.set_index('timestamp').resample('D').last()['price'].ffill()
                    if not daily_data.empty:
                        price_df[symbol] = daily_data
                        logger.info(f"Loaded CSV daily data for {symbol}, {len(daily_data)} points")
                        continue
            try:
                resp = requests.get(f"{API_URL}coins/{cid.lower()}/market_chart",
                                  params={'vs_currency': 'usd', 'days': days, 'interval': 'daily'},
                                  headers=HEADERS)
                resp.raise_for_status()
                hist = resp.json()['prices']
                if hist:
                    dates = [datetime.fromtimestamp(ts/1000).date() for ts, _ in hist]
                    prices = [price for _, price in hist]
                    temp_df = pd.DataFrame({'price': prices}, index=pd.to_datetime(dates))
                    daily_data = temp_df.resample('D').last()['price'].ffill()
                    price_df[symbol] = daily_data
                    logger.info(f"Fetched API daily data for {cid}, {len(daily_data)} points")
            except Exception as e:
                logger.warning(f"Failed to fetch data for {cid}: {e}")
        
        if price_df.empty or len(price_df.columns) < 2:
            return [], [], "Insufficient data for correlation analysis"
        
        price_df = price_df.dropna(how='all')
        price_df = price_df.ffill()
        
        returns_df = price_df.pct_change().dropna()
        logger.info(f"Returns DataFrame shape: {returns_df.shape}")
        
        if len(returns_df) < 10:
            return [], [], f"Not enough overlapping data points ({len(returns_df)}) to compute correlation"
        
        corr_matrix = returns_df.corr().round(2)
        labels = list(corr_matrix.columns)
        matrix_data = []
        for i, row in enumerate(corr_matrix.values):
            for j, value in enumerate(row):
                matrix_data.append({
                    'x': labels[j],
                    'y': labels[i],
                    'v': float(value)
                })
        
        logger.info(f"Matrix data size: {len(matrix_data)}, Labels: {labels}")
        return matrix_data, labels, None
    except Exception as e:
        logger.error(f"Error calculating correlation for {coin_id}: {e}")
        return [], [], "Error calculating correlation"

def scrape_crypto_news():
    try:
        url = "https://www.coindesk.com/"
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        news_items = []
        selectors = [
            'article.card h6.heading',
            'article h5',
            'article h6',
            '.article-card h6'
        ]
        for selector in selectors:
            articles = soup.select(selector)[:6]
            if articles:
                for article in articles:
                    title = article.text.strip()
                    link = article.find_parent('a')['href'] if article.find_parent('a') else '#'
                    if not link.startswith('http'):
                        link = f"https://www.coindesk.com{link}"
                    news_items.append({'title': title, 'link': link})
                break
        if not news_items:
            feed = feedparser.parse("https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml")
            news_items = [{'title': e.title, 'link': e.link} for e in feed.entries[:6]]
        return news_items[:6]
    except Exception as e:
        logger.error(f"Web scraping error: {e}")
        try:
            feed = feedparser.parse("https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml")
            return [{'title': e.title, 'link': e.link} for e in feed.entries[:6]]
        except:
            return []

@app.route("/", methods=["GET", "POST"])
def index():
    coin = None
    error = None
    labels = []
    values = []
    coin_id = None
    final_portfolio_value = None
    max_drawdown = None
    ier = None
    ier_error = None

    if request.method == "POST":
        coin_name = request.form["coin"].strip().lower()
        coin_id = COIN_ID_MAPPING.get(coin_name, coin_name)
        if coin_name:
            if not csv_data.empty and coin_name.upper() in csv_data['symbol'].values:
                symbol = coin_name.upper()
                labels, values = get_historical_data_from_csv(symbol, 365)
                coin_id = get_coin_id_from_symbol(symbol) or symbol
                if labels and values:
                    coin = {
                        'id': coin_id,
                        'name': csv_data[csv_data['symbol'] == symbol]['name'].iloc[0],
                        'symbol': symbol,
                        'price': csv_data[csv_data['symbol'] == symbol]['price'].iloc[-1],
                        'market_cap': csv_data[csv_data['symbol'] == symbol]['market_cap'].iloc[-1],
                        'change_24h': csv_data[csv_data['symbol'] == symbol]['percent_change_24h'].iloc[-1],
                        'high_24h': csv_data[csv_data['symbol'] == symbol]['price'].max(),
                        'low_24h': csv_data[csv_data['symbol'] == symbol]['price'].min(),
                        'tags': [],
                        'website': '',
                        'description': ''
                    }
                    final_portfolio_value, max_drawdown, ier, ier_error = calculate_ier(values)
                else:
                    error = "No historical data found in CSV for this coin."
            else:
                coin = get_coin_data(coin_id)
                if coin:
                    labels, values = get_historical_data(coin['id'], 365)
                    coin_id = coin['id']
                    final_portfolio_value, max_drawdown, ier, ier_error = calculate_ier(values)
                else:
                    error = f"Could not fetch data for '{coin_name}'. Please check the name and try again."
        else:
            error = "Please enter a coin name"

    return render_template(
        "index.html",
        coin=coin,
        labels=labels,
        values=values,
        error=error,
        coin_id=coin_id,
        final_portfolio_value=final_portfolio_value,
        max_drawdown=max_drawdown,
        ier=ier,
        ier_error=ier_error
    )

@app.route("/correlation/<coin_id>")
def correlation(coin_id):
    coin = get_coin_data(coin_id)
    if not coin:
        return render_template("correlation.html", error=f"Could not fetch data for coin ID: {coin_id}", coin_id=coin_id)
    
    matrix_data, labels, error = get_correlation_data(coin_id)
    return render_template(
        "correlation.html",
        coin=coin,
        matrix_data=matrix_data,
        labels=labels,
        error=error
    )

@app.route("/get_top_10", methods=["GET"])
def get_top_10():
    top_10_df = get_scraped_data()
    if top_10_df is not None:
        top_10 = top_10_df.to_dict('records')
        top_10_with_index = list(zip(top_10, range(10)))
        return jsonify([{
            'Name': crypto['Name'],
            'Symbol': crypto['Symbol'],
            'Price': crypto['Price'],
            'Market Cap': crypto['Market Cap'],
            '24h %': crypto['24h %'],
            'Sparkline': crypto['Sparkline'],
            'Image': crypto['Image'],
            'index': idx
        } for crypto, idx in top_10_with_index])
    return jsonify({'error': 'Could not fetch top 10 data'}), 500

@app.route("/get_news", methods=["GET"])
def get_news():
    news = scrape_crypto_news()
    if news:
        return jsonify(news)
    return jsonify({'error': 'Could not fetch news'}), 500

@app.route("/get_historical_data/<coin_id>/<int:days>", methods=["GET"])
def get_historical_data_ajax(coin_id, days):
    try:
        labels, values = [], []
        source = "unknown"
        if coin_id in csv_data['symbol'].values:
            labels, values = get_historical_data_from_csv(coin_id, days)
            source = "CSV"
        if not labels or not values:
            actual_coin_id = get_coin_id_from_symbol(coin_id) if coin_id in csv_data['symbol'].values else coin_id
            if actual_coin_id:
                labels, values = get_historical_data(actual_coin_id, days)
                source = "API"
            else:
                logger.error(f"Invalid coin ID or symbol: {coin_id}")
                return jsonify({'error': f'Invalid coin ID or symbol: {coin_id}'}), 404
        if not labels or not values:
            logger.warning(f"No data available for {coin_id}, {days} days from {source}")
            return jsonify({'error': f'No data available for {coin_id} for {days} days'}), 404
        logger.info(f"Returning data for {coin_id}, {days} days from {source}")
        return jsonify({'labels': labels, 'values': values})
    except Exception as e:
        logger.error(f"Error in get_historical_data_ajax for {coin_id}, {days} days: {e}")
        return jsonify({'error': 'Failed to fetch historical data'}), 500

if __name__ == "__main__":
    app.run(debug=True)