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

browser_config = BrowserConfig(
    viewport_width=1920,
    viewport_height=1080,
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    headless=True,
    extra_args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
)

# 1. THE BLOCKING HOOK
async def btech_native_click(page, *args, **kwargs):
    print("⏳ [HOOK] Starting B.TECH Sidebar Hunter...")
    await page.wait_for_timeout(3000) 
    
    # Target the button
    btn = page.locator('div[data-slot="card-header"]:has-text("Other sellers for this product")').first
    
    if await btn.count() > 0:
        print("🎯 [HOOK] Button found, clicking...")
        await btn.click(force=True)
        
        # BLOCKING WAIT: Don't let the crawler run until we see multiple "Sold by" in the DOM
        print("⏳ [HOOK] Blocking crawler until sidebar content verifies...")
        try:
            # We wait until the DOM contains at least 3 "Sold by" strings
            # This forces the page to be fully loaded with the sidebar content before extraction
            await page.wait_for_function("""
                () => {
                    const text = document.body.innerText;
                    const count = (text.match(/Sold by/g) || []).length;
                    return count >= 3;
                }
            """, timeout=10000)
            print("✅ [HOOK] Sidebar verified and fully loaded!")
        except:
            print("⚠️ [HOOK] Timeout waiting for sidebar content. Proceeding anyway.")
    else:
        print("❌ [HOOK] Button not found, falling back to main page.")

@app.route('/scrape_btech', methods=['POST'])
def scrape():
    data = request.get_json()
    urls = data.get("urls")
    schema = data.get("schema")

    config = CrawlerRunConfig(
        scan_full_page=True,
        simulate_user=True,
        page_timeout=60000
    )

    async def run_scraper():
        async with AsyncWebCrawler(config=browser_config) as crawler:
            crawler.crawler_strategy.set_hook("after_goto", btech_native_click)
            results = await crawler.arun_many(urls=urls, config=config)
            
            output = []
            for result in results:
                soup = BeautifulSoup(result.html, 'html.parser')
                
                # DEBUGGING: List ALL "Sold by" findings for this run
                found_texts = [tag.text.strip() for tag in soup.find_all(string=re.compile("Sold by"))]
                
                # If we have more than 1 "Sold by", we are in the sidebar!
                offers = []
                # Use a broader search area
                search_area = soup.find(attrs={"role": "dialog"}) or soup
                
                sold_by_nodes = search_area.find_all(string=re.compile("Sold by", re.IGNORECASE))
                
                for node in sold_by_nodes:
                    parent = node.parent
                    seller_name = parent.text.replace("Sold by", "").strip()
                    if len(seller_name) > 30: continue # Cleanup junk
                    
                    # Logic to pull price from surrounding nodes
                    card = parent.parent
                    price = ""
                    # Search nearby for currency
                    for _ in range(5):
                        if not card: break
                        match = re.search(r'([\d,.]+)\s*(LE|EGP)', card.text)
                        if match: 
                            price = match.group(1)
                            break
                        card = card.parent
                    
                    if seller_name and price:
                        offers.append({"seller_name": seller_name, "price": price})

                unique_offers = list({ (o['seller_name'], o['price']): o for o in offers }.values())
                
                output.append({
                    "url": result.url,
                    "debug_total_found": len(found_texts),
                    "debug_all_strings": found_texts,
                    "other_offers": unique_offers
                })
            return output

    try:
        return jsonify(asyncio.run(run_scraper()))
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    from waitress import serve
    serve(app, host='0.0.0.0', port=5002)
