import requests
import random
import time
from bs4 import BeautifulSoup
import pandas as pd
from fake_useragent import UserAgent
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import undetected_chromedriver as uc

def get_random_delay():
    """Return a random delay between 2-5 seconds"""
    return random.uniform(2, 5)

def setup_undetected_driver():
    """Setup undetected Chrome driver with various anti-detection measures"""
    options = uc.ChromeOptions()

    # Common settings to mimic human behavior
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-web-security")
    options.add_argument("--disable-xss-auditor")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--disable-logging")
    options.add_argument("--log-level=3")
    options.add_argument("--output=/dev/null")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--start-maximized")

    # Randomize user agent
    ua = UserAgent()
    user_agent = ua.random
    options.add_argument(f'user-agent={user_agent}')

    # Enable stealth mode
    options.add_argument("--disable-blink-features")
    options.add_argument("--disable-blink-features=AutomationControlled")

    # Set up proxy if needed (rotating proxies would be better)
    # proxy = get_random_proxy()
    # options.add_argument(f'--proxy-server={proxy}')

    # Initialize undetected chromedriver
    driver = uc.Chrome(options=options)

    # Execute stealth JS
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    driver.execute_script("window.navigator.chrome = {runtime: {}, etc: {}};")
    driver.execute_script("const originalQuery = window.navigator.permissions.query; window.navigator.permissions.query = (parameters) => (parameters.name === 'notifications' ? Promise.resolve({ state: Notification.permission }) : originalQuery(parameters));")

    return driver

def scrape_coinmarketcap():
    """Scrape cryptocurrency data from CoinMarketCap"""
    url = "https://coinmarketcap.com/"

    try:
        # Setup undetected browser
        driver = setup_undetected_driver()
        driver.get(url)

        # Random delay before interacting
        time.sleep(get_random_delay())

        # Wait for the page to load completely
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".cmc-table")))

        # Scroll to load all data (simulate human scrolling)
        last_height = driver.execute_script("return document.body.scrollHeight")
        for _ in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
            time.sleep(get_random_delay())
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/1.5);")
            time.sleep(get_random_delay())
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(get_random_delay())
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

        # Parse the page with BeautifulSoup
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # Find the table containing cryptocurrency data
        table = soup.find('table', {'class': 'cmc-table'})
        if not table:
            raise ValueError("Could not find cryptocurrency table on page")

        # Extract table headers
        headers = []
        for th in table.find('thead').find_all('th'):
            headers.append(th.get_text(strip=True))

        # Extract table rows
        rows = []
        for tr in table.find('tbody').find_all('tr'):
            row = []
            for td in tr.find_all('td'):
                row.append(td.get_text(strip=True))
            rows.append(row)

        # Create DataFrame
        df = pd.DataFrame(rows, columns=headers)

        # Clean up data
        df = df.dropna(how='all')
        df = df[df['#'] != '']

        # Close the browser
        driver.quit()
        
        return df

    except Exception as e:
        print(f"Error occurred: {str(e)}")
        if 'driver' in locals():
            driver.quit()
        return None

def save_data(df, filename='crypto_data.csv'):
    """Save scraped data to CSV"""
    if df is not None:
        df.to_csv(filename, index=False)
        print(f"Data successfully saved to {filename}")
    else:
        print("No data to save")

if __name__ == "__main__":
    print("Starting CoinMarketCap scraping...")
    crypto_data = scrape_coinmarketcap()
    
    if crypto_data is not None:
        print("Scraping completed successfully!")
        print(crypto_data.head())
        save_data(crypto_data)
    else:
        print("Scraping failed. Please check the error message.")