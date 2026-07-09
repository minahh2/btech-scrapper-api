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

# 1. Clean Browser Config
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
    
    # THE TROJAN HORSE: Optimized for Headless Stability
    # THE TROJAN HORSE: Hybrid Isolation + Headless Failsafe
    # THE TROJAN HORSE: Final Polish (Ghost-Killer + Precision Warranty)
    wait_condition_js = """js:() => {
        if (document.getElementById('extracted_offers_json')) return true;
        if (window._isScrapingOffers) return false;
        window._isScrapingOffers = true;
        
        (async () => {
            const uniqueOffers = [];
            let fallbackDebugHtml = "NO_DATA";
            try {
                const bodyText = document.body.innerText || "";
                const HAS_OTHER_OFFERS = bodyText.includes("Offers starting from") || 
                                         bodyText.includes("Compare the best offers from other sellers") || 
                                         bodyText.includes("Select from other sellers");
                
                if (!HAS_OTHER_OFFERS) {
                     const resultDiv = document.createElement('div');
                     resultDiv.id = 'extracted_offers_json';
                     resultDiv.textContent = JSON.stringify([]);
                     document.body.appendChild(resultDiv);
                     return; 
                }
                
                const delay = ms => new Promise(res => setTimeout(res, ms));
                let targetButton = null;
                const allElements = Array.from(document.querySelectorAll('*'));
                 
                for (let i = allElements.length - 1; i >= 0; i--) {
                    const el = allElements[i];
                    if (el.textContent && el.textContent.includes("Compare the best offers from other sellers") && el.children.length === 0) {
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
                
                let el = targetButton;
                if (!el) {
                     const candidates = Array.from(document.querySelectorAll('button, div[role="button"], .flex.justify-between, .cursor-pointer'));
                     const specificButtons = candidates.filter(e => (e.textContent || "").includes("Compare the best offers from other sellers"));
                     if (specificButtons.length > 0) el = specificButtons[specificButtons.length - 1];
                }

                if (el) {
                    el.scrollIntoView({behavior: "smooth", block: "center"});
                    await delay(1000); 
                    el.click();
                    await delay(2000); // Wait for React to open the panel
                }
                
                let attempts = 0;
                let previousCount = 0;
                let stableMatches = 0;
                
                while (attempts < 100) { 
                     const tempOffers = [];
                     
                     // 1. Find the sidebar header to isolate our search area
                     const headers = Array.from(document.querySelectorAll('span, h2, h3, h4, p, div')).filter(e => {
                         const t = e.textContent.trim();
                         return t === "Select from other sellers" || t === "Compare the best offers from other sellers";
                     });
                     
                     // Sort to get the deepest exact text match
                     headers.sort((a, b) => {
                         let depthA = 0, depthB = 0;
                         let pA = a, pB = b;
                         while(pA) { depthA++; pA = pA.parentElement; }
                         while(pB) { depthB++; pB = pB.parentElement; }
                         return depthB - depthA; 
                     });

                     let searchArea = document; 
                     if (headers.length > 0) {
                         let parent = headers[0].parentElement;
                         for(let i = 0; i < 4; i++) { if(parent && parent.parentElement) parent = parent.parentElement; }
                         if (parent) searchArea = parent;
                     }
                     
                     // 2. Find all "Sold by" elements inside our isolated area
                     const sellerPars = Array.from(searchArea.querySelectorAll('p, div')).filter(p => p.textContent.includes('Sold by') && p.children.length > 0);
                     const processedSellers = new Set();
                     
                     sellerPars.forEach(sellerP => {
                         let sellerName = "";
                         let price = "";
                         let warranty = "";
                         
                         // --- EXACT SELLER NAME EXTRACTION ---
                         const childSpans = Array.from(sellerP.querySelectorAll('span'));
                         const soldBySpan = childSpans.find(s => s.textContent.includes('Sold by'));
                         
                         if (soldBySpan && soldBySpan.nextElementSibling) {
                             sellerName = soldBySpan.nextElementSibling.textContent.trim();
                         } else if (childSpans.length >= 2) {
                             sellerName = childSpans[1].textContent.trim();
                         } else {
                             sellerName = sellerP.textContent.replace('Sold by', '').trim();
                         }
                         
                         // 🔥 KILL THE GHOST SELLER 🔥 (Ignore EGP/LE mistakes)
                         if (!sellerName || sellerName.includes('EGP') || sellerName.includes('LE')) return;
                         
                         // Prevent duplicates from nested divs
                         if (processedSellers.has(sellerName)) return; 
                         processedSellers.add(sellerName);

                         // --- EXACT PRICE & WARRANTY EXTRACTION ---
                         // B.TECH perfectly wraps price/warranty in the direct parent of the seller <p>
                         const cardContainer = sellerP.parentElement;
                         if (cardContainer) {
                             const allSpans = Array.from(cardContainer.querySelectorAll('span, p'));
                             
                             // Get Price (Look for LE or EGP, then grab the number before it)
                             const currencySpan = allSpans.find(s => s.textContent.trim() === 'LE' || s.textContent.trim() === 'EGP');
                             if (currencySpan && currencySpan.previousElementSibling) {
                                 price = currencySpan.previousElementSibling.textContent.trim();
                             } else {
                                 // Fallback if the DOM slightly shifted
                                 const pSpan = allSpans.find(s => /^\s*[\d,.]+\s*$/.test(s.textContent.trim()) && s.nextElementSibling && ['LE', 'EGP'].includes(s.nextElementSibling.textContent.trim()));
                                 if (pSpan) price = pSpan.textContent.trim();
                             }
                             
                             // Get Warranty
                             const wEl = allSpans.find(s => s.textContent.toLowerCase().includes('warranty'));
                             if (wEl) warranty = wEl.textContent.trim();
                         }
                         
                         if (sellerName && price) {
                             tempOffers.push({ seller_name: sellerName, price: price, warranty: warranty });
                         }
                     });

                     // Deduplicate array
                     const seen = new Set();
                     const cleanOffers = [];
                     tempOffers.forEach(o => {
                         const key = o.seller_name + o.price;
                         if (!seen.has(key)) {
                             seen.add(key);
                             cleanOffers.push(o);
                         }
                     });
                     
                     // Smart exit strategy
                     if (cleanOffers.length > 0) {
                         if (cleanOffers.length === previousCount) {
                             stableMatches++;
                             if (stableMatches >= 4) { // Found data, wait a beat to ensure it's stable, then exit!
                                 uniqueOffers.push(...cleanOffers);
                                 break;
                             }
                         } else {
                             stableMatches = 0;
                             previousCount = cleanOffers.length;
                         }
                     } else {
                         // IF FAILING: Grab the raw HTML of the headless sidebar so we can fix it!
                         if (attempts === 99) fallbackDebugHtml = searchArea.innerHTML.substring(0, 1000); 
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
