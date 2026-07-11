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
    headless=True,
    viewport_width=1920,
    viewport_height=1080,
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    user_data_dir="/app/chrome_cache",
    use_persistent_context=True,
    extra_args=[
        "--no-sandbox", 
        "--disable-gpu", 
        "--disable-extensions",
        "--disable-dev-shm-usage", 
        "--js-flags=--max-old-space-size=512",
        "--disable-features=IsolateOrigins,site-per-process",
        "--disable-blink-features=AutomationControlled"
    ]
)

_btech_session_counter = 0
def get_btech_session_id():
    global _btech_session_counter
    _btech_session_counter += 1
    return f"btech_session_{_btech_session_counter // 50}"

@app.route('/scrape_btech9', methods=['POST'])
def scrape():
    _current_session_id = get_btech_session_id()
    data = request.get_json()
    
    if not data:
         return jsonify({"error": "No JSON payload received"}), 400
         
    urls = data.get("urls")
    schema = data.get("schema")

    if not isinstance(urls, list) or not isinstance(schema, dict):
        return jsonify({"error": "Invalid input"}), 400

    extraction_strategy = JsonCssExtractionStrategy(schema, verbose=True)
    
    # Modern Crawl4AI 0.9.x Page Interaction
    JS_BEFORE_WAIT = """
    return new Promise((resolve) => {
        window.__BTECH_DEBUG = { stage: "init", matches: 0, clicked: false, fiber: false, url: window.location.href };
        setTimeout(() => {
            try {
                const all = Array.from(document.querySelectorAll("*:not(script):not(style)"));
                const matches = all.filter(e => (e.innerText || "").replace(/\\s+/g, " ").includes("Compare the best offers"));
                window.__BTECH_DEBUG.matches = matches.length;
                
                if(matches.length > 0) {
                    const candidates = Array.from(document.querySelectorAll('button, div[role="button"], .flex.justify-between, .cursor-pointer'));
                    const specificButtons = candidates.filter(e => (e.textContent || "").replace(/\\s+/g, " ").includes("Compare the best offers"));
                    
                    if (specificButtons.length > 0) {
                        specificButtons.forEach(b => {
                            try {
                                b.scrollIntoView();
                                b.addEventListener('click', function(e) { e.preventDefault(); });
                                if (b.tagName === 'A') b.removeAttribute('href');
                                
                                const eventOpts = { bubbles: true, cancelable: true, view: window };
                                b.dispatchEvent(new MouseEvent('click', eventOpts));
                                b.click();
                                window.__BTECH_DEBUG.clicked = true;
                                
                                let fiberKey = Object.keys(b).find(k => k.startsWith('__reactFiber$'));
                                if (fiberKey) {
                                    let fiber = b[fiberKey];
                                    let found = false;
                                    while (fiber && !found) {
                                        if (fiber.memoizedProps) {
                                            ['onClick', 'onPointerDown', 'onMouseDown'].forEach(h => {
                                                if (typeof fiber.memoizedProps[h] === 'function') {
                                                    try {
                                                        fiber.memoizedProps[h]({ preventDefault: () => {}, stopPropagation: () => {}, target: b, currentTarget: b });
                                                        found = true;
                                                    } catch(e) {}
                                                }
                                            });
                                        }
                                        fiber = fiber.return;
                                    }
                                    window.__BTECH_DEBUG.fiber = true;
                                }
                            } catch(e) {}
                        });
                    }
                }
            } catch(e) {
                window.__BTECH_DEBUG.error = e.toString();
            }
            
            // Wait 5 seconds after click to allow API to fetch cards, regardless of layout changes!
            setTimeout(() => {
                window.__BTECH_DEBUG.stage = "done_waiting";
                resolve(true);
            }, 5000);
            
        }, 2500);
    });
    """

    JS_EXTRACT_SCRIPT = """
    let uniqueOffers = [];
    try {
        const bodyText = document.body.innerText || "";
        const HAS_OTHER_OFFERS = bodyText.includes("Offers starting from") ||
            bodyText.includes("Compare the best offers") ||
            bodyText.includes("Select from other sellers");
            
        window.__BTECH_DEBUG.has_offers_text = HAS_OTHER_OFFERS;

        if (HAS_OTHER_OFFERS) {
            const tempOffers = [];
            
            // Bulletproof extraction: find ALL <p> tags containing "Sold by"
            const soldByPs = Array.from(document.querySelectorAll('p')).filter(p => (p.textContent || "").includes("Sold by"));
            window.__BTECH_DEBUG.sold_by_ps = soldByPs.length;
            
            soldByPs.forEach(soldByP => {
                let sellerName = "";
                let price = "";
                let warranty = "";

                const spans = soldByP.querySelectorAll('span');
                if (spans.length >= 2) sellerName = spans[1].textContent.trim();
                else sellerName = soldByP.textContent.replace('Sold by', '').trim();

                // Traverse up to find the container with the price
                let card = soldByP.parentElement;
                let currencySpan = null;
                while (card && card !== document.body) {
                    const priceSpans = card.querySelectorAll('span');
                    currencySpan = Array.from(priceSpans).find(s => {
                        const t = s.textContent.trim();
                        return t === 'LE' || t === 'EGP';
                    });
                    if (currencySpan) break;
                    card = card.parentElement;
                }

                if (currencySpan && currencySpan.previousElementSibling) {
                    price = currencySpan.previousElementSibling.textContent.trim();
                }

                if (card) {
                    const wSpan = Array.from(card.querySelectorAll('span')).find(s => (s.textContent || "").toLowerCase().includes('warranty'));
                    if (wSpan) warranty = wSpan.textContent.trim();
                }

                if (sellerName && price) {
                    tempOffers.push({ seller_name: sellerName, price: price, warranty: warranty });
                }
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
            tempOffers.forEach(o => {
                const key = o.seller_name + o.price;
                if (!seen.has(key)) {
                    seen.add(key);
                    uniqueOffers.push(o);
                }
            });
            window.__BTECH_DEBUG.unique_offers = uniqueOffers.length;
        }
    } catch (error) {
        console.error("Extraction error", error);
        window.__BTECH_DEBUG.extract_error = error.toString();
    } finally {
        const resultDiv = document.createElement('div');
        resultDiv.id = 'extracted_offers_json';
        // IF WE FOUND 0 OFFERS, SPIT OUT THE DEBUG INFO INSTEAD!
        if (uniqueOffers.length === 0) {
            resultDiv.textContent = JSON.stringify([{ "DEBUG_INFO": window.__BTECH_DEBUG }]);
        } else {
            resultDiv.textContent = JSON.stringify(uniqueOffers);
        }
        document.body.appendChild(resultDiv);
    }
    """
    
    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        session_id=_current_session_id,
        extraction_strategy=extraction_strategy,
        js_code_before_wait=JS_BEFORE_WAIT,
        js_code=[JS_EXTRACT_SCRIPT],
        wait_for='js:() => true',
        delay_before_return_html=0.5,
        remove_overlay_elements=False,
        excluded_tags=['nav', 'footer', 'header', 'script', 'style', 'noscript'],
        exclude_external_links=True,
        exclude_social_media_links=True,
        exclude_external_images=True,
        word_count_threshold=10,
        magic=False 
    )

    async def run_scraper():
        async with AsyncWebCrawler(config=browser_config, verbose=False) as crawler:
            results = await crawler.arun_many(urls=urls, config=config, semaphore_count=3)
            
            output = []
            for result in results:
                if result.success:
                    js_res = getattr(result, "js_execution_result", "None")
                    js_debug = str(js_res)[:500] if js_res else "None"
                try:
                    extracted = json.loads(result.extracted_content)
                    if isinstance(extracted, list) and len(extracted) > 0:
                        item = extracted[0]
                        item["js_debug"] = js_debug
                        if "other_offers" in item and isinstance(item["other_offers"], str):
                            try:
                                item["other_offers"] = json.loads(item["other_offers"])
                            except Exception:
                                pass
                    elif isinstance(extracted, dict) and "data" in extracted and len(extracted["data"]) > 0:
                        item = extracted["data"][0]
                        item["js_debug"] = js_debug
                        if "other_offers" in item and isinstance(item["other_offers"], str):
                            try:
                                item["other_offers"] = json.loads(item["other_offers"])
                            except Exception:
                                pass
                except Exception:
                    extracted = {"error": "Failed to parse extracted content", "js_debug": js_debug}
                
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
    print("🚀 Starting B.TECH development server (bypassing Waitress to prevent thread deadlocks)...")
    app.run(host='0.0.0.0', port=5002, threaded=True)
