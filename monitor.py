import os, requests, time, json, warnings
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# === 🎛️ CONFIG ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CF_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")

# ✅ ALL 3 SOURCES - ABCB NEWS ONLY
TARGET_URLS = [
    "https://www.bpc.vic.gov.au/news",
    "https://engage.vic.gov.au/security-buying-building-a-home",
    "https://www.abcb.gov.au/news",  # ✅ News section only
]

MAX_ITEMS = 15

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

def scrape_with_links(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "html.parser")
        items, base = [], "/".join(url.split("/")[:3])
        
        # ✅ BPC (Standard HTML news)
        if "bpc.vic.gov.au" in url:
            src = "BPC"
            for art in soup.find_all('article') or soup.find_all('div', class_=lambda c: c and 'news' in str(c).lower()):
                lk, tt = art.find('a', href=True), art.find(['h2','h3','h4'], class_=lambda c: c and any(x in str(c).lower() for x in ['title','heading']))
                if lk and tt:
                    txt, href = tt.get_text().strip(), lk['href']
                    full = clean_url(href, base)
                    if 30 < len(txt) < 300 and '/news/' in full:
                        items.append(f"📰 [{src}] {txt}\n🔗 {full}")
                        if len(items) >= MAX_ITEMS: break
            log(f"✅ BPC: {len(items)}")
        
        # ✅ Engage Victoria
        elif "engage.vic.gov.au" in url:
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
        
        # ✅ ABCB - NEWS ONLY (filter out /initiatives/, /resources/, etc.)
        elif "abcb.gov.au" in url:
            src = "ABCB"
            # Strategy 1: Look for <article> or news containers with /news/ in link
            for article in soup.find_all('article') or soup.find_all('div', class_=lambda c: c and 'news' in str(c).lower()):
                tt = article.find(['h3','h4','h2'])
                lk = article.find('a', href=True)
                if tt and lk:
                    txt = tt.get_text().strip()
                    href = lk['href']
                    # ✅ CRITICAL: Only accept URLs with /news/ in path
                    if '/news/' in href or '/news?' in href:
                        full = clean_url(href, base)
                        if 30 < len(txt) < 300:
                            items.append(f"📰 [{src}] {txt}\n🔗 {full}")
                            if len(items) >= MAX_ITEMS: break
            
            # Strategy 2: Fallback - scan all links for /news/ pattern
            if len(items) < MAX_ITEMS:
                for lk in soup.find_all('a', href=True):
                    href = lk['href']
                    # ✅ Only grab /news/ URLs
                    if '/news/' in href or '/news?' in href:
                        txt = lk.get_text().strip()
                        full = clean_url(href, base)
                        if txt and 30 < len(txt) < 300:
                            items.append(f"📰 [{src}] {txt}\n🔗 {full}")
                            if len(items) >= MAX_ITEMS: break
            
            log(f"✅ ABCB News: {len(items)}")
        
        return f"🌐 {url}\n✅ {len(items)}\n\n" + "\n\n".join(items[:MAX_ITEMS]) if items else f"🌐 {url}\n⚠️ None"
    except Exception as e:
        log(f"✗ {url}: {e}")
        return f"🌐 {url}\n❌ {type(e).__name__}"

def call_ai(text):
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/meta/llama-3-8b-instruct"
    headers = {"Authorization": f"Bearer {CF_TOKEN}", "Content-Type": "application/json"}
    
    # ✅ 3-SOURCE PROMPT - ABCB NEWS ONLY
    prompt = f"""Victoria building news. Reforms, compliance, safety.
Rules: 1) 🔗 link EVERY item 2) Labels [BPC],[ENGAGE],[ABCB] 3) Group by source 4) Bullets+emojis 5) Max 500 words
News:
{text[:8000]}
Format:
🏗️ <b>BPC</b>
• 📋 [Summary] 🔗 [URL]
📢 <b>Engage</b>
• 📋 [Summary] 🔗 [URL]
🏛️ <b>ABCB News</b>
• 📋 [Summary] 🔗 [URL]"""
    
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
    summary = call_ai(content) or content[:700]
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
                return f"🏗️ Victoria Building News\n📅 {time.strftime('%d %b')}\n\n{call_ai(content) or content[:600]}"
        return None
    except: return None

def main():
    log("🔍 Start")
    if check_commands(): return
    run_scheduled()
    log("✅ Done")

if __name__ == "__main__":
    main()
