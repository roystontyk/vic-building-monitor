import os, requests, time, json, warnings, sys
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# === 🎛️ CONFIG ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CF_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")

# ✅ REMOVED: All 6 Consumer Affairs RSS feeds
TARGET_URLS = [
    "https://www.bpc.vic.gov.au/news",
    "https://engage.vic.gov.au/security-buying-building-a-home",
    "https://www.abcb.gov.au/news",
]

MAX_ITEMS = 15  # ✅ Increased (fewer sources = more items per source)

def log(msg): 
    print(f"📝 [LOG] {msg}")
    sys.stdout.flush()

def send_telegram(text, reply_id=None):
    log(f"📤 Sending Telegram ({len(text)} chars)...")
    try:
        if len(text) > 4000: 
            text = text[:3950] + "\n\n...(more)"
            log("⚠️ Message truncated")
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False}
        if reply_id: data["reply_to_message_id"] = reply_id
        r = requests.post(url, json=data, timeout=30)
        log(f"✅ Telegram: {r.status_code}")
        return r.json()
    except Exception as e:
        log(f"❌ TELEGRAM FAILED: {type(e).__name__}: {e}")
        raise

def clean_url(href, base):
    if not href: return base
    href = href.strip().split()[0]  # ✅ Remove spaces
    if href.startswith(('http://','https://')): return href
    if href.startswith('//'): return f"https:{href}"
    return f"{base}{href}" if href.startswith('/') else f"{base}/{href}"

def scrape_with_links(url):
    start = time.time()
    try:
        log(f"🔍 Scraping: {url[:60]}...")
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        log(f"✅ HTTP OK ({r.status_code}) in {time.time()-start:.1f}s")
        
        soup = BeautifulSoup(r.content, "html.parser")
        items, base = [], "/".join(url.split("/")[:3])
        
        # ✅ ENGAGE VICTORIA
        if "engage.vic.gov.au" in url:
            log("📡 Parsing Engage Victoria...")
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
            log(f"✅ Engage: {len(items)} items")
        
        # ✅ ABCB
        elif "abcb.gov.au" in url:
            log("📡 Parsing ABCB...")
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
                    if any(k in txt.lower() for k in ['construction','code','regulation','handbook','guidance','prefabricated','NCC','performance']):
                        full = clean_url(href, base)
                        if 30 < len(txt) < 300:
                            items.append(f"📰 [{src}] {txt}\n🔗 {full}")
                            if len(items) >= MAX_ITEMS: break
            log(f"✅ ABCB: {len(items)} items")
        
        # ✅ BPC (Standard HTML)
        else:
            log("📡 Parsing BPC...")
            src = "BPC"
            for art in soup.find_all('article') or soup.find_all('div', class_=lambda c: c and 'news' in str(c).lower()):
                lk, tt = art.find('a', href=True), art.find(['h2','h3','h4'], class_=lambda c: c and any(x in str(c).lower() for x in ['title','heading']))
                if lk and tt:
                    txt, href = tt.get_text().strip(), lk['href']
                    full = clean_url(href, base)
                    if 30 < len(txt) < 300:
                        items.append(f"📰 [{src}] {txt}\n🔗 {full}")
                        if len(items) >= MAX_ITEMS: break
            log(f"✅ BPC: {len(items)} items")
        
        result = f"🌐 {url}\n✅ {len(items)}\n\n" + "\n\n".join(items[:MAX_ITEMS]) if items else f"🌐 {url}\n⚠️ None"
        log(f"✅ DONE: {url[:50]}... ({len(items)} items)")
        return result
        
    except requests.exceptions.Timeout:
        log(f"❌ TIMEOUT: {url[:60]}...")
        return f"🌐 {url}\n⏰ Timeout"
    except Exception as e:
        log(f"❌ ERROR {url[:60]}...: {type(e).__name__}: {e}")
        return f"🌐 {url}\n❌ {type(e).__name__}"

def call_ai(text):
    log(f"🤖 Calling AI ({len(text)} chars)...")
    try:
        url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/meta/llama-3-8b-instruct"
        headers = {"Authorization": f"Bearer {CF_TOKEN}", "Content-Type": "application/json"}
        prompt = f"""Victoria building news. Reforms, compliance, safety only.
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
        
        log("📡 Posting to Cloudflare AI...")
        r = requests.post(url, headers=headers, json={"messages": [{"role": "user", "content": prompt}], "max_tokens": 1200}, timeout=30)
        log(f"✅ AI response: {r.status_code}")
        r.raise_for_status()
        result = r.json()['result']['response'].strip()
        log(f"✅ AI completed ({len(result)} chars)")
        return result
    except Exception as e:
        log(f"❌ AI FAILED: {type(e).__name__}: {e}")
        return None

def run_scheduled():
    log("📰 === RUNNING SCHEDULED DIGEST ===")
    try:
        all_content = []
        working = 0
        total = len(TARGET_URLS)
        
        for i, url in enumerate(TARGET_URLS, 1):
            log(f"📊 [{i}/{total}] Processing: {url[:50]}...")
            result = scrape_with_links(url)
            all_content.append(result)
            if "✅" in result: working += 1
        
        log(f"📊 COMPLETE: {working}/{total} sources working")
        content = "\n\n".join(all_content)
        log(f"📊 Total content: {len(content)} chars")
        
        summary = call_ai(content)
        if not summary:
            log("⚠️ AI failed, using raw content")
            summary = content[:800]
        
        msg = f"🏗️ Victoria Building News\n📅 {time.strftime('%d %b %Y')}\n\n{summary}"
        log(f"📊 Final message: {len(msg)} chars")
        
        send_telegram(msg)
        log("✅ === DIGEST SENT SUCCESSFULLY ===")
        
    except Exception as e:
        log(f"❌ === RUN_SCHEDULED FAILED: {type(e).__name__}: {e} ===")
        import traceback
        log(traceback.format_exc())
        raise

def check_commands():
    try:
        log("🔍 Checking Telegram commands...")
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
    except Exception as e:
        log(f"❌ Command check failed: {e}")
        return None

def main():
    log("🔍 === SCRIPT STARTING ===")
    log(f"🔑 TELEGRAM_TOKEN: {'✅ Set' if TELEGRAM_TOKEN else '❌ MISSING'}")
    log(f"🔑 CHAT_ID: {'✅ Set' if CHAT_ID else '❌ MISSING'}")
    log(f"🔑 CF_TOKEN: {'✅ Set' if CF_TOKEN else '❌ MISSING'}")
    log(f"🔑 CF_ACCOUNT_ID: {'✅ Set' if CF_ACCOUNT_ID else '❌ MISSING'}")
    
    try:
        if check_commands():
            log("✅ Command handled, exiting")
            return
        log("📰 No commands, running scheduled digest...")
        run_scheduled()
        log("✅ === SCRIPT COMPLETED SUCCESSFULLY ===")
    except Exception as e:
        log(f"❌ === MAIN FAILED: {type(e).__name__}: {e} ===")
        import traceback
        log(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()
