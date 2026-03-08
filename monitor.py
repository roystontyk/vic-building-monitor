import os, requests, time, json, warnings, re
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# === 🎛️ CONFIG ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CF_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")

TARGET_URLS = [
    "https://www.bpc.vic.gov.au/news",
    "https://engage.vic.gov.au/security-buying-building-a-home",
    "https://www.abcb.gov.au/news",
]

MAX_ITEMS = 12  # ✅ Increased from 8 (saved space by removing fluff)

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
        is_rss = "rss.aspx" in url.lower() or ".rss" in url.lower()
        
        if is_rss:  # RSS feeds
            src = url.split('/')[2].replace('cms9.','').replace('.vic.gov.au','').upper()
            for item in soup.find_all('item'):
                t, l = item.find('title'), item.find('link')
                if t and l:
                    txt, lnk = t.get_text().strip(), l.get_text().strip().split()[0]
                    lnk = lnk if lnk.startswith('http') else clean_url(lnk, base)
                    if 20 < len(txt) < 300 and lnk:
                        items.append(f"📰 [{src}] {txt}\n🔗 {lnk}")
                        if len(items) >= MAX_ITEMS: break
            log(f"✅ RSS {src}: {len(items)}")
        
        elif "engage.vic.gov.au" in url:  # Engage Victoria
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
        
        elif "abcb.gov.au" in url:  # ABCB
            src = "ABCB"
            for ni in soup.find_all('div', class_='news-item') or soup.find_all('article'):
                tt, lk = ni.find(['h3','h4','h2']), ni.find('a', href=True)
                if tt and lk:
                    txt, href = tt.get_text().strip(), lk['href']
                    full = clean_url(href, base)
                    if 30 < len(txt) < 300:
                        items.append(f"📰 [{src}] {txt}\n🔗 {full}")
                        if len(items) >= MAX_ITEMS: break
            if len(items) < MAX_ITEMS:
                for lk in soup.find_all('a', href=True):
                    txt, href = lk.get_text().strip(), lk['href']
                    if any(k in txt.lower() for k in ['construction','code','regulation','handbook','guidance','prefabricated']):
                        full = clean_url(href, base)
                        if 30 < len(txt) < 300:
                            items.append(f"📰 [{src}] {txt}\n🔗 {full}")
                            if len(items) >= MAX_ITEMS: break
            log(f"✅ ABCB: {len(items)}")
        
        else:  # Standard HTML (BPC)
            src = url.split('/')[2].replace('www.','').upper()
            for art in soup.find_all('article') or soup.find_all('div', class_=lambda c: c and 'news' in str(c).lower()):
                lk, tt = art.find('a', href=True), art.find(['h2','h3','h4'], class_=lambda c: c and any(x in str(c).lower() for x in ['title','heading']))
                if lk and tt:
                    txt, href = tt.get_text().strip(), lk['href']
                    full = clean_url(href, base)
                    if 30 < len(txt) < 300:
                        items.append(f"📰 [{src}] {txt}\n🔗 {full}")
                        if len(items) >= MAX_ITEMS: break
            log(f"✅ HTML {src}: {len(items)}")
        
        return f"🌐 {url}\n✅ {len(items)}\n\n" + "\n\n".join(items[:MAX_ITEMS]) if items else f"🌐 {url}\n⚠️ None"
    except Exception as e:
        log(f"✗ {url}: {e}")
        return f"🌐 {url}\n❌ {type(e).__name__}"

def call_ai(text):
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/meta/llama-3-8b-instruct"
    headers = {"Authorization": f"Bearer {CF_TOKEN}", "Content-Type": "application/json"}
    
    # ✅ LEAN PROMPT - No filler, no "What to Do/Next Steps"
    prompt = f"""Victoria building news. Reforms, compliance, safety only.
Rules: 1) 🔗 link EVERY item 2) Source labels [BPC],[CONSUMER],[ENGAGE],[ABCB] 3) Group by source 4) Bullets+emojis 5) Max 450 words
News:
{text[:7500]}
Format:
🏗️ <b>BPC</b>
• 📋 [Summary] 🔗 [URL]
📰 <b>Consumer Affairs</b>
• 📋 [NEWSALERTS] Summary 🔗 [URL]
📢 <b>Engage</b>
• 📋 Summary 🔗 [URL]
🏛️ <b>ABCB</b>
• 📋 Summary 🔗 [URL]"""
    
    try:
        r = requests.post(url, headers=headers, json={"messages": [{"role": "user", "content": prompt}], "max_tokens": 1100}, timeout=90)
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
