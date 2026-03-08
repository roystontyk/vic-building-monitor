import os, requests, time, json
from bs4 import BeautifulSoup

# === 🎛️ USER CONFIGURATION ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CF_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")

# ✅ TARGET_URLS - All Cleaned & Organized (NO TRAILING SPACES!)
TARGET_URLS = [
    # ─────────────────────────────────────────────────────────────
    # 🏗️ BUILDING PRACTITIONERS COMMISSION (HTML News Page)
    # ─────────────────────────────────────────────────────────────
    "https://www.bpc.vic.gov.au/news",
    
    # ─────────────────────────────────────────────────────────────
    # 📢 ENGAGE VICTORIA - Public Consultations (HTML Pages)
    # ─────────────────────────────────────────────────────────────
    "https://engage.vic.gov.au/security-buying-building-a-home",
    # "https://engage.vic.gov.au/",  # ⚠️ Too generic - may return irrelevant content
    
    # ─────────────────────────────────────────────────────────────
    # 📰 CONSUMER AFFAIRS VICTORIA - RSS Feeds (Most Reliable!)
    # ─────────────────────────────────────────────────────────────
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=newsalerts",
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=mediareleases",
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=courtactions",
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=enforceableundertakings",
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=legislationupdates",
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=publicwarnings",
    
    # ─────────────────────────────────────────────────────────────
    # 🏛️ ADDITIONAL SOURCES (Uncomment to Enable)
    # ─────────────────────────────────────────────────────────────
    # "https://www.vba.vic.gov.au/news-and-publications/news",
    # "https://www.planning.vic.gov.au/news-and-media/media-releases/rss",
    # "https://www.abcb.gov.au/news",
]

MAX_ITEMS = 10

print(f"🔍 [DEBUG] Script starting. CHAT_ID: {CHAT_ID[:5]}...")

def log(msg): print(f"📝 [LOG] {msg}")

def send_telegram(text, reply_id=None):
    log(f"Sending Telegram: {text[:100]}...")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False}
    if reply_id: data["reply_to_message_id"] = reply_id
    try:
        r = requests.post(url, json=data, timeout=30)
        log(f"Telegram response: {r.status_code}")
        return r.json()
    except Exception as e:
        log(f"✗ Telegram error: {e}")
        return None

def check_commands():
    log("🔍 Checking Telegram for commands...")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"timeout": 1, "allowed_updates": ["message"]}
    try:
        r = requests.get(url, params=params, timeout=10)
        updates = r.json().get("result", [])
        log(f"Found {len(updates)} Telegram updates")
        
        for upd in updates:
            if "message" not in upd: continue
            msg = upd["message"]
            chat_id = str(msg["chat"]["id"])
            text = msg.get("text", "").strip()
            msg_id = msg["message_id"]
            date = msg.get("date", 0)
            
            log(f"📨 Message: chat={chat_id}, text='{text}', date={date}")
            
            if chat_id != str(CHAT_ID):
                continue
            if time.time() - date > 120:
                continue
            if not text.startswith("/"):
                continue
            
            parts = text.split(maxsplit=1)
            cmd = parts[0].lower()
            args = parts[1] if len(parts) > 1 else None
            log(f"🎮 Processing: {cmd} {args}")
            
            if cmd == "/ping":
                return "🏓 Pong! Bot is alive. ✅"
            elif cmd == "/help":
                return "<b>Commands:</b>\n/ping - Test\n/today - Scan all sites\n/check [url] - Scan one site"
            elif cmd == "/today":
                send_telegram("🔄 Scanning all sites...", reply_id=msg_id)
                content = "\n\n".join([scrape_with_links(u) for u in TARGET_URLS])
                summary = call_ai(content) or content[:400]
                return f"🏗️ <b>On-Demand Digest</b>\n📅 {time.strftime('%d %b %Y')}\n\n{summary}"
            elif cmd == "/check" and args:
                send_telegram(f"🔍 Scanning {args}...", reply_id=msg_id)
                content = scrape_with_links(args)
                summary = call_ai(content) or content[:400]
                return f"🔍 <b>Result</b>\n{summary}"
            else:
                return f"❓ Unknown: {cmd}. Try /help"
        
        log("✅ No new commands found")
        return None
    except Exception as e:
        log(f"✗ Command check error: {e}")
        return None

def scrape_with_links(url):
    """Scrape news items WITH their individual article links"""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"}
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "html.parser")
        
        items = []
        base_domain = "/".join(url.split("/")[:3])
        
        # ✅ SPECIAL HANDLING for engage.vic.gov.au
        if "engage.vic.gov.au" in url:
            log(f"🔧 Using engage.vic.gov.au scraper...")
            for card in soup.find_all(['div', 'a'], class_=lambda c: c and any(x in c.lower() for x in ['card', 'project', 'consultation', 'engagement'])):
                title_tag = card.find(['h2', 'h3', 'h4', 'span', 'p'], class_=lambda c: c and any(x in c.lower() for x in ['title', 'heading', 'name']))
                link_tag = card.find('a', href=True) if card.name != 'a' else card
                
                if title_tag or link_tag:
                    title = title_tag.get_text().strip() if title_tag else link_tag.get_text().strip()
                    href = link_tag['href'] if link_tag else url
                    full_url = href if href.startswith('http') else f"{base_domain}{href}"
                    
                    if title and 20 < len(title) < 300:
                        items.append(f"📰 {title}\n🔗 {full_url}")
                        if len(items) >= MAX_ITEMS:
                            break
            
            if len(items) < MAX_ITEMS:
                for link in soup.find_all('a', href=True):
                    text = link.get_text().strip()
                    href = link['href']
                    if any(kw in text.lower() for kw in ['building', 'construction', 'planning', 'home', 'security', 'consultation']):
                        full_url = href if href.startswith('http') else f"{base_domain}{href}"
                        if text and 20 < len(text) < 300:
                            items.append(f"📰 {text}\n🔗 {full_url}")
                            if len(items) >= MAX_ITEMS:
                                break
        
        # ✅ SPECIAL HANDLING for RSS feeds
        elif "rss.aspx" in url.lower() or ".rss" in url.lower() or "/feed" in url.lower():
            log(f"🔧 Using RSS feed parser...")
            for item in soup.find_all('item'):
                title = item.find('title')
                link = item.find('link')
                pubdate = item.find('pubdate')
                
                if title and link:
                    title_text = title.get_text().strip()
                    link_url = link.get_text().strip()
                    date_text = f" ({pubdate.get_text().strip()[:16]})" if pubdate else ""
                    
                    if title_text and 20 < len(title_text) < 300:
                        items.append(f"📰 {title_text}{date_text}\n🔗 {link_url}")
                        if len(items) >= MAX_ITEMS:
                            break
        
        # ✅ STANDARD HANDLING for HTML news pages
        else:
            log(f"🔧 Using standard news scraper...")
            articles = soup.find_all('article') or soup.find_all('div', class_=lambda c: c and 'news' in c.lower())
            for article in articles:
                link_tag = article.find('a', href=True)
                title_tag = article.find(['h2', 'h3', 'h4', 'a'], class_=lambda c: c and any(x in c.lower() for x in ['title', 'heading', 'news']))
                
                if link_tag and title_tag:
                    title = title_tag.get_text().strip()
                    href = link_tag['href']
                    full_url = href if href.startswith('http') else f"{base_domain}{href}"
                    
                    if title and 30 < len(title) < 300:
                        items.append(f"📰 {title}\n🔗 {full_url}")
                        if len(items) >= MAX_ITEMS:
                            break
            
            if len(items) < MAX_ITEMS:
                for link in soup.find_all('a', href=True):
                    title = link.get_text().strip()
                    href = link['href']
                    full_url = href if href.startswith('http') else f"{base_domain}{href}"
                    
                    if title and 30 < len(title) < 300 and 'http' in full_url:
                        if any(skip in title.lower() for skip in ['home', 'contact', 'about', 'privacy', 'subscribe']):
                            continue
                        items.append(f"📰 {title}\n🔗 {full_url}")
                        if len(items) >= MAX_ITEMS:
                            break
        
        if len(items) < MAX_ITEMS:
            for p in soup.find_all('p'):
                text = p.get_text().strip()
                if text and 50 < len(text) < 300:
                    items.append(f"📰 {text}\n🔗 {url}")
                    if len(items) >= MAX_ITEMS:
                        break
        
        if items:
            return f"🌐 Source: {url}\n\n" + "\n\n".join(items[:MAX_ITEMS])
        return f"🌐 Source: {url}\nNo items found."
        
    except Exception as e:
        log(f"✗ Scrape error for {url}: {e}")
        return f"🌐 Source: {url}\n❌ Error: {e}"

def call_ai(text):
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/meta/llama-3-8b-instruct"
    headers = {"Authorization": f"Bearer {CF_TOKEN}", "Content-Type": "application/json"}
    
    prompt = f"""You are a helpful assistant for property professionals in Victoria, Australia.

TASK: Summarize these Victorian building/planning news items. Focus on reforms, regulations, compliance, safety, and legal updates.

IMPORTANT: 
1. Include the 🔗 link for EACH news item you mention
2. Make links clickable (Telegram supports raw URLs)
3. Group by topic, not by source
4. Use bullet points with emojis
5. Keep under 400 words

NEWS ITEMS:
{text[:4000]}

OUTPUT FORMAT:
🏗️ <b>Key Updates</b>
• 📋 [Summary] 🔗 [URL]
• 📋 [Summary] 🔗 [URL]

💡 <b>What to Do</b>
• [Action item]

📅 <b>Next Steps</b>
• [Follow-up suggestion]

If no relevant reforms: Say "✅ No major reforms found" but still list headlines with links."""

    try:
        r = requests.post(url, headers=headers, json={
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 800
        }, timeout=90)
        r.raise_for_status()
        return r.json()['result']['response'].strip()
    except Exception as e:
        log(f"✗ AI error: {e}")
        return None

def run_scheduled():
    log("📰 Running scheduled digest...")
    content = "\n\n".join([scrape_with_links(u) for u in TARGET_URLS])
    summary = call_ai(content) or content[:400]
    msg = f"🏗️ <b>Victoria Building Digest</b>\n📅 {time.strftime('%d %b %Y')}\n📰 Sites: {len(TARGET_URLS)}\n\n{summary}"
    send_telegram(msg)
    log("✅ Scheduled digest sent")

def main():
    log("🔍 Monitor starting...")
    
    response = check_commands()
    if response:
        log(f"🎯 Sending command response")
        send_telegram(response)
        log("✅ Command handled, exiting")
        return
    
    run_scheduled()
    log("✅ Done")

if __name__ == "__main__":
    main()
