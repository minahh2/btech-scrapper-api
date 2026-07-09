import json
import asyncio
import re
from flask import Flask, request, jsonify
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from bs4 import BeautifulSoup

app = Flask(__name__)
browser_config = BrowserConfig(headless=True)

# THE ULTIMATE CLICKER
async def btech_native_click(page, *args, **kwargs):
    print("⏳ [HOOK] Starting...")
    await page.wait_for_timeout(3000)
    # Target the container precisely
    btn = page.locator('div[data-slot="card-header"]').first
    if await btn.count() > 0:
        await btn.click(force=True)
        # Force wait until the sidebar actually populates
        await page.wait_for_timeout(5000) 
        print("✅ Clicked and waited.")

@app.route('/scrape_btech', methods=['POST'])
def scrape():
    data = request.get_json()
    url = data.get("urls")[0]
    
    # We remove the hook for the diagnostic-style parser to ensure pure content retrieval
    config = CrawlerRunConfig(
        scan_full_page=True,
        simulate_user=True,
        page_timeout=60000
    )

    async def run_scraper():
        async with AsyncWebCrawler(config=browser_config) as crawler:
            crawler.crawler_strategy.set_hook("after_goto", btech_native_click)
            result = await crawler.arun(url=url, config=config)
            
            # Use BeautifulSoup to scan everything
            soup = BeautifulSoup(result.html, 'html.parser')
            
            # Find every single div, as the sidebar might be a nested portal
            divs = soup.find_all('div')
            results = []
            
            for div in divs:
                text = div.get_text(" ", strip=True)
                # Filter for blocks that look like a seller entry (contains "Sold by" and a price)
                if "Sold by" in text and any(x in text for x in ["EGP", "LE"]):
                    # Clean it up
                    seller = re.sub(r'Sold by\s+', '', text, flags=re.IGNORECASE)
                    results.append(seller)
            
            # Deduplicate
            final_sellers = list(set(results))
            
            return {
                "status": "Success",
                "sellers_found": final_sellers,
                "raw_text_check": "Sold by" in soup.get_text()
            }

    try:
        data = asyncio.run(run_scraper())
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    from waitress import serve
    serve(app, host='0.0.0.0', port=5002)
