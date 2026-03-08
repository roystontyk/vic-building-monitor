import os, requests, time
from bs4 import BeautifulSoup

# === Configuration (from GitHub Secrets) ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CF_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")

# === Target: Building Practices Council News ===
TARGET_URL = "https://www.bpc.vic.gov.au/news"
HEADERS = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)'}

# === Settings ===
MAX_NEWS_ITEMS = 20  # How many items to scrape & summarize
MAX_TELEGRAM_LENGTH = 4000  # Telegram limit is 4096, leave room for formatting

def send_telegram(message):
    """Send message to Telegram with length safety"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    # Truncate if too long (Telegram limit: 4096 chars)
    if len(message) > MAX_TELEGRAM_LENGTH:
        message = message[:MAX_TELEGRAM_LENGTH-100] + "\n\n...(truncated)"
    data = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        resp = requests.post(url, json=data, timeout=30)
        resp.raise_for_status()
        print("✓ Telegram message sent")
        return True
    except Exception as e:
        print(f"✗ Telegram error: {e}")
        return False

def call_cloudflare_ai(text):
    """Send text to Cloudflare Workers AI for summarization"""
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/meta/llama-3-8b-instruct"
    headers = {
        "Authorization": f"Bearer {CF_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Smart prompt: summarize up to 20 news items with practical focus
    prompt = f"""You are a helpful assistant for property professionals in Victoria, Australia.

TASK: Review these news items from the Building Practices Council website and provide a concise, practical summary.

INSTRUCTIONS:
1. Summarize the TOP {MAX_NEWS_ITEMS} news items (or fewer if that's all that's available)
2. Focus on: building regulation changes, compliance updates, safety reforms, licensing news, or policy shifts
3. For each relevant item: include a 1-line summary + why it matters to builders/homeowners
4. Group similar topics together to avoid repetition
5. If an item is unrelated to building reforms (e.g., staff announcements, events), skip it
6. Use clear bullet points with emojis for readability
7. Keep total output under 350 words

NEWS ITEMS TO REVIEW:
{text}

OUTPUT FORMAT:
🏗️ <b>Key Updates</b>
• [Emoji] [Brief summary] → [Why it matters]
• [Emoji] [Brief summary] → [Why it matters]

💡 <b>What to Do</b>
• [Practical action item]
• [Practical action item]

📅 <b>Next Steps</b>
• [Follow-up suggestion]

If no relevant reforms found: Say "✅ No new building reforms this week. Check back soon!" and list 1-2 general news headlines for context."""

    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 800  # Allow longer response for 20 items
    }
    
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=90)
        resp.raise_for_status()
        result = resp.json()
        return result['result']['response'].strip()
    except Exception as e:
        print(f"✗ Cloudflare AI error: {e}")
        return None

def scrape_news_items(max_items=MAX_NEWS_ITEMS):
    """Scrape news headlines + snippets from BPC website"""
    try:
        response = requests.get(TARGET_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        items = []
        
        # Strategy 1: Look for article containers with titles
        articles = soup.find_all('article') or soup.find_all('div', class_=lambda c: c and 'news' in c.lower())
        for article in articles:
            title = article.find(['h2', 'h3', 'h4', 'a'], class_=lambda c: c and any(x in c.lower() for x in ['title', 'heading', 'news']))
            if title:
                text = title.get_text().strip()
                # Get snippet if available
                snippet = article.find('p')
                if snippet:
                    text += f" – {snippet.get_text().strip()}"
                if text and len(text) > 30:
                    items.append(text)
                    if len(items) >= max_items:
                        break
        
        # Strategy 2: Fallback to generic headline search
        if len(items) < max_items:
            selectors = [
                ('h2', None), ('h3', None), ('h4', None),
                ('a', 'news-item'), ('div', 'article-title'),
                ('h2', 'title'), ('h3', 'title'), ('a', lambda c: c and 'news' in c.lower())
            ]
            for tag_name, class_filter in selectors:
                if len(items) >= max_items:
                    break
                if callable(class_filter):
                    found = soup.find_all(tag_name, class_=class_filter)
                elif class_filter:
                    found = soup.find_all(tag_name, class_=class_filter)
                else:
                    found = soup.find_all(tag_name)
                for el in found:
                    text = el.get_text().strip()
                    if text and 30 < len(text) < 300 and text not in items:
                        items.append(text)
                        if len(items) >= max_items:
                            break
        
        # Strategy 3: Last resort – grab paragraphs with news-like content
        if len(items) < max_items:
            for p in soup.find_all('p'):
                text = p.get_text().strip()
                if text and len(text) > 50 and len(text) < 400 and text not in items:
                    # Skip if it looks like footer/nav text
                    if any(skip in text.lower() for skip in ['copyright', 'subscribe', 'privacy', 'contact us']):
                        continue
                    items.append(text)
                    if len(items) >= max_items:
                        break
        
        if items:
            # Number the items for AI context
            return "\n\n".join([f"{i+1}. {item}" for i, item in enumerate(items[:max_items])])
        else:
            return "No news items could be extracted. The website structure may have changed. Please check manually."
            
    except Exception as e:
        return f"Error scraping website: {type(e).__name__}: {e}"

def main():
    print("🔍 Starting Victorian Building Reform Monitor...")
    
    # Step 1: Scrape content
    print(f"📰 Scraping up to {MAX_NEWS_ITEMS} news items...")
    raw_content = scrape_news_items()
    
    # Step 2: Get AI summary
    print("🤖 Generating AI summary...")
    summary = call_cloudflare_ai(raw_content)
    
    # Step 3: Format final message
    if not summary:
        # Fallback: show raw items if AI fails
        preview = raw_content[:600].replace("\n", "\n• ")
        summary = f"⚠️ AI summary unavailable. Latest headlines:\n• {preview}...\n\n🔗 Visit source for details."
    
    final_message = f"🏗️ <b>Victoria Building Reform Digest</b>\n📅 {time.strftime('%d %b %Y')}\n📰 Top {MAX_NEWS_ITEMS} items reviewed\n\n{summary}\n\n🔗 Source: {TARGET_URL}"
    
    # Step 4: Send to Telegram
    print("📱 Sending to Telegram...")
    if send_telegram(final_message):
        print("✅ Done! Check your Telegram.")
    else:
        print("❌ Failed to send Telegram message")

if __name__ == "__main__":
    main()
