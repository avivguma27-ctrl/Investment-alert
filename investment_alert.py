# investment_alert.py
import os
import requests
from bs4 import BeautifulSoup
import yfinance as yf
import feedparser
from telegram import Bot

# Environment variables (set in GitHub Secrets)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_IDS = os.getenv("TELEGRAM_CHAT_IDS", "")  # comma separated IDs
LANG = os.getenv("APP_LANG", "en")  # "en" or "he"

# parse chat ids
CHAT_IDS = [c.strip() for c in TELEGRAM_CHAT_IDS.split(",") if c.strip()]

bot = None
if TELEGRAM_TOKEN and CHAT_IDS:
    bot = Bot(token=TELEGRAM_TOKEN)

def send_telegram_message(message):
    if not bot:
        print("Telegram not configured:", message)
        return
    for cid in CHAT_IDS:
        try:
            bot.send_message(chat_id=cid, text=message)
        except Exception as e:
            print("Failed to send to", cid, e)

# --- Stock price via yfinance
def get_stock_price(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="2d")
        if len(hist) < 2:
            return None
        today_close = float(hist['Close'][-1])
        yesterday_close = float(hist['Close'][-2])
        change_pct = ((today_close - yesterday_close) / yesterday_close) * 100
        return {"ticker": ticker.upper(), "today_close": today_close, "yesterday_close": yesterday_close, "change_pct": change_pct}
    except Exception as e:
        print("get_stock_price error:", e)
        return None

# --- SEC 13F (recent)
def get_recent_13f_filings(count=10):
    try:
        url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=13F-HR&count={count}"
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; InvestmentAlert/1.0)'}
        r = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        filings = []
        for row in soup.find_all('tr')[1:]:
            cols = row.find_all('td')
            if len(cols) < 5: continue
            date_filed = cols[3].text.strip()
            company_name = cols[1].text.strip()
            link_tag = cols[1].find('a')
            filing_link = "https://www.sec.gov" + link_tag['href'] if link_tag else ""
            filings.append({"date": date_filed, "company": company_name, "link": filing_link})
        return filings
    except Exception as e:
        print("get_recent_13f_filings error:", e)
        return []

# --- Google News RSS
def get_google_news_rss(query, max_items=5):
    try:
        rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(rss_url)
        news_items = []
        for entry in feed.entries[:max_items]:
            news_items.append({"title": entry.title, "link": entry.link, "published": getattr(entry, 'published', '')})
        return news_items
    except Exception as e:
        print("get_google_news_rss error:", e)
        return []

# --- SEC Form 4 (politician trades)
def get_recent_politician_trades(count=10):
    try:
        url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=form4&count={count}"
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; InvestmentAlert/1.0)'}
        r = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        trades = []
        for row in soup.find_all('tr')[1:]:
            cols = row.find_all('td')
            if len(cols) < 5: continue
            date_filed = cols[3].text.strip()
            filer = cols[1].text.strip()
            link_tag = cols[1].find('a')
            filing_link = "https://www.sec.gov" + link_tag['href'] if link_tag else ""
            trades.append({"date": date_filed, "filer": filer, "link": filing_link})
        return trades
    except Exception as e:
        print("get_recent_politician_trades error:", e)
        return []

# --- scoring
def score_opportunity(stock_data, filings_count, news_count, politician_trades_count):
    score = 0
    if stock_data and abs(stock_data.get("change_pct", 0)) > 5:
        score += 3
    if filings_count > 0:
        score += filings_count * 2
    if news_count > 0:
        score += news_count
    if politician_trades_count > 0:
        score += politician_trades_count * 2
    return score

# --- read tickers from tickers.txt (one per line)
def load_tickers(path="tickers.txt", limit=None):
    try:
        with open(path, "r") as f:
            lines = [l.strip().upper() for l in f.readlines() if l.strip()]
        return lines[:limit] if limit else lines
    except Exception as e:
        print("load_tickers error:", e)
        return ["MSFT","AAPL","NVDA"]

# --- run and optionally notify
def run_and_notify(ticker="MSFT"):
    stock_data = get_stock_price(ticker)
    filings = get_recent_13f_filings()
    news = get_google_news_rss(ticker)
    politician_trades = get_recent_politician_trades()

    score = score_opportunity(stock_data, len(filings), len(news), len(politician_trades))

    if LANG == "he":
        message = f"🔔 הזדמנות: {ticker}\n"
        if stock_data:
            message += f"מחיר: {stock_data['today_close']} | שינוי: {stock_data['change_pct']:.2f}%\n"
        else:
            message += "אין מידע מחיר\n"
        message += f"13F: {len(filings)} | חדשות: {len(news)} | רכישות פוליטיקאים: {len(politician_trades)}\n"
        message += f"ניקוד: {score}"
    else:
        message = f"🔔 Opportunity: {ticker}\n"
        if stock_data:
            message += f"Price: {stock_data['today_close']} | Change: {stock_data['change_pct']:.2f}%\n"
        else:
            message += "No price data\n"
        message += f"13F: {len(filings)} | News: {len(news)} | Politician trades: {len(politician_trades)}\n"
        message += f"Score: {score}"

    send_telegram_message(message)
    return {"ticker": ticker, "score": score}
