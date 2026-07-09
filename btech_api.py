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
    user_agent_mode="random"
)

@app.route('/scrape_btech', methods=['POST'])
def scrape():
    data = request.get_json()
    
    if not data:
         return jsonify({"error": "No JSON payload received"}), 400
         
    urls = data.get("urls")
    schema = data.get("schema")

    if not isinstance(urls, list) or not isinstance(schema, dict):
        return jsonify({"error": "Invalid input"}), 400

    extraction_strategy = JsonCssExtractionStrategy(schema, verbose=True)
    
    # THE TROJAN HORSE: Your verified "Surgical" JS Script
    wait_condition_js = """js:() => {
        // 1. If the div exists, we are done! Unblock Python instantly.
        if (document.getElementById('extracted_offers_json')) return true;
        
        // 2. Prevent duplicate script launches
        if (window._isScrapingOffers) return false;
        window._isScrapingOffers = true;
        
        // 3. Launch the Surgical Extractor in the background
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
                    await delay(500);
                }
                
                let expectedCount = 1; 
                let waitCountAttempts = 0;
                let countSpan = null;
                
                while (!countSpan && waitCountAttempts < 50) { 
                     const spans = Array.from(document.querySelectorAll('span'));
                     countSpan = spans.find(s => s.textContent.toLowerCase().includes('sellers') && s.textContent.match(/(\d+)/));
                     if (countSpan) break;
                     await delay(100);
                     waitCountAttempts++;
                }
                
                if (countSpan) {
                    const match = countSpan.textContent.match(/(\d+)/);
                    if (match) expectedCount = parseInt(match[1]);
                }

                let attempts = 0;
                let stableMatches = 0;
                
                while (attempts < 150) { 
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

                     const seen = new Set();
                     const cleanOffers = [];
                     tempOffers.forEach(o => {
                         const key = o.seller_name + o.price;
                         if (!seen.has(key)) {
                             seen.add(key);
                             cleanOffers.push(o);
                         }
                     });
                     
                     if (cleanOffers.length >= expectedCount && expectedCount > 0) {
                         stableMatches++;
                         if (stableMatches > 3) {
                             uniqueOffers.push(...cleanOffers);
                             break;
                         }
                     } else {
                         stableMatches = 0;
                     }
                     
                     await delay(150);
                     attempts++;
                }
                
            } catch (error) {
                console.error("Error in JS execution:", error);
            } finally {
                // Return the perfect array back to Python via the DOM
                const resultDiv = document.createElement('div');
                resultDiv.id = 'extracted_offers_json';
                resultDiv.textContent = JSON.stringify(uniqueOffers || []);
                document.body.appendChild(resultDiv);
            }
        })();
        
        return false; // Tells Python "Wait until the div exists!"
    }"""

    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        extraction_strategy=extraction_strategy,
        scan_full_page=True,      
        scroll_delay=0.3,
        simulate_user=True,
        wait_for=wait_condition_js, # The Trojan Horse is loaded
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
    print("🚀 Starting B.TECH production server with Waitress...")
    serve(app, host='0.0.0.0', port=5002, threads=2)
