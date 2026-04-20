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

# 1. THE NETWORK SNIPER (DNS Blackholing)
# We map known ad networks and analytics trackers to 127.0.0.1 so the browser drops them instantly.
browser_config = BrowserConfig(
    viewport_width=1920,
    viewport_height=1080,
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    user_agent_mode="random",
    # light_mode=True, # REMOVED: This can sometimes trigger anti-bot systems
    extra_args=[
        "--disable-dev-shm-usage", # CRITICAL: Prevents Docker RAM crashes
        "--no-sandbox",
        "--disable-gpu",
        # "--disable-web-security", # REMOVED: Triggered B.TECH WAF
        # "--blink-settings=imagesEnabled=false", # REMOVED: Triggered B.TECH WAF
        # NEW: Blackholing heavy trackers and analytics at the OS network level
        "--host-resolver-rules=MAP *google-analytics.com 127.0.0.1, MAP *googletagmanager.com 127.0.0.1, MAP *facebook.net 127.0.0.1, MAP *criteo.com 127.0.0.1, MAP *hotjar.com 127.0.0.1, MAP *adsystem.com 127.0.0.1"
    ]
)

@app.route('/scrape_btech9', methods=['POST'])
def scrape():
    data = request.get_json()
    
    if not data:
         return jsonify({"error": "No JSON payload received"}), 400
         
    urls = data.get("urls")
    schema = data.get("schema")

    if not isinstance(urls, list) or not isinstance(schema, dict):
        return jsonify({"error": "Invalid input. 'urls' must be a list, 'schema' must be a dict."}), 400

    extraction_strategy = JsonCssExtractionStrategy(schema, verbose=True)
    
    # YOUR EXACT ORIGINAL JS LOGIC + NEW DOM CLEANUP
    js_code = """
    (async () => {
        // --- NEW: DOM CLEANUP (Lighten the scrape) ---
        // We instantly delete heavy layout elements that we don't need before parsing
        try {
            const trashSelectors = ['header', 'footer', 'nav', 'aside', 'iframe', 'noscript', '.ads-banner', '.newsletter-popup'];
            document.querySelectorAll(trashSelectors.join(',')).forEach(el => el.remove());
            console.log("Optimized DOM: Removed headers, footers, and iframes.");
        } catch(e) {
            console.log("DOM Cleanup error: ", e);
        }
        // ---------------------------------------------

        const uniqueOffers = [];
        try {
        // 0. STRICT CHECK & FAST EXIT (Performance)
        const bodyText = document.body.innerText || "";
        const HAS_OTHER_OFFERS = bodyText.includes("Offers starting from") || bodyText.includes("Compare the best offers");
        
        if (!HAS_OTHER_OFFERS) {
             console.log("Stict Check: No 'Offers starting from' text found. Assuming Single Offer Page.");
             // FAST EXIT: Return empty array immediately.
             const resultDiv = document.createElement('div');
             resultDiv.id = 'extracted_offers_json';
             resultDiv.textContent = JSON.stringify([]);
             document.body.appendChild(resultDiv);
             return; // EXIT SCRIPT
        }
        
        console.log("Strict Check: Multi-offer text found. Enforcing Strict Wait Mode.");
        
        // Helper to wait
        const delay = ms => new Promise(res => setTimeout(res, ms));
        
        // 1. Click "Other Offers"
        console.log("Locating 'Compare the best offers' button...");
        
        // Target Logic: Find text node -> traverse to button
        let targetButton = null;
        const allElements = Array.from(document.querySelectorAll('*'));
         
        // Iterate backwards (bottom-up) to find the last occurrence
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
        
        // Fallback or assignment
        let el = null;
        if (targetButton) {
             console.log("Found target button via text content.");
             el = targetButton;
        } else {
             const candidates = Array.from(document.querySelectorAll('button, div[role="button"], .flex.justify-between'));
             const specificButtons = candidates.filter(el => {
                  const txt = el.textContent || "";
                  return txt.includes("Compare the best offers");
             });
             
             if (specificButtons.length > 0) {
                 el = specificButtons[specificButtons.length - 1];
                 console.log("Found target button via candidate filter.");
             } else {
                  console.log("Specific 'Compare the best offers' button NOT found. Assuming 1-Offer Page.");
                  el = null; 
             }
        }

        if (el) {
            console.log("Scrolling to element...");
            el.scrollIntoView({behavior: "smooth", block: "center"});
            await delay(2000); 
            
            console.log("Clicking element...");
            el.click();
            await delay(500);
        } else {
            console.log("No clickable element found for sidebar.");
        }
        
        if (el) {
            el.scrollIntoView({behavior: "smooth", block: "center"});
            await delay(1000);
            el.click();
        } else {
            console.error("Critical: Could not find ANY 'Other offers' button to click.");
        }
        
        // 4. Wait for sidebar (Strict Count Wait)
        console.log("Waiting for sidebar content...");
        
        let expectedCount = 2; 
        let countTextForOutput = null; 
        const countSelector = "div.px-small.pt-small.flex.justify-between.items-center span.text-xsmall.font-medium.text-secondarySupportiveD3";
        
        // STRICT WAIT for Count Element
        let waitCountAttempts = 0;
        let countSpan = null;
        
        while (!countSpan && waitCountAttempts < 100) { 
             countSpan = document.querySelector(countSelector);
             if (!countSpan) {
                 const fallback = Array.from(document.querySelectorAll('span')).find(s => s.textContent.includes('sellers'));
                 if (fallback) countSpan = fallback;
             }
             if (countSpan) break;
             await delay(100);
             waitCountAttempts++;
        }
        
        if (countSpan) {
            countTextForOutput = countSpan.textContent.trim();
            const match = countSpan.textContent.match(/(\d+)/);
            if (match) {
                expectedCount = parseInt(match[1]);
            }
        }
        
        if (countTextForOutput) {
            const countDiv = document.createElement('div');
            countDiv.id = 'debug_offer_count';
            countDiv.textContent = countTextForOutput;
            countDiv.style.display = 'none';
            document.body.appendChild(countDiv);
        }

        let attempts = 0;
        let stableMatches = 0;
        
        while (attempts < 150) { 
             const tempOffers = [];
             let rejectedCount = 0;
             
             const sellerPars = Array.from(document.querySelectorAll('p')).filter(p => p.textContent.includes('Sold by'));
             sellerPars.forEach(sellerP => {
                let container = sellerP.parentElement;
                let priceEl = null;
                let warrantyEl = null;
                
                for (let i = 0; i < 5; i++) {
                    if (!container) break;
                    const spans = Array.from(container.querySelectorAll('span'));
                    
                    const foundPrice = spans.find(s => {
                        const txt = s.textContent.trim();
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
                        const wTxt = warrantyEl.textContent.trim();
                        if (wTxt.toLowerCase() === "warranty" || wTxt.toLowerCase() === "warranty:") {
                            if (warrantyEl.nextElementSibling) {
                                warrantyText = warrantyEl.nextElementSibling.textContent.trim();
                            }
                        } else if (wTxt.includes("Warranty:")) {
                            warrantyText = wTxt.replace("Warranty:", "").trim();
                        } else {
                             warrantyText = wTxt; 
                        }
                    }
                    
                    const sName = sellerP.textContent.trim().replace('Sold by', '').trim();
                    const pText = priceEl.textContent.trim();
                    
                    if (sName.length > 0 && pText.length > 0) {
                         tempOffers.push({
                            price: pText,
                            seller_name: sName,
                            warranty: warrantyText
                        });
                    } else {
                        rejectedCount++;
                    }
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
             
             if (expectedCount > 1 && cleanOffers.length === 1 && attempts === 50 && el) {
                 el.scrollIntoView({behavior: "smooth", block: "center"});
                 el.click();
             }
             
             const totalProcessed = cleanOffers.length + rejectedCount;
             
             if (totalProcessed >= expectedCount) {
                 if (cleanOffers.length > 0 || rejectedCount > 0) {
                     if (totalProcessed === expectedCount && expectedCount === 1) {
                          stableMatches++;
                          if (stableMatches > 5) {
                               uniqueOffers.push(...cleanOffers);
                               break;
                          }
                     } else {
                         uniqueOffers.push(...cleanOffers); 
                         break;
                     }
                 }
             } else {
                 stableMatches = 0;
             }
             
             if (cleanOffers.length > expectedCount) { 
                  uniqueOffers.push(...cleanOffers); 
                  break;
             }
             
             await delay(100);
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
    """

    # 2. OPTIMIZED CRAWLER CONFIG
    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        extraction_strategy=extraction_strategy,
        js_code=js_code,
        scan_full_page=True,
        scroll_delay=0.3,
        wait_for="css:#extracted_offers_json",
        simulate_user=True,
        page_timeout=180000,
        
        # --- NEW: Structural Blacklisting ---
        exclude_external_links=True, # Prevents Playwright from parsing outbound links
        exclude_social_media_links=True,
        excluded_tags=['header', 'footer', 'nav', 'aside', 'svg'] # Tells Crawl4AI to ignore these in markdown extraction
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

    # 3. MEMORY SAFE ASYNC EXECUTION
    try:
        result = asyncio.run(run_scraper())
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    from waitress import serve
    print("🚀 Starting B.TECH production server with Waitress (Max 2 threads)...")
    serve(app, host='0.0.0.0', port=5002, threads=2)
