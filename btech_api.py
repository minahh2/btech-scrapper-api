import json
import asyncio
from flask import Flask, request, jsonify
from crawl4ai import (
    AsyncWebCrawler,
    CrawlerRunConfig,
    JsonCssExtractionStrategy,
    BrowserConfig,
    CacheMode
)
from bs4 import BeautifulSoup
import re

app = Flask(__name__)

browser_config = BrowserConfig(
    viewport_width=1920,
    viewport_height=1080,
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    user_agent_mode="random",
    headless=True,
    extra_args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
)

# 1. THE NATIVE CLICKER (Bypasses React isTrusted blocker)
async def btech_native_click(page, *args, **kwargs):
    print("⏳ [HOOK] Attempting Native Hardware Click...")
    try:
        await page.wait_for_timeout(2000)
        
        selectors = [
            'text="Compare the best offers from other sellers"',
            'text="Select from other sellers"'
        ]
        
        for sel in selectors:
            btn = page.locator(sel).first
            if await btn.count() > 0:
                print("🎯 [HOOK] Button found! Sending OS-level click...")
                await btn.scroll_into_view_if_needed()
                await page.wait_for_timeout(500)
                
                await btn.click(force=True)
                
                print("⏳ [HOOK] Waiting 4 seconds for sidebar to load...")
                await page.wait_for_timeout(4000)
                break
    except Exception as e:
        print(f"❌ [HOOK] Click failed: {e}")

@app.route('/scrape_btech', methods=['POST'])
def scrape():
    data = request.get_json()
    if not data: return jsonify({"error": "No payload"}), 400
         
    urls = data.get("urls")
    schema = data.get("schema")

    extraction_strategy = JsonCssExtractionStrategy(schema, verbose=False)
    
    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        extraction_strategy=extraction_strategy,
        scan_full_page=True,
        scroll_delay=0.3,
        simulate_user=True,
        page_timeout=60000,
        excluded_tags=['nav', 'footer', 'header', 'script', 'style', 'noscript']
    )

    async def run_scraper():
        async with AsyncWebCrawler(config=browser_config, verbose=False) as crawler:
            crawler.crawler_strategy.set_hook("after_goto", btech_native_click)
            
            results = await crawler.arun_many(urls=urls, config=config)
            
            output = []
            for result in results:
                if result.success:
                    try:
                        extracted = json.loads(result.extracted_content)
                    except:
                        extracted = {}
                    
                    # 2. PYTHON SURGICAL EXTRACTION
                    soup = BeautifulSoup(result.html, 'html.parser')
                    sidebar_headers = soup.find_all(string=re.compile("Select from other sellers|Compare the best offers from other sellers"))
                    
                    offers = []
                    if sidebar_headers:
                        sidebar = sidebar_headers[-1].parent.parent.parent.parent
                        sold_by_elements = sidebar.find_all(string=re.compile("Sold by"))
                        
                        for el in sold_by_elements:
                            parent = el.parent
                            if not parent: continue
                            
                            seller_name = ""
                            spans = parent.find_all('span')
                            if len(spans) >= 2:
                                seller_name = spans[1].text.strip()
                            else:
                                seller_name = parent.text.replace('Sold by', '').strip()
                                
                            if not seller_name or 'EGP' in seller_name or 'LE' in seller_name:
                                continue
                                
                            price = ""
                            warranty = ""
                            
                            container = parent.parent
                            for _ in range(5):
                                if not container: break
                                
                                if not price:
                                    currency_tags = container.find_all(string=re.compile("^(LE|EGP)$"))
                                    if currency_tags:
                                        prev = currency_tags[0].parent.find_previous_sibling()
                                        if prev: price = prev.text.strip()
                                
                                if not warranty:
                                    w_tags = container.find_all(string=re.compile("warranty", re.IGNORECASE))
                                    if w_tags: 
                                        warranty = w_tags[0].text.strip()
                                        
                                if price: break
                                container = container.parent
                                
                            if seller_name and price:
                                offers.append({
                                    "seller_name": seller_name, 
                                    "price": price, 
                                    "warranty": warranty.replace("Warranty", "").strip() if warranty else ""
                                })
                    
                    unique_offers = list({ (o['seller_name'], o['price']): o for o in offers }.values())
                    
                    # --- 3. THE FIX FOR YOUR 500 ERROR ---
                    # We check if your schema returned a List or a Dict, and inject safely.
                    if isinstance(extracted, list):
                        if len(extracted) > 0:
                            extracted[0]["other_offers"] = unique_offers
                        else:
                            extracted.append({"other_offers": unique_offers})
                    elif isinstance(extracted, dict):
                        extracted["other_offers"] = unique_offers
                    else:
                        extracted = {"other_offers": unique_offers}
                    
                    output.append({
                        "url": result.url,
                        "status": result.status_code,
                        "data": extracted
                    })
                else:
                    output.append({"url": result.url, "error": result.error_message})
            return output

    try:
        return jsonify(asyncio.run(run_scraper()))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    from waitress import serve
    print("🚀 Starting B.TECH Native production server...")
    serve(app, host='0.0.0.0', port=5002, threads=2)
