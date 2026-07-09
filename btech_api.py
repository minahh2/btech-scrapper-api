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

# 1. UPGRADED MULTI-STRATEGY CLICKER HOOK
async def btech_native_click(page, *args, **kwargs):
    print("⏳ [HOOK] Initializing interactive actions...")
    await page.wait_for_timeout(3000) # Let React component mounting settle
    
    selectors = [
        'text="Compare the best offers from other sellers"',
        'text="Select from other sellers"',
        'button:has-text("offers")',
        'div:has-text("Compare the best offers")'
    ]
    
    clicked = False
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if await btn.count() > 0 and await btn.is_visible():
                print(f"🎯 [HOOK] Match found via: {sel}. Triggering OS-level click...")
                await btn.scroll_into_view_if_needed()
                await page.wait_for_timeout(500)
                await btn.click(force=True)
                clicked = True
                print("⚡ [HOOK] Click sequence executed. Holding for animation...")
                await page.wait_for_timeout(5000)
                break
        except Exception as e:
            print(f"⚠️ [HOOK] Selector skip: {sel} ({e})")
            
    if not clicked:
        print("🔍 [HOOK] Standard click skipped. Deploying window fallback event...")
        try:
            await page.evaluate("""() => {
                const elements = Array.from(document.querySelectorAll('button, div, span, p'));
                const target = elements.find(e => e.textContent && e.textContent.includes('Compare the best offers'));
                if (target) { target.click(); return true; }
                return false;
            }""")
            await page.wait_for_timeout(4000)
        except Exception as e:
            print(f"❌ [HOOK] Secondary trigger failed: {e}")

@app.route('/scrape_btech', methods=['POST'])
def scrape():
    data = request.get_json()
    if not data: return jsonify({"error": "No payload payload detected"}), 400
         
    urls = data.get("urls")
    schema = data.get("schema")

    extraction_strategy = JsonCssExtractionStrategy(schema, verbose=False)
    
    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        extraction_strategy=extraction_strategy,
        scan_full_page=True,
        scroll_delay=0.4,
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
                    
                    # 2. BULLETPROOF REGEX PARSING ENGINE
                    soup = BeautifulSoup(result.html, 'html.parser')
                    offers = []
                    
                    # Scan visual text containers across the layout
                    for tag in soup.find_all(['span', 'p', 'div', 'td']):
                        raw_text = tag.get_text(" ", strip=True)
                        
                        if "Sold by" in raw_text and len(raw_text) < 300:
                            # Safely extract merchant strings using regex boundaries
                            name_match = re.search(r'Sold\s*by\s*([^0-9\nLE|EGP,$]+)', raw_text, re.IGNORECASE)
                            seller_name = name_match.group(1).strip() if name_match else raw_text.replace("Sold by", "").strip()
                            
                            # Clean up trailing layout clutter from smashed tags
                            for delimiter in ["Other sellers", "Compare", "Delivery", "Store"]:
                                if delimiter in seller_name:
                                    seller_name = seller_name.split(delimiter)[0].strip()
                            
                            price = ""
                            warranty = ""
                            
                            # Trace up the DOM lineage locally to isolate matching prices/warranties
                            tracker = tag
                            for _ in range(5):
                                if not tracker: break
                                lineage_text = tracker.get_text(" ", strip=True)
                                
                                if not price:
                                    price_match = re.search(r'([\d,]+)\s*(?:EGP|LE)', lineage_text)
                                    if price_match:
                                        price = price_match.group(1)
                                
                                if not warranty:
                                    warranty_match = re.search(r'(\d+)\s*(?:month|year)s?\s*warranty', lineage_text, re.IGNORECASE)
                                    if warranty_match:
                                        warranty = warranty_match.group(1) + " months warranty"
                                
                                if price and warranty: break
                                tracker = tracker.parent
                            
                            if seller_name and price and len(seller_name) < 60:
                                offers.append({
                                    "seller_name": seller_name,
                                    "price": price,
                                    "warranty": warranty if warranty else "12 months warranty"
                                })
                    
                    # 3. ATOMIC DE-DUPLICATION
                    unique_offers = list({ (o['seller_name'].lower(), o['price']): o for o in offers }.values())
                    
                    # Structuring response schema output safely
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
