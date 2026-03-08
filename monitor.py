import os, requests, time, json, warnings, re
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from datetime import datetime, timedelta

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# === 🎛️ CONFIG ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CF_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")

# ✅ UPDATED: Consumer RSS removed. ABCB points to /news (not initiatives)
TARGET_URLS = [
    "https://www.bpc.vic.gov.au/news",
    "https://engage.vic.gov.au/security-buying-building-a-home",
    "https://www.abcb.gov.au/news",  # ✅ Only news, no resources/initiatives
]

MAX_ITEMS = 15  # ✅ Increased (more space now that RSS is gone)
MAX_AGE_DAYS = 30  # ✅ Only show news from last 30 days

def log(msg): print(f"📝 [LOG] {msg}")

def send_telegram(text, reply_id=None):
    if len(text) > 4000: text = text[:3950] + "\n\n...(more)"
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False}
    if reply_id: data["reply_to_message_id"] = reply_id
    try:
        return requests.post(url, json=data, timeout=30).json()
    except Exception as e:
        log(f"✗ Telegram: {e}")
        return None

def clean_url(href, base):
    if not href: return base
    href = href.strip().split()[0]
    if href.startswith(('http://','https://')): return href
    if href.startswith('//'): return f"https:{href}"
    return f"{base}{href}" if href.startswith('/') else f"{base}/{href}"

def parse_date(date_str):
    """Parse common date formats to datetime"""
    if not date_str: return None
    formats = [
        "%d %B %Y", "%d %b %Y", "%Y-%m-%d", 
        "%d/%m/%Y", "%B %d, %Y", "%b %d, %Y"
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except: pass
    return None

def is_recent(pub_date, max_days=MAX_AGE_DAYS):
    if not pub_date: return True  # Include if no date found
    return (datetime.now() - pub_date).days <= max_days

def scrape_with_links(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "html.parser")
        items, base = [], "/".join(url.split("/")[:3])
        
        # ✅ ABCB NEWS (with date filtering)
        if "abcb.gov.au" in url:
            log(f"🔧 ABCB News scraper...")
            raw_items = []
            # ABCB news list usually has <article> or <div class="news-item">
            for art in soup.find_all('article') or soup.find_all('div', class_=lambda c: c and 'news' in str(c).lower() if c else False):
                tt = art.find(['h2','h3','h4'])
                lk = art.find('a', href=True)
                # Try to find date (often in <time> or <span class="date">)
                dt = art.find(['time', 'span'], class_=lambda c: c and 'date' in str(c).lower() if c else False)
                
                if tt and lk:
                    title = tt.get_text().strip()
                    href = lk['href']
                    full_url = clean_url(href, base)
                    pub_date = parse_date(dt.get_text().strip() if dt else None)
                    
                    if 30 < len(title) < 300 and is_recent(pub_date):
                        raw_items.append({'title': title, 'link': full_url, 'date': pub_date})
            
            # Sort by date (newest first)
            raw_items.sort(key=lambda x: x['date'] if x['date'] else datetime.now(), reverse=True)
            
            for it in raw_items[:MAX_ITEMS]:
                items.append(f"📰 [ABCB] {it['title']}\n🔗 {it['link']}")
            
            log(f"✅ ABCB: {len(items)} (filtered by date)")
        
        # ✅ ENGAGE VICTORIA
        elif "engage.vic.gov.au" in url:
            log(f"🔧 Engage scraper...")
            for card in soup.find_all(['div','section'], class_=lambda c: c and any(x in str(c).lower() for x in ['card','project','consultation'])):
                tt = card.find(['h2','h3','h4','h5'], class_=lambda c: c and any(x in str(c).lower() for x in ['title','heading']))
                lk = card.find('a', href=True)
                if tt or lk:
                    txt = (tt.get_text() if tt else lk.get_text()).strip() if tt or lk else ""
                    href = lk['href'] if lk else url
                    full = clean_url(href, base)
                    if 20 < len(txt) < 400:
                        items.append(f"📰 [ENGAGE] {txt}\n🔗 {full}")
                        if len(items) >= MAX_ITEMS: break
            if not items:
                tt = soup.find('title')
                if tt: items.append(f"📰 [ENGAGE] {tt.get_text().strip()}\n🔗 {url}")
            log(f"✅ Engage: {len(items)}")
        
        # ✅ BPC NEWS (Standard HTML)
        else:
            src = "BPC"
            log(f"🔧 BPC scraper...")
            raw_items = []
            for art in soup.find_all('article') or soup.find_all('div', class_=lambda c: c and 'news' in str(c).lower() if c else False):
                lk, tt = art.find('a', href=True), art.find(['h2','h3','h4'], class_=lambda c: c and any(x in str(c).lower() for x in ['title','heading']) if c else False)
                # Try to find date
                dt = art.find(['time', 'span'], class_=lambda c: c and 'date' in str(c).lower() if c else False)
                
                if lk and tt:
                    txt = tt.get_text().strip()
                    href = lk['href']
                    full = clean_url(href, base)
                    pub_date = parse_date(dt.get_text().strip() if dt else None)
                    
                    if 30 < len(txt) < 300 and is_recent(pub_date):
                        raw_items.append({'title': txt, 'link': full, 'date': pub_date})
            
            # Sort by date
            raw_items.sort(key=lambda x: x['date'] if x['date'] else datetime.now(), reverse=True)
            
            for it in raw_items[:MAX_ITEMS]:
                items.append(f"📰 [{src}] {it['title']}\n🔗 {it['link']}")
            
            log(f"✅ BPC: {len(items)} (filtered by date)")
        
        return f"🌐 {url}\n✅ {len(items)}\n\n" + "\n\n".join(items[:MAX_ITEMS]) if items else f"🌐 {url}\n⚠️ None"
    except Exception as e:
        log(f"✗ {url}: {e}")
        return f"🌐 {url}\n❌ {type(e).__name__}"

def call_ai(text):
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/meta/llama-3-8b-instruct"
    headers = {"Authorization": f"Bearer {CF_TOKEN}", "Content-Type": "application/json"}
    
    # ✅ LEAN PROMPT - No filler, no Consumer Affairs
    prompt = f"""Victoria building news (last 30 days). Reforms, compliance, safety only.
Rules: 1) 🔗 link EVERY item 2) Source labels [BPC],[ENGAGE],[ABCB] 3) Group by source 4) Bullets+emojis 5) Max 500 words
News:
{text[:8000]}
Format:
🏗️ <b>BPC</b>
• 📋 [Summary] 🔗 [URL]
📢 <b>Engage</b>
• 📋 Summary 🔗 [URL]
🏛️ <b>ABCB</b>
• 📋 Summary 🔗 [URL]"""
    
    try:
        r = requests.post(url, headers=headers, json={"messages": [{"role": "user", "content": prompt}], "max_tokens": 1200}, timeout=90)
        r.raise_for_status()
        return r.json()['result']['response'].strip()
    except Exception as e:
        log(f"✗ AI: {e}")
        return None

def run_scheduled():
    log("📰 Running...")
    content = "\n\n".join([scrape_with_links(u) for u in TARGET_URLS])
    summary = call_ai(content) or content[:800]
    msg = f"🏗️ Victoria Building News\n📅 {time.strftime('%d %b %Y')}\n\n{summary}"
    send_telegram(msg)
    log("✅ Sent")

def check_commands():
    try:
        updates = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates", params={"timeout":1}, timeout=10).json().get("result",[])
        for upd in updates:
            if "message" not in upd: continue
            msg = upd["message"]
            if str(msg["chat"]["id"]) != str(CHAT_ID): continue
            txt = msg.get("text","").strip()
            if not txt.startswith("/") or time.time()-msg.get("date",0)>600: continue
            cmd = txt.split()[0].lower()
            if cmd == "/ping": return "🏓 Pong"
            elif cmd == "/today":
                send_telegram("🔄", reply_id=msg["message_id"])
                content = "\n\n".join([scrape_with_links(u) for u in TARGET_URLS])
                return f"🏗️ Victoria Building News\n📅 {time.strftime('%d %b')}\n\n{call_ai(content) or content[:700]}"
        return None
    except: return None

def main():
    log("🔍 Start")
    if check_commands(): return
    run_scheduled()
    log("✅ Done")

if __name__ == "__main__":
    main()
