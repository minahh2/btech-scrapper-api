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
    
    # JS Logic executed exactly ONCE
    JS_CLICK_SCRIPT = """
    return new Promise((resolve) => {
        (async () => {
            const uniqueOffers = [];
            try {
                const delay = ms => new Promise(res => setTimeout(res, ms));
                await delay(2500); // CRITICAL: Wait for React hydration before clicking!

                const bodyText = document.body.innerText || "";
                const HAS_OTHER_OFFERS = bodyText.includes("Offers starting from") ||
                    bodyText.includes("Compare the best offers from other sellers") ||
                    bodyText.includes("Select from other sellers");

                if (!HAS_OTHER_OFFERS) {
                    const resultDiv = document.createElement('div');
                    resultDiv.id = 'extracted_offers_json';
                    resultDiv.textContent = JSON.stringify([]);
                    document.body.appendChild(resultDiv);
                    resolve("NO OFFERS BUTTON FOUND");
                    return;
                }

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
                    el.scrollIntoView({ behavior: "smooth", block: "center" });
                    await delay(1000);
                    
                    // CRITICAL FIX: Stop the browser from navigating if it's a link!
                    el.addEventListener('click', function(e) {
                        e.preventDefault();
                    });
                    if (el.tagName === 'A') el.removeAttribute('href');
                    
                    el.click();
                    await delay(1000); // Give panel time to open
                } else {
                    const resultDiv = document.createElement('div');
                    resultDiv.id = 'extracted_offers_json';
                    resultDiv.textContent = JSON.stringify([]);
                    document.body.appendChild(resultDiv);
                    resolve("BUTTON FOUND IN TEXT BUT NOT IN DOM");
                    return;
                }

                let attempts = 0;
                let previousCount = 0;
                let stableMatches = 0;
                let maxCardsSeen = 0;
                let finalDebug = "";

                while (attempts < 100) {
                    const tempOffers = [];
                    const cards = document.querySelectorAll('[data-slot="card"], [data-slot="expandable-card"]');
                    if (cards.length > maxCardsSeen) maxCardsSeen = cards.length;

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

                    if (cleanOffers.length > 0) {
                        if (cleanOffers.length === previousCount) {
                            stableMatches++;
                            if (stableMatches >= 5) {
                                uniqueOffers.push(...cleanOffers);
                                finalDebug = "SUCCESS: Found " + cleanOffers.length + " offers";
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
                
                if (uniqueOffers.length === 0) {
                     finalDebug = "FAILED: Loop ended. Max cards seen in DOM: " + maxCardsSeen;
                }
            } catch (error) {
                resolve("ERROR: " + error.toString());
            } finally {
                const resultDiv = document.createElement('div');
                resultDiv.id = 'extracted_offers_json';
                resultDiv.textContent = JSON.stringify(uniqueOffers || []);
                document.body.appendChild(resultDiv);
                resolve(finalDebug);
            }
        })();
    });
    """

    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        session_id=_current_session_id,
        extraction_strategy=extraction_strategy,
        js_code=[JS_CLICK_SCRIPT],
        delay_before_return_html=0.5,
        remove_overlay_elements=False, # VERY IMPORTANT: Prevents crawl4ai from accidentally deleting the sidebar drawer!
        excluded_tags=['nav', 'footer', 'header', 'script', 'style', 'noscript'],
        exclude_external_links=True,
        exclude_social_media_links=True,
        exclude_external_images=True,
        word_count_threshold=10,
        magic=False 
    )

    async def run_scraper():
        async with AsyncWebCrawler(config=browser_config, verbose=True) as crawler:
            results = await crawler.arun_many(urls=urls, config=config)
            output = []
            for result in results:
                if result.success:
                    js_res = getattr(result, "js_execution_result", "None")
                    js_debug = str(js_res)[:500] if js_res else "None"
                    
                    try:
                        extracted = json.loads(result.extracted_content)
                        # Ensure 'other_offers' is a JSON array instead of a string
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
    from waitress import serve
    print("🚀 Starting B.TECH production server with Waitress...")
    serve(app, host='0.0.0.0', port=5002, threads=2)
