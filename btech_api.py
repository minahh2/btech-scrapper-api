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
    user_agent_mode="random",
    headless=True,
    extra_args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
)

# 1. PURE PYTHON HOOK: Precision DOM Clicking
async def btech_native_click(page, *args, **kwargs):
    print("⏳ [HOOK] Hunting for B.TECH button using precise DOM structure...")
    await page.wait_for_timeout(2000) 
    
    # Target the exact parent div wrapper using your provided HTML snippet
    selectors = [
        'div[data-slot="card-header"]:has-text("Other sellers for this product")',
        'div[data-slot="card-header"]:has-text("Compare the best offers")',
        'div.flex.flex-row.items-center.w-full:has-text("Other sellers")'
    ]
    
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if await btn.count() > 0 and await btn.is_visible():
                print(f"🎯 [HOOK] Wrapper found! Scrolling to safe center zone...")
                await btn.evaluate("el => el.scrollIntoView({block: 'center', inline: 'center'})")
                await page.wait_for_timeout(1000) 
                
                print("🎯 [HOOK] Sending double-action click to the exact card header...")
                # Action 1: OS-Level Hardware Click
                await btn.click(force=True)
                # Action 2: Failsafe JS Dispatch (wakes up stubborn React listeners)
                await btn.evaluate("el => el.click()")
                
                print("⏳ [HOOK] Waiting 4 seconds for Sidebar animation and network fetch...")
                await page.wait_for_timeout(4000) 
                print("✅ [HOOK] Proceeding to extraction!")
                break
        except Exception as e:
            pass

@app.route('/scrape_btech', methods=['POST'])
def scrape():
    data = request.get_json()
    if not data: return jsonify({"error": "No payload detected"}), 400
         
    urls = data.get("urls")
    schema = data.get("schema")

    extraction_strategy = JsonCssExtractionStrategy(schema, verbose=False)
    
    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        extraction_strategy=extraction_strategy,
        scan_full_page=True,      
        scroll_delay=0.3,
        simulate_user=True,
        excluded_tags=['nav', 'footer', 'header', 'script', 'style', 'noscript'],
        page_timeout=60000        
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
                    
                    # 2. PURE PYTHON PARSER
                    soup = BeautifulSoup(result.html, 'html.parser')
                    offers = []
                    
                    # Search the entire soup since Headless mode might strip 'role="dialog"'
                    sold_by_nodes = soup.find_all(string=re.compile("Sold by", re.IGNORECASE))
                    
                    for text_node in sold_by_nodes:
                        parent = text_node.parent
                        if not parent: continue

                        # A. Get Seller Name
                        seller_name = parent.text.replace("Sold by", "").strip()
                        if not seller_name:
                            sib = parent.find_next_sibling()
                            if sib: seller_name = sib.text.strip()
                        
                        # Clean up sticky layout text
                        for delimiter in ["Other sellers", "Compare", "Delivery"]:
                            if delimiter in seller_name:
                                seller_name = seller_name.split(delimiter)[0].strip()
                        
                        # Ghost Killer
                        if not seller_name or 'EGP' in seller_name or 'LE' in seller_name or len(seller_name) > 40:
                            continue

                        # B. Get Price and Warranty
                        price = ""
                        warranty = ""
                        card = parent.parent
                        
                        for _ in range(7):
                            if not card: break
                            
                            if not price:
                                # Find EGP or LE
                                currency = card.find(string=re.compile("^(LE|EGP)$"))
                                if currency:
                                    prev = currency.parent.find_previous_sibling()
                                    if prev: price = prev.text.strip()
                                if not price:
                                    m = re.search(r'([\d,.]+)\s*(LE|EGP)', card.text)
                                    if m: price = m.group(1)
                                    
                            if not warranty:
                                w_node = card.find(string=re.compile("warranty", re.IGNORECASE))
                                if w_node:
                                    warranty = w_node.parent.text.lower().replace("warranty", "").strip()
                                    if warranty: warranty += " warranty"
                                    
                            if price: break
                            card = card.parent

                        if seller_name and price:
                            offers.append({
                                "seller_name": seller_name,
                                "price": price,
                                "warranty": warranty if warranty else "12 months warranty"
                            })
                    
                    # Deduplicate perfectly
                    unique_offers = list({ (o['seller_name'].lower(), o['price']): o for o in offers }.values())
                    
                    # Format output for n8n safely
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
    print("🚀 Starting B.TECH Pure-Python production server...")
    serve(app, host='0.0.0.0', port=5002, threads=2)
