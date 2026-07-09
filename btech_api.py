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

async def btech_native_click(page, *args, **kwargs):
    print("⏳ [HOOK] Initializing interactive actions...")
    await page.wait_for_timeout(3000) 
    
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
                await page.wait_for_timeout(4000) # Wait 4s for network fetch
                break
        except Exception as e:
            pass
            
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
    
    # THE TROJAN HORSE: Target Lock & Patience update
    wait_condition_js = """js:() => {
        if (document.getElementById('extracted_offers_json')) return true;
        if (window._isScrapingOffers) return false;
        window._isScrapingOffers = true;
        
        (async () => {
            const delay = ms => new Promise(res => setTimeout(res, ms));
            const uniqueOffers = [];
            let fallbackDebugHtml = "TIMEOUT";
            
            try {
                let attempts = 0;
                let previousCount = 0;
                let stableMatches = 0;
                let expectedCount = 0; // Target Lock
                
                while (attempts < 120) { // Up to 18 seconds total
                     const tempOffers = [];
                     
                     // 1. ISOLATE SIDEBAR
                     const headers = Array.from(document.querySelectorAll('span, h2, h3, h4, p, div')).filter(e => {
                         const t = e.textContent.trim();
                         return t.includes("Select from other sellers") || 
                                t === "Compare the best offers from other sellers" || 
                                t === "All sellers";
                     });
                     
                     let searchArea = null;
                     if (headers.length > 0) {
                         headers.sort((a, b) => {
                             let depthA = 0, depthB = 0;
                             let pA = a, pB = b;
                             while(pA) { depthA++; pA = pA.parentElement; }
                             while(pB) { depthB++; pB = pB.parentElement; }
                             return depthB - depthA; 
                         });
                         let parent = headers[0].parentElement;
                         for(let i = 0; i < 4; i++) { if(parent && parent.parentElement) parent = parent.parentElement; }
                         searchArea = parent;
                     }
                     
                     if (searchArea) {
                         // Attempt to find the target count (e.g. "5 sellers")
                         if (expectedCount === 0) {
                             const spans = Array.from(searchArea.querySelectorAll('span'));
                             const countSpan = spans.find(s => s.textContent.toLowerCase().includes('sellers') && s.textContent.match(/(\d+)/));
                             if (countSpan) {
                                 const match = countSpan.textContent.match(/(\d+)/);
                                 if (match) expectedCount = parseInt(match[1]);
                             }
                         }

                         const allSoldBy = Array.from(searchArea.querySelectorAll('p, div, span')).filter(el => (el.textContent || "").includes('Sold by'));
                         
                         const deepestSoldBy = allSoldBy.filter(el => {
                             return !Array.from(el.children).some(child => (child.textContent || "").includes('Sold by'));
                         });
                         
                         deepestSoldBy.forEach(sellerEl => {
                             let sellerName = sellerEl.textContent.replace('Sold by', '').trim();
                             if (!sellerName) return;
                             
                             let price = "";
                             let warranty = "";
                             
                             let container = sellerEl.parentElement;
                             for (let i = 0; i < 7; i++) {
                                 if (!container) break;
                                 
                                 if (!price) {
                                     const spans = Array.from(container.querySelectorAll('span, p, div'));
                                     const curSpan = spans.find(s => s.textContent.trim() === 'LE' || s.textContent.trim() === 'EGP');
                                     if (curSpan && curSpan.previousElementSibling) {
                                         price = curSpan.previousElementSibling.textContent.trim();
                                     } else {
                                         const tMatch = (container.textContent || "").match(/([\d,.]+)\s*(LE|EGP)/);
                                         if (tMatch) price = tMatch[1];
                                     }
                                 }
                                 
                                 if (!warranty) {
                                     const spans = Array.from(container.querySelectorAll('span, p, div'));
                                     const wSpan = spans.find(s => (s.textContent || "").toLowerCase().includes('warranty'));
                                     if (wSpan) {
                                         warranty = wSpan.textContent.replace(/warranty/ig, '').trim();
                                         if (warranty) warranty = warranty + " warranty"; 
                                     }
                                 }
                                 
                                 if (price) break; 
                                 container = container.parentElement;
                             }
                             
                             if (sellerName && price) {
                                 tempOffers.push({ seller_name: sellerName, price: price, warranty: warranty });
                             }
                         });

                         const seen = new Set();
                         const cleanOffers = [];
                         tempOffers.forEach(o => {
                             const key = o.seller_name + o.price;
                             if (!seen.has(key)) {
                                 seen.add(key);
                                 cleanOffers.push(o);
                             }
                         });
                         
                         // DYNAMIC EXIT LOGIC (PATIENT MODE)
                         if (cleanOffers.length > 0) {
                             if (expectedCount > 0 && cleanOffers.length >= expectedCount) {
                                 // We hit the target number! Wait just a split second to ensure text is fully rendered, then exit.
                                 stableMatches++;
                                 if (stableMatches >= 2) {
                                     uniqueOffers.push(...cleanOffers);
                                     break;
                                 }
                             } else if (cleanOffers.length === previousCount) {
                                 // We don't have the target number yet, so we wait patiently.
                                 stableMatches++;
                                 if (stableMatches >= 18) { // Wait 2.7 seconds (18 loops * 150ms) before giving up!
                                     uniqueOffers.push(...cleanOffers);
                                     break; 
                                 }
                             } else {
                                 // A new seller just loaded! Reset the timer.
                                 stableMatches = 0;
                                 previousCount = cleanOffers.length;
                             }
                         }
                     }
                     
                     await delay(150);
                     attempts++;
                }
                
            } catch (error) {
                console.error("Error in JS execution:", error);
            } finally {
                const resultDiv = document.createElement('div');
                resultDiv.id = 'extracted_offers_json';
                resultDiv.textContent = JSON.stringify(uniqueOffers);
                document.body.appendChild(resultDiv);
            }
        })();
        
        return false;
    }"""

    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        extraction_strategy=extraction_strategy,
        scan_full_page=True,      
        scroll_delay=0.4,
        simulate_user=True,
        wait_for=wait_condition_js, 
        excluded_tags=['nav', 'footer', 'header', 'script', 'style', 'noscript'],
        exclude_external_links=True,
        exclude_social_media_links=True,
        exclude_external_images=True,
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
                    
                    # 2. BULLETPROOF REGEX PARSING ENGINE FOR MAIN PAGE FALLBACK
                    soup = BeautifulSoup(result.html, 'html.parser')
                    offers = []
                    
                    for tag in soup.find_all(['span', 'p', 'div', 'td']):
                        raw_text = tag.get_text(" ", strip=True)
                        
                        if "Sold by" in raw_text and len(raw_text) < 300:
                            name_match = re.search(r'Sold\s*by\s*([^0-9\nLE|EGP,$]+)', raw_text, re.IGNORECASE)
                            seller_name = name_match.group(1).strip() if name_match else raw_text.replace("Sold by", "").strip()
                            
                            for delimiter in ["Other sellers", "Compare", "Delivery", "Store"]:
                                if delimiter in seller_name:
                                    seller_name = seller_name.split(delimiter)[0].strip()
                            
                            price = ""
                            warranty = ""
                            
                            tracker = tag
                            for _ in range(5):
                                if not tracker: break
                                lineage_text = tracker.get_text(" ", strip=True)
                                
                                if not price:
                                    price_match = re.search(r'([\d,]+)\s*(?:EGP|LE)', lineage_text)
                                    if price_match: price = price_match.group(1)
                                
                                if not warranty:
                                    warranty_match = re.search(r'(\d+)\s*(?:month|year)s?\s*warranty', lineage_text, re.IGNORECASE)
                                    if warranty_match: warranty = warranty_match.group(1) + " months warranty"
                                
                                if price and warranty: break
                                tracker = tracker.parent
                            
                            if seller_name and price and len(seller_name) < 60:
                                offers.append({
                                    "seller_name": seller_name,
                                    "price": price,
                                    "warranty": warranty if warranty else "12 months warranty"
                                })
                    
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
