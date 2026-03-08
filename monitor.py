import os, requests, time, json, warnings
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

# === Suppress XML Warning ===
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# === 🎛️ USER CONFIGURATION ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CF_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")

# ✅ TARGET_URLS - Clean, tested, working only
TARGET_URLS = [
    "https://www.bpc.vic.gov.au/news",
    "https://engage.vic.gov.au/security-buying-building-a-home",
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=newsalerts",
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=mediareleases",
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=courtactions",
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=enforceableundertakings",
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=legislationupdates",
    "https://cms9.consumer.vic.gov.au/RSS.aspx?RssType=publicwarnings",
    "https://www.abcb.gov.au/news",
]

MAX_ITEMS = 8

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
            
            if chat_id != str(CHAT_ID): continue
            if time.time() - date > 600: continue
            if not text.startswith("/"): continue
            
            parts = text.split(maxsplit=1)
            cmd = parts[0].lower()
            args = parts[1] if len(parts) > 1 else None
            
            if cmd == "/ping": return "🏓 Pong! Bot is alive. ✅"
            elif cmd == "/help": return "<b>Commands:</b>\n/ping - Test\n/today - Scan all sites"
            elif cmd == "/today":
                send_telegram("🔄 Scanning...", reply_id=msg_id)
                content = "\n\n".join([scrape_with_links(u) for u in TARGET_URLS])
                summary = call_ai(content) or content[:600]
                return f"🏗️ <b>On-Demand</b>\n📅 {time.strftime('%d %b %Y')}\n\n{summary}"
            elif cmd == "/check" and args:
                send_telegram(f"🔍 Scanning {args}...", reply_id=msg_id)
                content = scrape_with_links(args)
                summary = call_ai(content) or content[:600]
                return f"🔍 <b>Result</b>\n{summary}"
            else: return f"❓ Unknown: {cmd}. Try /help"
        return None
    except Exception as e:
        log(f"✗ Command error: {e}")
        return None

def clean_url(href, base_domain):
    """Clean and normalize URLs"""
    if not href: return base_domain
    href = href.strip()  # ✅ Remove whitespace
    if href.startswith('http'): return href.split()[0]  # ✅ Take first part if space exists
    if href.startswith('//'): return f"https:{href}"
    if href.startswith('/'): return f"{base_domain}{href}"
    return f"{base_domain}/{href}" if base_domain else href

def scrape_with_links(url):
    """Scrape news items WITH links - FIXED VERSION"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        
        # ✅ FIXED: Use html.parser for ALL feeds (no lxml dependency needed)
        soup = BeautifulSoup(r.content, "html.parser")
        
        items = []
        base_domain = "/".join(url.split("/")[:3])
        is_rss = "rss.aspx" in url.lower() or ".rss" in url.lower() or "/feed" in url.lower()
        
        # ✅ RSS FEEDS - Using html.parser fallback
        if is_rss:
            log(f"🔧 RSS parser (html fallback) for {url}...")
            source_name = url.split('/')[2].replace('cms9.', '').replace('.vic.gov.au', '').upper()
            
            # Try <item> tags first (standard RSS)
            for item in soup.find_all('item'):
                title = item.find('title')
                link = item.find('link')
                if title and link:
                    title_text = title.get_text().strip()
                    link_url = clean_url(link.get_text().strip(), base_domain)
                    if title_text and 20 < len(title_text) < 300:
                        items.append(f"📰 [{source_name}] {title_text}\n🔗 {link_url}")
                        if len(items) >= MAX_ITEMS: break
            
            # Fallback: look for <entry> (Atom feeds)
            if len(items) < MAX_ITEMS:
                for entry in soup.find_all('entry'):
                    title = entry.find('title')
                    link = entry.find('link', href=True)
                    if title and link:
                        title_text = title.get_text().strip()
                        link_url = clean_url(link['href'], base_domain)
                        if title_text and 20 < len(title_text) < 300:
                            items.append(f"📰 [{source_name}] {title_text}\n🔗 {link_url}")
                            if len(items) >= MAX_ITEMS: break
            
            log(f"✅ RSS: Found {len(items)} items")
        
        # ✅ ENGAGE VICTORIA - Aggressive fallback scraper
        elif "engage.vic.gov.au" in url:
            log(f"🔧 Engage VIC scraper...")
            
            # Strategy 1: Look for consultation cards
            for card in soup.find_all(['div', 'section'], class_=lambda c: c and any(x in str(c).lower() for x in ['card', 'project', 'consultation', 'engagement'])):
                title = card.find(['h2', 'h3', 'h4', 'h5', 'span', 'p'], class_=lambda c: c and any(x in str(c).lower() for x in ['title', 'heading', 'name']))
                link_tag = card.find('a', href=True)
                if title or link_tag:
                    title_text = title.get_text().strip() if title else (link_tag.get_text().strip() if link_tag else "")
                    href = link_tag['href'] if link_tag else url
                    full_url = clean_url(href, base_domain)
                    if title_text and 20 < len(title_text) < 400:
                        items.append(f"📰 [ENGAGE-VIC] {title_text}\n🔗 {full_url}")
                        if len(items) >= MAX_ITEMS: break
            
            # Strategy 2: Grab ALL links with building keywords
            if len(items) < MAX_ITEMS:
                for link in soup.find_all('a', href=True):
                    text = link.get_text().strip()
                    href = link['href']
                    combined = (text + " " + href).lower()
                    if any(kw in combined for kw in ['building', 'construction', 'planning', 'home', 'security', 'consultation', 'survey', 'feedback', 'regulation']):
                        full_url = clean_url(href, base_domain)
                        if text and 20 < len(text) < 400:
                            items.append(f"📰 [ENGAGE-VIC] {text}\n🔗 {full_url}")
                            if len(items) >= MAX_ITEMS: break
            
            # Strategy 3: Last resort - page title + URL
            if not items:
                page_title = soup.find('title')
                title_text = page_title.get_text().strip() if page_title else "Consultation"
                items.append(f"📰 [ENGAGE-VIC] {title_text}\n🔗 {url}")
            
            log(f"✅ Engage VIC: Found {len(items)} items")
        
        # ✅ STANDARD HTML NEWS
        else:
            log(f"🔧 Standard scraper for {url}...")
            source_name = url.split('/')[2].replace('www.', '').upper()
            
            for article in soup.find_all('article') or soup.find_all('div', class_=lambda c: c and 'news' in str(c).lower()):
                link_tag = article.find('a', href=True)
                title_tag = article.find(['h2', 'h3', 'h4', 'a'], class_=lambda c: c and any(x in str(c).lower() for x in ['title', 'heading', 'news']))
                if link_tag and title_tag:
                    title = title_tag.get_text().strip()
                    href = link_tag['href']
                    full_url = clean_url(href, base_domain)
                    if title and 30 < len(title) < 300:
                        items.append(f"📰 [{source_name}] {title}\n🔗 {full_url}")
                        if len(items) >= MAX_ITEMS: break
            
            if len(items) < MAX_ITEMS:
                for link in soup.find_all('a', href=True):
                    title = link.get_text().strip()
                    href = link['href']
                    full_url = clean_url(href, base_domain)
                    if title and 30 < len(title) < 300 and 'http' in full_url:
                        if any(skip in title.lower() for skip in ['home', 'contact', 'about', 'privacy', 'subscribe', 'menu']): continue
                        items.append(f"📰 [{source_name}] {title}\n🔗 {full_url}")
                        if len(items) >= MAX_ITEMS: break
            
            log(f"✅ HTML: Found {len(items)} items")
        
        if items:
            return f"🌐 Source: {url}\n✅ Items: {len(items)}\n\n" + "\n\n".join(items[:MAX_ITEMS])
        return f"🌐 Source: {url}\n⚠️ No items found"
        
    except Exception as e:
        log(f"✗ Error for {url}: {e}")
        return f"🌐 Source: {url}\n❌ Error: {type(e).__name__}"

def call_ai(text):
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/meta/llama-3-8b-instruct"
    headers = {"Authorization": f"Bearer {CF_TOKEN}", "Content-Type": "application/json"}
    
    prompt = f"""Summarize Victorian building news. Focus on reforms, compliance, safety.
RULES:
1. Include 🔗 link for EACH item
2. Show source labels: [BPC], [CONSUMER-AFFAIRS], [ENGAGE-VIC], [ABCB]
3. Group by SOURCE first
4. Bullet points with emojis, under 600 words

NEWS:
{text[:7000]}

FORMAT:
🏗️ <b>Building Practitioners Commission</b>
• 📋 [Summary] 🔗 [URL]

📰 <b>Consumer Affairs RSS</b>
• 📋 [NEWSALERTS] Summary 🔗 [URL]

📢 <b>Engage Victoria</b>
• 📋 [Summary] 🔗 [URL]

🏛️ <b>ABCB</b>
• 📋 [Summary] 🔗 [URL]

💡 <b>What to Do</b>
• [Action]

📅 <b>Next Steps</b>
• [Follow-up]"""

    try:
        r = requests.post(url, headers=headers, json={"messages": [{"role": "user", "content": prompt}], "max_tokens": 1200}, timeout=90)
        r.raise_for_status()
        return r.json()['result']['response'].strip()
    except Exception as e:
        log(f"✗ AI error: {e}")
        return None

def run_scheduled():
    log("📰 Running digest...")
    all_content = []
    working = 0
    for url in TARGET_URLS:
        result = scrape_with_links(url)
        all_content.append(result)
        if "✅ Items:" in result: working += 1
    
    content = "\n\n".join(all_content)
    log(f"📊 {working}/{len(TARGET_URLS)} sources working")
    summary = call_ai(content) or content[:800]
    msg = f"🏗️ <b>Victoria Building Digest</b>\n📅 {time.strftime('%d %b %Y')}\n📰 Sources: {working}/{len(TARGET_URLS)}\n\n{summary}"
    send_telegram(msg)
    log("✅ Sent")

def main():
    log("🔍 Starting...")
    response = check_commands()
    if response:
        send_telegram(response)
        return
    run_scheduled()
    log("✅ Done")

if __name__ == "__main__":
    main()
