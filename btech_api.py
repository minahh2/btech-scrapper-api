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

# 1. EXACTLY YOUR ORIGINAL CONFIG (Clean, no extra args)
browser_config = BrowserConfig(
    viewport_width=1920,
    viewport_height=1080,
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    user_agent_mode="random"
)

@app.route('/scrape_btech9', methods=['POST'])
def scrape():
    data = request.get_json()
    
    if not data:
         return jsonify({"error": "No JSON payload received"}), 400
         
    urls = data.get("urls")
    schema = data.get("schema")

    if not isinstance(urls, list) or not isinstance(schema, dict):
        return jsonify({"error": "Invalid input"}), 400

    extraction_strategy = JsonCssExtractionStrategy(schema, verbose=True)
    
    # THE TROJAN HORSE: Patched for the new "bukra" UI, LE currency, and new button text
    wait_condition_js = """js:() => {
        // 1. If the div exists, we are done! Unblock Python instantly.
        if (document.getElementById('extracted_offers_json')) return true;
        
        // 2. If we already launched the script, don't launch it again, just wait.
        if (window._isScrapingOffers) return false;
        window._isScrapingOffers = true;
        
        // 3. Launch YOUR EXACT ORIGINAL JS CODE in the background
        (async () => {
            const uniqueOffers = [];
            try {
                const bodyText = document.body.innerText || "";
                // NEW: Updated to match the new button text and panel titles
                const HAS_OTHER_OFFERS = bodyText.includes("Offers starting from") || 
                                         bodyText.includes("Compare the best offers from other sellers") || 
                                         bodyText.includes("Select from other sellers");
                
                if (!HAS_OTHER_OFFERS) {
                     console.log("Strict Check: No 'Offers starting from' text found. Assuming Single Offer Page.");
                     const resultDiv = document.createElement('div');
                     resultDiv.id = 'extracted_offers_json';
                     resultDiv.textContent = JSON.stringify([]);
                     document.body.appendChild(resultDiv);
                     return; 
                }
                
                console.log("Strict Check: Multi-offer text found. Enforcing Strict Wait Mode.");
                const delay = ms => new Promise(res => setTimeout(res, ms));
                console.log("Locating 'Compare the best offers from other sellers' button...");
                
                let targetButton = null;
                const allElements = Array.from(document.querySelectorAll('*'));
                 
                for (let i = allElements.length - 1; i >= 0; i--) {
                    const el = allElements[i];
                    // NEW: Looking for the exact new string
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
                
                let el = null;
                if (targetButton) {
                     console.log("Found target button via text content.");
                     el = targetButton;
                } else {
                     const candidates = Array.from(document.querySelectorAll('button, div[role="button"], .flex.justify-between, .cursor-pointer'));
                     const specificButtons = candidates.filter(e => {
                          const txt = e.textContent || "";
                          return txt.includes("Compare the best offers from other sellers");
                     });
                     
                     if (specificButtons.length > 0) {
                         el = specificButtons[specificButtons.length - 1];
                         console.log("Found target button via candidate filter.");
                     } else {
                          console.log("Specific button NOT found. Assuming 1-Offer Page or already open.");
                          el = null; 
                     }
                }

                if (el) {
                    console.log("Scrolling to element...");
                    el.scrollIntoView({behavior: "smooth", block: "center"});
                    await delay(1000); 
                    console.log("Clicking element...");
                    el.click();
                    await delay(500);
                }
                
                console.log("Waiting for sidebar content...");
                let expectedCount = 2; 
                let waitCountAttempts = 0;
                let countSpan = null;
                
                // NEW: Robust 'Sellers Count' detection for the new Bukra UI (e.g. '5 sellers')
                while (!countSpan && waitCountAttempts < 100) { 
                     const spans = Array.from(document.querySelectorAll('span'));
                     countSpan = spans.find(s => s.textContent.toLowerCase().includes('sellers') && s.textContent.match(/(\d+)/));
                     if (countSpan) break;
                     await delay(100);
                     waitCountAttempts++;
                }
                
                if (countSpan) {
                    console.log("DEBUG: Count Span found: ", countSpan.textContent);
                    const match = countSpan.textContent.match(/(\d+)/);
                    if (match) {
                        expectedCount = parseInt(match[1]);
                        console.log(`Expecting exactly ${expectedCount} sellers based on selector.`);
                    }
                }

                let attempts = 0;
                let stableMatches = 0;
                
                while (attempts < 150) { 
                     const tempOffers = [];
                     let rejectedCount = 0;
                     
                     // NEW: The seller is now inside nested spans `<p><span>Sold by</span><span>Name</span></p>`
                     const sellerPars = Array.from(document.querySelectorAll('p, div')).filter(p => p.textContent.includes('Sold by') && p.children.length > 0);
                     
                     // Use a set to prevent duplicating reads from nested divs
                     const processedSellers = new Set();

                     sellerPars.forEach(sellerP => {
                        const sNameRaw = sellerP.textContent.trim().replace('Sold by', '').trim();
                        if (processedSellers.has(sNameRaw)) return;
                        processedSellers.add(sNameRaw);

                        let container = sellerP.parentElement;
                        let priceEl = null;
                        let warrantyText = "";
                        
                        for (let i = 0; i < 6; i++) {
                            if (!container) break;
                            const spans = Array.from(container.querySelectorAll('span'));
                            
                            // NEW: Notice how we check for 'LE' now instead of just 'EGP'
                            const foundPrice = spans.find(s => {
                                const txt = s.textContent.trim();
                                return /^\s*[\d,.]+\s*$/.test(txt) && !txt.includes('EGP') && !txt.includes('LE');
                            });
                            
                            // If we found the number, check if its container has LE or EGP
                            if (foundPrice && (container.textContent.includes('EGP') || container.textContent.includes('LE'))) {
                                priceEl = foundPrice;
                                
                                // NEW: Warranty is now an inline span with an SVG image inside
                                const wEl = spans.find(s => s.textContent.toLowerCase().includes('warranty'));
                                if (wEl) {
                                    warrantyText = wEl.textContent.trim();
                                }
                                break;
                            }
                            container = container.parentElement;
                        }
                        
                        const pText = priceEl ? priceEl.textContent.trim() : "";
                        
                        if (sNameRaw.length > 0 && pText.length > 0) {
                             tempOffers.push({
                                price: pText,
                                seller_name: sNameRaw,
                                warranty: warrantyText
                             });
                        } else {
                            rejectedCount++;
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
                     
                     if (totalProcessed >= expectedCount && expectedCount > 0) {
                         stableMatches++;
                         if (stableMatches > 4) { // Increased stability threshold slightly
                             uniqueOffers.push(...cleanOffers);
                             break;
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
                // The moment this injects, Playwright will detect it and unblock Python!
                const resultDiv = document.createElement('div');
                resultDiv.id = 'extracted_offers_json';
                resultDiv.textContent = JSON.stringify(uniqueOffers || []);
                document.body.appendChild(resultDiv);
            }
        })();
        
        return false; // Tell Playwright to keep polling until the div exists
    }"""

    # 2. YOUR EXACT RUN CONFIGURATION
    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        extraction_strategy=extraction_strategy,
        
        # We removed js_code parameter entirely! The script is now safely running inside wait_for.
        
        scan_full_page=True,      # RESTORED: Exactly as you demanded for B.TECH lazy loading
        scroll_delay=0.3,
        simulate_user=True,
        
        wait_for=wait_condition_js, # The Trojan Horse
        
        # Performance Targeting & Exclusions
        excluded_tags=['nav', 'footer', 'header', 'script', 'style', 'noscript'],
        exclude_external_links=True,
        exclude_social_media_links=True,
        exclude_external_images=True,
        page_timeout=60000        # Safety net, but your JS will unblock it in 8-12s
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
    print("🚀 Starting B.TECH production server with Waitress...")
    serve(app, host='0.0.0.0', port=5002, threads=2)
