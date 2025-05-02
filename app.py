from flask import Flask, render_template, request, jsonify
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import feedparser
from scraper import scrape_coinmarketcap

app = Flask(__name__)
API_URL = "https://api.coingecko.com/api/v3/"
API_KEY = "CG-4XuW8PMezjUirbVrSiZ7RK5Z"

HEADERS = {
    'x-cg-demo-api-key': API_KEY,
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

cached_data = None
last_scraped_time = None
CACHE_DURATION = timedelta(minutes=5)

def get_scraped_data():
    global cached_data, last_scraped_time
    now = datetime.now()
    if cached_data is None or last_scraped_time is None or now - last_scraped_time > CACHE_DURATION:
        df = scrape_coinmarketcap()
        if df is not None:
            cached_data = df
            last_scraped_time = now
    return cached_data

def get_coin_data(coin_name):
    try:
        resp = requests.get(f"{API_URL}coins/{coin_name.lower()}", headers=HEADERS)
        resp.raise_for_status()
        j = resp.json()
        return {
            'id': j['id'],  # Add id for accurate API calls
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
        print(f"Error fetching coin data: {e}")
        return None

def get_historical_data(coin_id, days=365):
    try:
        resp = requests.get(f"{API_URL}coins/{coin_id.lower()}/market_chart",
                          params={'vs_currency': 'usd', 'days': days},
                          headers=HEADERS)
        resp.raise_for_status()
        hist = resp.json()['prices']
        labels = [datetime.fromtimestamp(ts/1000).strftime('%b %d') for ts, _ in hist]
        values = [price for _, price in hist]
        return labels, values
    except Exception as e:
        print(f"Error fetching historical data: {e}")
        return [], []

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
            articles = soup.select(selector)[:5]
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

        return news_items

    except Exception as e:
        print(f"Web scraping error: {e}")
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
    news = scrape_crypto_news()
    coin_id = None

    if request.method == "POST":
        coin_name = request.form["coin"].strip().lower()
        if coin_name:
            coin = get_coin_data(coin_name)
            if coin:
                labels, values = get_historical_data(coin['id'], 365)
                coin_id = coin['id']
            else:
                error = "Coin not found or error fetching data."
        else:
            error = "Please enter a coin name"

    scraped_df = get_scraped_data()
    if scraped_df is not None:
        top_10 = scraped_df.head(10).to_dict('records')
        top_10_with_index = list(zip(top_10, range(10)))
    else:
        top_10_with_index = []

    return render_template(
        "index.html",
        coin=coin,
        labels=labels,
        values=values,
        news=news,
        error=error,
        top_10_with_index=top_10_with_index,
        coin_id=coin_id
    )

@app.route("/get_historical_data/<coin_id>/<int:days>", methods=["GET"])
def get_historical_data_ajax(coin_id, days):
    labels, values = get_historical_data(coin_id, days)
    return jsonify({'labels': labels, 'values': values})

if __name__ == "__main__":
    app.run(debug=True)