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

# Global browser config
browser_config = BrowserConfig(
    viewport_width=1920,
    viewport_height=1080,
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    user_agent_mode="random",
    #text_mode=True,
    #light_mode=True,
    #extra_args=["--no-sandbox", "--disable-gpu", "--disable-extensions"]
)

@app.route('/scrape_btech3', methods=['POST'])
def scrape():
    data = request.get_json()
    urls = data.get("urls")
    schema = data.get("schema")
   

    if not isinstance(urls, list) or not isinstance(schema, dict):
        return jsonify({"error": "Invalid input"}), 400

    extraction_strategy = JsonCssExtractionStrategy(schema, verbose=True)
    js_code = """
    (async () => {
        console.log("Starting JS code with User Strategy...");
        const selector = '.flex.justify-between.w-full.items-center.gap-2xsmall.text-absoluteDark.font-semibold.text-xsmall';
        
        // Helper to wait
        const delay = ms => new Promise(res => setTimeout(res, ms));
        
        // 1. Wait for element to exist
        console.log("Waiting for element...");
        let el = document.querySelector(selector);
        let attempts = 0;
        while (!el && attempts < 50) { // Wait up to 5 seconds
            await delay(100);
            el = document.querySelector(selector);
            attempts++;
        }
        
        if (!el) {
            console.log("Element not found after waiting.");
            return;
        }
        
        // 2. Wait for text content to load (User observation)
        console.log("Waiting for text content...");
        attempts = 0;
        while (attempts < 50) {
            const text = el.textContent || "";
            if (text.includes("Offers starting from") || text.includes("starting from")) {
                console.log("Found expected text:", text);
                break;
            }
            await delay(100);
            attempts++;
        }
        
        // 3. Click
        console.log("Scrolling to element...");
        el.scrollIntoView({behavior: "smooth", block: "center"});
        await delay(1000);
        
        console.log("Clicking element...");
        el.click();
        
        // 4. Wait for sidebar (Count-based Smart Wait)
        console.log("Waiting for sidebar content...");
        
        // Try to find expected count from "X sellers" text
        let expectedCount = 1;
        // Selector for "X offers" or "X sellers" text
        const countSpan = Array.from(document.querySelectorAll('span')).find(s => s.textContent.includes('sellers') || s.textContent.includes('offers'));
        if (countSpan) {
            const match = countSpan.textContent.match(/(\d+)/);
            if (match) {
                expectedCount = parseInt(match[1]);
                // If expected count is high, we might count the main one too, so expect at least that many
                console.log(`Expecting at least ${expectedCount} sellers based on text '${countSpan.textContent}'.`);
            }
        }
        
        attempts = 0;
        let stableCount = 0;
        let lastCount = 0;
        
        while (attempts < 100) { // Wait up to 10s max (polling)
             const sellerPars = Array.from(document.querySelectorAll('p')).filter(p => p.textContent.includes('Sold by'));
             const currentCount = sellerPars.length;
             
             // We want at least 2 distinct prices or sellers to ensure sidebar is loaded
             // AND ideally match expected count
             if (currentCount >= expectedCount || currentCount > 1) {
                 if (currentCount === lastCount) {
                     stableCount++;
                 } else {
                     stableCount = 0;
                 }
             }
             
             // If we match expected OR we have >1 and it's stable for 500ms
             if ((currentCount >= expectedCount && stableCount > 3) || stableCount > 8) {
                 console.log(`Sidebar loaded. Found ${currentCount} sellers. Stable for ${stableCount*100}ms.`);
                 break;
             }
             
             lastCount = currentCount;
             await delay(100);
             attempts++;
        }
        
        // Give a tiny buffer for layout to settle
        await delay(500);
        
        // 5. Extract offers (Verified Logic)
        const offers = [];
        // Use a broader search for "Sold by" to capture sidebar items
        const sellerPars = Array.from(document.querySelectorAll('p')).filter(p => p.textContent.includes('Sold by'));
        
        sellerPars.forEach(sellerP => {
            let container = sellerP.parentElement;
            let priceEl = null;
            let warrantyEl = null;
            
            for (let i = 0; i < 5; i++) {
                if (!container) break;
                const spans = Array.from(container.querySelectorAll('span'));
                const foundPrice = spans.find(s => s.textContent.includes(',') && !s.textContent.includes('EGP'));
                if (foundPrice && container.textContent.includes('EGP')) {
                    priceEl = foundPrice;
                    warrantyEl = Array.from(container.querySelectorAll('p')).find(p => p.textContent.includes('Warranty'));
                    break;
                }
                container = container.parentElement;
            }
            
            if (priceEl) {
                let warrantyText = "";
                if (warrantyEl) {
                    warrantyText = warrantyEl.textContent.trim();
                    if (warrantyText.toLowerCase() === "warranty" || warrantyText.toLowerCase() === "warranty:") {
                        if (warrantyEl.nextElementSibling) {
                            warrantyText = warrantyEl.nextElementSibling.textContent.trim();
                        }
                    } else if (warrantyText.includes("Warranty:")) {
                        warrantyText = warrantyText.replace("Warranty:", "").trim();
                    }
                }
                
                offers.push({
                    price: priceEl.textContent.trim(),
                    seller_name: sellerP.textContent.trim().replace('Sold by', '').trim(),
                    warranty: warrantyText
                });
            }
        });
        
        // Deduplicate
        const uniqueOffers = [];
        const seen = new Set();
        offers.forEach(o => {
            const key = o.seller_name + o.price;
            if (!seen.has(key)) {
                seen.add(key);
                uniqueOffers.push(o);
            }
        });
        
        console.log(`Extracted ${uniqueOffers.length} offers`);
        
        // Inject into DOM
        const resultDiv = document.createElement('div');
        resultDiv.id = 'extracted_offers_json';
        resultDiv.textContent = JSON.stringify(uniqueOffers);
        document.body.appendChild(resultDiv);
        console.log("Injected extracted offers into DOM");
    })();
    """
    config = CrawlerRunConfig(
    cache_mode=CacheMode.BYPASS,
    extraction_strategy=extraction_strategy,
    js_code=js_code,
    scan_full_page=True,
    scroll_delay=0.3,
    #magic=True,
    delay_before_return_html=2.0,   
    simulate_user=True    
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

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(asyncio.wait_for(run_scraper(), timeout=60))
        return jsonify(result)
    except asyncio.TimeoutError:
        return jsonify({"error": "Scraping timed out"}), 504

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)
