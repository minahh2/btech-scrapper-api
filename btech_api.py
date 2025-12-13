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

@app.route('/scrape_btech5', methods=['POST'])
def scrape():
    data = request.get_json()
    urls = data.get("urls")
    schema = data.get("schema")
   

    if not isinstance(urls, list) or not isinstance(schema, dict):
        return jsonify({"error": "Invalid input"}), 400

    extraction_strategy = JsonCssExtractionStrategy(schema, verbose=True)
    js_code = """
    (async () => {
        const uniqueOffers = [];
        try {
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
        
        // Try to find expected count from SPECIFIC selector provided by user
        let expectedCount = 1;
        const countSelector = "div.px-small.pt-small.flex.justify-between.items-center span.text-xsmall.font-medium.text-secondarySupportiveD3";
        const countSpan = document.querySelector(countSelector);
        
        if (countSpan) {
            console.log("DEBUG: Count Span found: ", countSpan.textContent);
            const match = countSpan.textContent.match(/(\d+)/);
            if (match) {
                expectedCount = parseInt(match[1]);
                console.log(`Expecting exactly ${expectedCount} sellers based on selector.`);
            }
        } else {
             // Fallback to broader search
             console.log("DEBUG: Specific count selector failed. Trying broader search...");
             const fallbackSpan = Array.from(document.querySelectorAll('span')).find(s => s.textContent.includes('sellers'));
             if (fallbackSpan) {
                 const match = fallbackSpan.textContent.match(/(\d+)/);
                 if (match) {
                     expectedCount = parseInt(match[1]);
                     console.log(`Expecting exactly ${expectedCount} sellers based on fallback text: "${fallbackSpan.textContent}"`);
                 }
             } else {
                 console.log("DEBUG: No 'sellers' count found. Defaulting to 1.");
             }
        }
        
        attempts = 0;
        let stableMatches = 0;
        
        while (attempts < 150) { // Wait up to 15s max (polling)
             // 5. Extract offers (Verified Logic)
             const tempOffers = [];
             // Use a broader search for "Sold by" to capture sidebar items
             const sellerPars = Array.from(document.querySelectorAll('p')).filter(p => p.textContent.includes('Sold by'));
            
             // We need to loop here to check extraction quality inside the wait loop
             sellerPars.forEach(sellerP => {
                let container = sellerP.parentElement;
                let priceEl = null;
                let warrantyEl = null;
                
                for (let i = 0; i < 5; i++) {
                    if (!container) break;
                    const spans = Array.from(container.querySelectorAll('span'));
                    
                    // STRICT PRICE CHECK: Regex for digits and commas only
                    const foundPrice = spans.find(s => {
                        const txt = s.textContent.trim();
                        // Allows "3,857" or "3857" or "3,857.00" - generally numbers, commas, dots
                        // User said remove "," then check if numerical.
                        // Regex: Start, optional whitespace, digits/commas/dots, optional whitespace, End.
                        return /^\s*[\d,.]+\s*$/.test(txt) && !txt.includes('EGP');
                    });
                    
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
                         // Warranty Logic (Verified)
                        const wTxt = warrantyEl.textContent.trim();
                        if (wTxt.toLowerCase() === "warranty" || wTxt.toLowerCase() === "warranty:") {
                            if (warrantyEl.nextElementSibling) {
                                warrantyText = warrantyEl.nextElementSibling.textContent.trim();
                            }
                        } else if (wTxt.includes("Warranty:")) {
                            warrantyText = wTxt.replace("Warranty:", "").trim();
                        } else {
                             warrantyText = wTxt; // Fallback
                        }
                    }
                    
                    const sName = sellerP.textContent.trim().replace('Sold by', '').trim();
                    const pText = priceEl.textContent.trim();
                    
                    // FINAL VALIDATION
                    if (sName.length > 0 && pText.length > 0) {
                         tempOffers.push({
                            price: pText,
                            seller_name: sName,
                            warranty: warrantyText
                        });
                    } else {
                        console.log(`Rejected offer: Price='${pText}', Seller='${sName}'`);
                    }
                } else {
                     // Log if price not found valid
                     // console.log("No valid price found for checking container.");
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
             
             // VALIDATE COUNT
             // If we found exactly what we expected (>1), we're good.
             // If expected is 1, we might just be seeing the main one. Wait a bit to be sure.
             if (cleanOffers.length === expectedCount) {
                 if (cleanOffers.length > 1) {
                     console.log(`Success! Found exactly ${cleanOffers.length} valid offers.`);
                     uniqueOffers.push(...cleanOffers); 
                     break;
                 } else {
                     // If we only expect 1, make sure it's STABLE (wait 5 iterations)
                     stableMatches++;
                     if (stableMatches > 5) {
                         console.log(`Success! Found 1 valid offer and stable.`);
                         uniqueOffers.push(...cleanOffers); 
                         break;
                     }
                 }
             } else {
                 stableMatches = 0;
             }
             
             // If we have MORE than expected (unlikely given dedupe), accept it?
             if (cleanOffers.length > expectedCount) {
                  console.log(`Found MORE than expected (${cleanOffers.length} > ${expectedCount}). accepting.`);
                  uniqueOffers.push(...cleanOffers); 
                  break;
             }
             
             if (attempts % 10 === 0) console.log(`Attempt ${attempts}: Found ${cleanOffers.length}/${expectedCount} offers.`);
             
             await delay(100);
             attempts++;
        }
        
        if (uniqueOffers.length === 0 && attempts >= 150) {
             console.log("Timed out waiting for offer count match.");
        }
        
        console.log(`Extracted ${uniqueOffers.length} offers`);
        
        // Inject into DOM
        } catch (error) {
            console.error("Error in JS execution:", error);
        } finally {
            // ALWAYS Inject into DOM (empty array if offers is undefined or error)
            const resultDiv = document.createElement('div');
            resultDiv.id = 'extracted_offers_json';
            // ensure uniqueOffers exists from outer scope, or default to []
            resultDiv.textContent = JSON.stringify(uniqueOffers || []);
            document.body.appendChild(resultDiv);
            console.log("Injected extracted offers into DOM (Final)");
        }
    })();
    """
    config = CrawlerRunConfig(
    cache_mode=CacheMode.BYPASS,
    extraction_strategy=extraction_strategy,
    js_code=js_code,
    scan_full_page=True,
    scroll_delay=0.3,
    #magic=True,
    #delay_before_return_html=2.0,
    wait_for="css:#extracted_offers_json",
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
