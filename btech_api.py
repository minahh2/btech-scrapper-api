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

# 1. THE MUSCLE: Python handles all clicking to bypass anti-bot
async def btech_native_click(page, *args, **kwargs):
    print("⏳ [HOOK] Python is hunting for the button...")
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
                print(f"🎯 [HOOK] Match found. Sending OS-level click...")
                await btn.scroll_into_view_if_needed()
                await page.wait_for_timeout(500)
                await btn.click(force=True)
                clicked = True
                print("⚡ [HOOK] Clicked! Yielding to JavaScript for extraction...")
                await page.wait_for_timeout(2000) # Give it 2 seconds to start animating
                break
        except Exception:
            pass
            
    if not clicked:
        print("⚠️ [HOOK] Native click failed. Relaying to fallback.")

@app.route('/scrape_btech', methods=['POST'])
def scrape():
    data = request.get_json()
    if not data: return jsonify({"error": "No payload detected"}), 400
         
    urls = data.get("urls")
    schema = data.get("schema")

    extraction_strategy = JsonCssExtractionStrategy(schema, verbose=False)
    
    # 2. THE BRAIN: JS ONLY observes the DOM and extracts. NO clicking (unless Python failed).
    wait_condition_js = """js:() => {
        if (document.getElementById('extracted_offers_json')) return true;
        if (window._isScrapingOffers) return false;
        window._isScrapingOffers = true;
        
        (async () => {
            const delay = ms => new Promise(res => setTimeout(res, ms));
            const uniqueOffers = [];
            let debugReason = "TIMEOUT_SIDEBAR_NEVER_OPENED";
            
            try {
                let attempts = 0;
                let previousCount = 0;
                let stableMatches = 0;
                let expectedCount = 0; 
                
                while (attempts < 120) { // 18 seconds max timeout
                     const tempOffers = [];
                     
                     // Isolate the sidebar
                     const headers = Array.from(document.querySelectorAll('span, h2, h3, h4, p, div')).filter(e => {
                         const t = e.textContent.trim();
                         return t.includes("Select from other sellers") || 
                                t === "Compare the best offers from other sellers" || 
                                t.includes("All sellers");
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
                     
                     // HAIL MARY: If Python missed the click, let JS try it once at second 6
                     if (!searchArea && attempts === 40) {
                         const btn = Array.from(document.querySelectorAll('button, div, span, p')).find(e => (e.textContent || "").includes("Compare the best offers"));
                         if (btn) {
                             btn.scrollIntoView({behavior: "smooth", block: "center"});
                             btn.click();
                         }
                     }
                     
                     if (searchArea) {
                         // Read the target number from the header
                         if (expectedCount === 0) {
                             const potentialElements = Array.from(searchArea.querySelectorAll('span, p, div, h2, h3, h4'));
                             for (let el of potentialElements) {
                                 const txt = el.textContent.trim();
                                 let match = txt.match(/(\d+)\s*(?:sellers|offers)/i) || txt.match(/(?:sellers|offers)\s*\(?(\d+)\)?/i);
                                 if (!match && (txt.toLowerCase().includes("sellers") || txt.toLowerCase().includes("offers"))) {
                                     match = txt.match(/(\d+)/);
                                 }
                                 if (match) {
                                     expectedCount = parseInt(match[1], 10);
                                     break;
                                 }
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
                         
                         // DYNAMIC EXIT LOGIC
                         if (cleanOffers.length > 0) {
                             if (expectedCount > 0) {
                                 if (cleanOffers.length >= expectedCount) {
                                     stableMatches++;
                                     if (stableMatches >= 2) {
                                         uniqueOffers.push(...cleanOffers);
                                         break;
                                     }
                                 } else {
                                     stableMatches = 0;
                                     previousCount = cleanOffers.length;
                                 }
                             } else {
                                 if (cleanOffers.length === previousCount) {
                                     stableMatches++;
                                     if (stableMatches >= 15) { 
                                         uniqueOffers.push(...cleanOffers);
                                         break; 
                                     }
                                 } else {
                                     stableMatches = 0;
                                     previousCount = cleanOffers.length;
                                 }
                             }
                         }
                     }
                     
                     // If we hit loop 119 (timeout), grab the HTML for debugging
                     if (attempts === 119) {
                         debugReason = document.body ? document.body.innerHTML.substring(0, 1500) : "BODY_UNAVAILABLE";
                     }
                     
                     await delay(150);
                     attempts++;
                }
                
            } catch (error) {
                console.error("Error in JS execution:", error);
                debugReason = error.toString();
            } finally {
                const resultDiv = document.createElement('div');
                resultDiv.id = 'extracted_offers_json';
                
                if (uniqueOffers.length === 0) {
                    resultDiv.textContent = JSON.stringify([{ "error": "No offers found", "debug_html": debugReason }]);
                } else {
                    resultDiv.textContent = JSON.stringify(uniqueOffers);
                }
                
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
                    
                    # Read the JSON that JS injected into the DOM
                    soup = BeautifulSoup(result.html, 'html.parser')
                    json_div = soup.find(id="extracted_offers_json")
                    
                    if json_div:
                        try:
                            unique_offers = json.loads(json_div.text)
                        except:
                            unique_offers = [{"error": "JSON Parse Failed"}]
                    else:
                        unique_offers = [{"error": "JS Script failed to inject div"}]
                    
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
