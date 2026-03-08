import os, requests, time, re
from bs4 import BeautifulSoup

# === 🎛️ USER CONFIGURATION (Edit these easily!) ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CF_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")

# ✅ ADD OR REMOVE WEBSITES HERE (Easy List!)
TARGET_URLS = [
    "https://www.bpc.vic.gov.au/news",
    "https://engage.vic.gov.au/"
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=newsalerts"
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=mediareleases"
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=courtactions"
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=enforceableundertakings"
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=legislationupdates"
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=publicwarnings"
    # "https://www.vba.vic.gov.au/news-and-publications/news",  # Example: Uncomment to add
    # "https://www.planning.vic.gov.au/news",                   # Example: Add another
]

# ✅ Default Settings
MAX_ITEMS_PER_SITE = 20  # How many news items to grab per website
POLLING_ENABLED = True   # Set False if you only want scheduled runs

# === 🤖 AI PROMPT ===
AI_PROMPT = """Summarize these Victorian building/planning news items. 
Focus on reforms, regulations, legal, compliance, safety. 
Use bullet points with emojis. Group by website source. 
Keep under 400 words. If no relevant news, say 'No major reforms found.'
\n\n{text}"""

# === 🛠️ SYSTEM FUNCTIONS (No need to edit below) ===
HEADERS = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)'}

def send_telegram(message, reply_to_message_id=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML", "disable_web_page_preview": True}
    if reply_to_message_id: data["reply_to_message_id"] = reply_to_message_id
    try:
        resp = requests.post(url, json=data, timeout=30)
        return resp.json()
    except Exception as e:
        print(f"✗ Telegram error: {e}")
        return None

def get_telegram_updates(offset=0):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"offset": offset, "timeout": 5, "allowed_updates": ["message"]}
    try:
        resp = requests.get(url, params=params, timeout=10)
        return resp.json() if resp.status_code == 200 else {"result": []}
    except: return {"result": []}

def scrape_site(url, max_items=MAX_ITEMS_PER_SITE):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, 'html.parser')
        items = []
        # Generic scraper: tries headlines first, then paragraphs
        for tag in soup.find_all(['h2','h3','h4','a'], class_=lambda c: c and any(x in c.lower() for x in ['title','news','heading'])):
            text = tag.get_text().strip()
            if 30 < len(text) < 300: items.append(text)
        if len(items) < max_items:
            for p in soup.find_all('p'):
                text = p.get_text().strip()
                if 50 < len(text) < 300 and text not in items: items.append(text)
        return f"📰 Source: {url}\n" + "\n• ".join(items[:max_items]) if items else f"📰 Source: {url}\nNo items found."
    except Exception as e: return f"📰 Source: {url}\nError: {e}"

def call_ai(text):
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/meta/llama-3-8b-instruct"
    headers = {"Authorization": f"Bearer {CF_TOKEN}", "Content-Type": "application/json"}
    try:
        resp = requests.post(url, headers=headers, json={"messages": [{"role": "user", "content": AI_PROMPT.format(text=text[:4000])}], "max_tokens": 800}, timeout=90)
        return resp.json()['result']['response'].strip()
    except: return None

def handle_command(cmd, args, msg_id):
    if cmd == '/help':
        return "<b>Commands:</b>\n/today - Scan all configured sites\n/check [url] - Scan specific URL\n/settings - Show config"
    elif cmd == '/settings':
        return f"<b>Config:</b>\nSites: {len(TARGET_URLS)}\nItems/site: {MAX_ITEMS_PER_SITE}\nPolling: {POLLING_ENABLED}"
    elif cmd == '/today':
        send_telegram("🔄 Scanning all sites...", reply_to_message_id=msg_id)
        all_content = "\n\n".join([scrape_site(u) for u in TARGET_URLS])
        summary = call_ai(all_content) or all_content[:500]
        return f"🏗️ <b>On-Demand Digest</b>\n📅 {time.strftime('%d %b %Y')}\n\n{summary}"
    elif cmd == '/check' and args:
        send_telegram(f"🔍 Scanning {args}...", reply_to_message_id=msg_id)
        content = scrape_site(args)
        summary = call_ai(content) or content[:500]
        return f"🔍 <b>Single Site Check</b>\n{args}\n\n{summary}"
    else:
        return "❓ Unknown command. Try /help"

def main():
    print("🔍 Starting Monitor...")
    last_update_id = 0
    
    # 1. Check for Telegram Commands (Polling)
    if POLLING_ENABLED:
        updates = get_telegram_updates(last_update_id)
        for update in updates.get("result", []):
            if "message" in update and str(update["message"]["chat"]["id"]) == str(CHAT_ID):
                msg = update["message"]
                cmd, args = (msg.get("text","").split(maxsplit=1) + [None])[:2]
                if cmd.startswith('/'):
                    resp = handle_command(cmd.lower(), args, msg["message_id"])
                    if resp: send_telegram(resp, reply_to_message_id=msg["message_id"])
                    last_update_id = update["update_id"] + 1
                    print("✅ Command processed")
                    return  # Exit after handling command to save time
    
    # 2. Run Scheduled Digest (if no command)
    print("📰 Running scheduled digest...")
    all_content = "\n\n".join([scrape_site(u) for u in TARGET_URLS])
    summary = call_ai(all_content) or all_content[:500]
    msg = f"🏗️ <b>Victoria Building Digest</b>\n📅 {time.strftime('%d %b %Y')}\n📰 Sites: {len(TARGET_URLS)}\n\n{summary}"
    send_telegram(msg)
    print("✅ Digest sent")

if __name__ == "__main__":
    main()
