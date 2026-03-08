import os
import requests
from bs4 import BeautifulSoup
import time

# === CONFIGURATION (from GitHub Secrets) ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
CF_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")

# === TARGET: Victorian Building Authority News ===
# Update this URL if you find a better source or RSS feed
TARGET_URL = "https://www.vba.vic.gov.au/news-and-publications/news"
HEADERS = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)'}

def send_telegram(message):
    """Send a message to your Telegram chat"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        resp = requests.post(url, json=data, timeout=30)
        resp.raise_for_status()
        print("✓ Telegram message sent")
    except Exception as e:
        print(f"✗ Telegram error: {e}")

def call_cloudflare_ai(text):
    """Send text to Cloudflare Workers AI for summarization"""
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/meta/llama-3-8b-instruct"
    headers = {
        "Authorization": f"Bearer {CF_TOKEN}",
        "Content-Type": "application/json"
    }
    
    prompt = f"""You are a helpful assistant for property owners in Victoria, Australia. 
Review this text from the Victorian Building Authority website and summarize any new building reforms, regulation changes, or important updates. 
Focus on practical implications for homeowners or builders. If there are no relevant reforms, say "No new building reforms found today."

Text to review:
{text[:3500]}  # Truncate to avoid token limits

Output format: Use 3-5 bullet points with emojis. Keep it under 200 words."""

    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 500
    }
    
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        result = resp.json()
        return result['result']['response']
    except Exception as e:
        print(f"✗ Cloudflare AI error: {e}")
        return None

def scrape_vba_news():
    """Fetch and extract news items from VBA website"""
    try:
        response = requests.get(TARGET_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Try to find news items - adjust selectors based on actual site structure
        # This is a generic example; you may need to inspect the site to refine
        items = []
        
        # Look for common news patterns
        for tag in soup.find_all(['h2', 'h3', 'h4'], class_=lambda x: x and ('title' in x.lower() or 'news' in x.lower())):
            text = tag.get_text().strip()
            if text and len(text) > 20:
                items.append(text)
        
        # Fallback: get first few paragraphs if no headlines found
        if not items:
            for p in soup.find_all('p')[:5]:
                text = p.get_text().strip()
                if text and len(text) > 50:
                    items.append(text)
        
        return "\n\n".join(items[:5]) if items else "No news items could be extracted. The website structure may have changed."
        
    except Exception as e:
        return f"Error scraping website: {str(e)}"

def main():
    print("🔍 Starting Victorian Building Reform Monitor...")
    
    # Step 1: Scrape content
    print("📰 Scraping website...")
    raw_content = scrape_vba_news()
    
    # Step 2: Get AI summary
    print("🤖 Generating AI summary...")
    summary = call_cloudflare_ai(raw_content)
    
    if not summary:
        summary = "⚠️ Could not generate AI summary. Raw content:\n\n" + raw_content[:500]
    
    # Step 3: Format and send to Telegram
    final_message = f"🏗️ <b>Victorian Building Reform Update</b>\n📅 {time.strftime('%d %b %Y')}\n\n{summary}\n\n🔗 Source: {TARGET_URL}"
    
    print("📱 Sending to Telegram...")
    send_telegram(final_message)
    print("✅ Done!")

if __name__ == "__main__":
    main()
