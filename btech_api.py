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
    wait_condition_js = """js:() => {
        if (document.getElementById('extracted_offers_json')) return true;
        if (window._isScrapingOffers) return false;
        window._isScrapingOffers = true;
        
        (async () => {
            const uniqueOffers = [];
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
                    await delay(1000); // Give panel time to open
                }
                
                let attempts = 0;
                let previousCount = 0;
                let stableMatches = 0;
                
                // LOOP SAFETY: Max 100 attempts (approx 15 seconds)
                while (attempts < 100) { 
                     const tempOffers = [];
                     
                     // ✨ SURGICAL EXTRACTION ✨
                     const cards = document.querySelectorAll('[data-slot="card"], [data-slot="expandable-card"]');
                     
                     cards.forEach(card => {
                         let sellerName = "";
                         let price = "";
                         let warranty = "";
                         
                         const pTags = card.querySelectorAll('p');
                         const soldByP = Array.from(pTags).find(p => (p.textContent || "").includes('Sold by'));
                         if (soldByP) {
                             const spans = soldByP.querySelectorAll('span');
                             if (spans.length >= 2) sellerName = spans[1].textContent.trim();
                             else sellerName = soldByP.textContent.replace('Sold by', '').trim();
                         }
                         
                         const priceSpans = card.querySelectorAll('span');
                         const currencySpan = Array.from(priceSpans).find(s => {
                             const t = s.textContent.trim();
                             return t === 'LE' || t === 'EGP';
                         });
                         
                         if (currencySpan && currencySpan.previousElementSibling) {
                             price = currencySpan.previousElementSibling.textContent.trim();
                         }
                         
                         const wSpan = Array.from(priceSpans).find(s => (s.textContent || "").toLowerCase().includes('warranty'));
                         if (wSpan) warranty = wSpan.textContent.trim();
                         
                         if (sellerName && price) {
                             tempOffers.push({ seller_name: sellerName, price: price, warranty: warranty });
                         }
                     });

                     // Deduplicate
                     const seen = new Set();
                     const cleanOffers = [];
                     tempOffers.forEach(o => {
                         const key = o.seller_name + o.price;
                         if (!seen.has(key)) {
                             seen.add(key);
                             cleanOffers.push(o);
                         }
                     });
                     
                     // DYNAMIC RELEASE LOGIC (Fixes the 44-second timeout)
                     if (cleanOffers.length > 0) {
                         if (cleanOffers.length === previousCount) {
                             stableMatches++;
                             // If the array hasn't changed in 5 loops (~750ms), assume it's fully loaded and exit!
                             if (stableMatches >= 5) {
                                 uniqueOffers.push(...cleanOffers);
                                 break;
                             }
                         } else {
                             stableMatches = 0;
                             previousCount = cleanOffers.length;
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
                resultDiv.textContent = JSON.stringify(uniqueOffers || []);
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
