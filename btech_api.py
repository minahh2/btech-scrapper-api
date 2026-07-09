import json
import asyncio
import re
from flask import Flask, request, jsonify
from crawl4ai import (
    AsyncWebCrawler,
    CrawlerRunConfig,
    JsonCssExtractionStrategy,
    BrowserConfig,
    CacheMode
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

async def btech_native_click(page, *args, **kwargs):
    await page.wait_for_timeout(3000) 
    # Force click on the container element that holds the text "Other sellers for this product"
    # Using a broad selector to ensure it hits
    locator = page.locator('div:has-text("Other sellers for this product")').first
    if await locator.count() > 0:
        await locator.click(force=True)
        await page.wait_for_timeout(4000) 

@app.route('/scrape_btech', methods=['POST'])
def scrape():
    data = request.get_json()
    urls = data.get("urls")
    schema = data.get("schema")

    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        scan_full_page=True,
        simulate_user=True,
        excluded_tags=['script', 'style', 'noscript'],
        page_timeout=60000
    )

    async def run_scraper():
        async with AsyncWebCrawler(config=browser_config) as crawler:
            crawler.crawler_strategy.set_hook("after_goto", btech_native_click)
            results = await crawler.arun_many(urls=urls, config=config)
            
            output = []
            for result in results:
                # DUMP RAW HTML FOR DEBUGGING
                soup = BeautifulSoup(result.html, 'html.parser')
                
                # Attempt to find "Sold by" anywhere
                all_text = soup.get_text(" ", strip=True)
                sold_by_presence = "Sold by" in all_text
                
                # If we can't find it, give us the HTML so we can debug
                raw_html_sample = soup.prettify()[:5000] if not sold_by_presence else "FOUND_SOLD_BY_TEXT"
                
                # Logic to scrape everything that looks like a seller card
                offers = []
                # Looking for divs that might contain seller info
                for div in soup.find_all('div'):
                    if "Sold by" in div.text and len(div.text) < 200:
                        offers.append(div.text.strip())
                
                output.append({
                    "url": result.url,
                    "debug_sold_by_detected": sold_by_presence,
                    "debug_raw_html_preview": raw_html_sample,
                    "debug_found_blocks": offers
                })
            return output

    try:
        return jsonify(asyncio.run(run_scraper()))
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    from waitress import serve
    serve(app, host='0.0.0.0', port=5002)
