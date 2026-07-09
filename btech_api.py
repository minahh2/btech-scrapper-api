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

app = Flask(__name__)

browser_config = BrowserConfig(
    viewport_width=1920,
    viewport_height=1080,
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    user_agent_mode="random",
    headless=True,
    extra_args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
)

@app.route('/scrape_btech', methods=['POST'])
def scrape():
    data = request.get_json()
    if not data: return jsonify({"error": "No JSON payload received"}), 400
         
    urls = data.get("urls")
    schema = data.get("schema")

    if not isinstance(urls, list) or not isinstance(schema, dict):
        return jsonify({"error": "Invalid input"}), 400

    extraction_strategy = JsonCssExtractionStrategy(schema, verbose=True)
    
    # THE TROJAN HORSE: Lazy-Load Resistant & 1-Seller Compatible
    wait_condition_js = """js:() => {
        if (document.getElementById('extracted_offers_json')) return true;
        if (window._isScrapingOffers) return false;
        window._isScrapingOffers = true;
        
        (async () => {
            const delay = ms => new Promise(res => setTimeout(res, ms));
            const uniqueOffers = [];
            let fallbackDebugHtml = "TIMEOUT_WAITING_FOR_BUTTON";
            
            try {
                let targetButton = null;
                
                // 1. POLL FOR THE BUTTON (Handles Lazy Loading)
                // We will check the DOM every 150ms for up to 9 seconds.
                for (let b = 0; b < 60; b++) { 
                    const allElements = Array.from(document.querySelectorAll('*'));
                    for (let i = allElements.length - 1; i >= 0; i--) {
                        const el = allElements[i];
                        if (el.textContent && el.textContent.includes("Compare the best offers") && el.children.length === 0) {
                             let parent = el.parentElement;
                             while (parent && parent !== document.body) {
                                 if (parent.tagName === 'BUTTON' || parent.getAttribute('role') === 'button' || parent.classList.contains('cursor-pointer') || (parent.tagName === 'DIV' && parent.className.includes('flex'))) {
                                     targetButton = parent;
                                     break;
                                 }
                                 parent = parent.parentElement;
                             }
                             if (targetButton) break;
                        }
                    }
                    
                    if (!targetButton) {
                         const candidates = Array.from(document.querySelectorAll('button, div[role="button"], .cursor-pointer'));
                         const specificButtons = candidates.filter(e => (e.textContent || "").includes("Compare the best offers"));
                         if (specificButtons.length > 0) targetButton = specificButtons[specificButtons.length - 1];
                    }
                    
                    if (targetButton) break; // Found it, stop waiting!
                    await delay(150); 
                }

                // If after 9 seconds there is STILL no button, assume it's a hard 0-seller product.
                if (!targetButton) {
                     const resultDiv = document.createElement('div');
                     resultDiv.id = 'extracted_offers_json';
                     resultDiv.textContent = JSON.stringify([]);
                     document.body.appendChild(resultDiv);
                     return;
                }

                // 2. CLICK THE LAZY-LOADED BUTTON
                targetButton.scrollIntoView({behavior: "smooth", block: "center"});
                await delay(1000); 
                targetButton.click();
                await delay(2000); // Give the panel time to animate and open
                
                // 3. ISOLATE SIDEBAR AND EXTRACT
                fallbackDebugHtml = "TIMEOUT_SIDEBAR_NEVER_OPENED";
                let attempts = 0;
                let previousCount = 0;
                let stableMatches = 0;
                
                while (attempts < 100) { 
                     const tempOffers = [];
                     
                     // Look for sidebar headers (Updated with 'All sellers' from your screenshot)
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
                         
                         // DYNAMIC EXIT (Works perfectly whether it finds 1 seller or 10 sellers)
                         if (cleanOffers.length > 0) {
                             if (cleanOffers.length === previousCount) {
                                 stableMatches++;
                                 if (stableMatches >= 4) { 
                                     uniqueOffers.push(...cleanOffers);
                                     break; 
                                 }
                             } else {
                                 stableMatches = 0;
                                 previousCount = cleanOffers.length;
                             }
                         }
                     } else {
                         if (attempts === 99) {
                             fallbackDebugHtml = document.body ? document.body.innerHTML.substring(0, 1500) : "NO_BODY";
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
                
                if (uniqueOffers.length === 0) {
                    resultDiv.textContent = JSON.stringify([{ "error": "No offers found", "debug_html": fallbackDebugHtml }]);
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
        scroll_delay=0.3,
        simulate_user=True,
        wait_for=wait_condition_js, 
        excluded_tags=['nav', 'footer', 'header', 'script', 'style', 'noscript'],
        exclude_external_links=True,
        exclude_social_media_links=True,
        exclude_external_images=True,
        page_timeout=60000        
    )

    async def run_scraper():
        async with AsyncWebCrawler(config=browser_config, verbose=True) as crawler:
            results = await crawler.arun_many(urls=urls, config=config)
            output = []
            for result in results:
                if result.success:
                    try:
                        extracted = json.loads(result.extracted_content)
                    except Exception:
                        extracted = {"error": "Failed to parse extracted content"}
                    output.append({
                        "url": result.url,
                        "status": result.status_code,
                        "data": extracted
                    })
                else:
                    output.append({
                        "url": result.url,
                        "status": result.status_code,
                        "error": result.error_message
                    })
            return output

    try:
        result = asyncio.run(run_scraper())
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    from waitress import serve
    print("🚀 Starting B.TECH production server...")
    serve(app, host='0.0.0.0', port=5002, threads=2)
