import json
import asyncio
import re
from flask import Flask, request, jsonify
from crawl4ai import (
    AsyncWebCrawler,
    CrawlerRunConfig,
    BrowserConfig,
)
from bs4 import BeautifulSoup

app = Flask(__name__)

# Config: 1080p to ensure sidebars aren't hidden by responsive CSS
browser_config = BrowserConfig(
    viewport_width=1920,
    viewport_height=1080,
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    headless=True
)

async def btech_native_click(page, *args, **kwargs):
    print("⏳ [HOOK] Starting Sidebar Hunter...")
    # 1. Target the exact div you identified
    btn = page.locator('div[data-slot="card-header"]').first
    
    if await btn.count() > 0:
        print("🎯 [HOOK] Button found! Clicking...")
        await btn.scroll_into_view_if_needed()
        await btn.click(force=True)
        
        # 2. THE LOCK: Wait until the Sidebar Dialog exists
        print("⏳ [HOOK] Waiting for Sidebar Dialog to mount...")
        try:
            # Radix UI modals/dialogs ALWAYS have role="dialog"
            await page.wait_for_selector('[role="dialog"]', state="visible", timeout=10000)
            await page.wait_for_timeout(2000) # Give it 2s to populate data
            print("✅ [HOOK] Sidebar verified!")
        except Exception as e:
            print(f"❌ [HOOK] Sidebar failed to open: {e}")
    else:
        print("⚠️ [HOOK] Button not found, proceeding with main content.")

@app.route('/scrape_btech', methods=['POST'])
def scrape():
    data = request.get_json()
    url = data.get("urls")[0]
    
    config = CrawlerRunConfig(
        scan_full_page=True,
        simulate_user=True,
        page_timeout=60000
    )

    async def run_scraper():
        async with AsyncWebCrawler(config=browser_config) as crawler:
            crawler.crawler_strategy.set_hook("after_goto", btech_native_click)
            result = await crawler.arun(url=url, config=config)
            
            soup = BeautifulSoup(result.html, 'html.parser')
            
            # Look for the Dialog Sidebar first
            sidebar = soup.find(attrs={"role": "dialog"})
            if not sidebar:
                sidebar = soup
            
            offers = []
            # Find all seller blocks
            # We look for the paragraph containing the seller name
            sold_by_nodes = sidebar.find_all(string=re.compile("Sold by", re.IGNORECASE))
            
            for node in sold_by_nodes:
                parent = node.parent
                seller_name = parent.text.replace("Sold by", "").strip()
                
                # Cleanup common layout junk
                for junk in ["Other sellers", "Compare", "Delivery"]:
                    if junk in seller_name: seller_name = seller_name.split(junk)[0].strip()
                
                # Look for price in the sibling/parent containers
                price = ""
                card = parent.parent
                for _ in range(5):
                    if not card: break
                    match = re.search(r'([\d,.]+)\s*(?:LE|EGP)', card.text)
                    if match:
                        price = match.group(1)
                        break
                    card = card.parent
                    
                if seller_name and price:
                    offers.append({"seller_name": seller_name, "price": price})
            
            # Unique filter
            unique_offers = list({ (o['seller_name'], o['price']): o for o in offers }.values())
            
            return {
                "url": url,
                "found_count": len(unique_offers),
                "other_offers": unique_offers
            }

    try:
        data = asyncio.run(run_scraper())
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    from waitress import serve
    serve(app, host='0.0.0.0', port=5002)
