import os
import json
import asyncio
from flask import Flask, request, jsonify
from playwright.async_api import async_playwright

app = Flask(__name__)

_playwright_semaphore = asyncio.Semaphore(5)

async def process_url_with_playwright(url, schema_fields):
    async with _playwright_semaphore:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-gpu',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled'
                ]
            )
            
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            
            page = await context.new_page()
            
            offers_data = []
            api_caught = asyncio.Event()
            
            async def handle_response(response):
                if "discovery/api/v1/products/" in response.url and "/offers" in response.url:
                    try:
                        json_data = await response.json()
                        if "data" in json_data and "offers" in json_data["data"]:
                            for offer in json_data["data"]["offers"]:
                                seller_name = offer.get("seller", {}).get("name", "")
                                price = str(offer.get("price", {}).get("amount", ""))
                                warranty = offer.get("warranty", "")
                                
                                offers_data.append({
                                    "seller_name": seller_name,
                                    "price": price,
                                    "warranty": warranty
                                })
                            api_caught.set()
                    except Exception as e:
                        pass
                        
            page.on("response", handle_response)
            
            status_code = 200
            error_msg = ""
            extracted_data = {}
            
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                status_code = response.status if response else 200
                
                # Try to trigger the drawer using the exact JS click that worked on the VPS
                click_js = """
                () => {
                    const all = Array.from(document.querySelectorAll("*:not(script):not(style)"));
                    const matches = all.filter(e => (e.innerText || "").replace(/\\s+/g, " ").includes("Compare the best offers"));
                    
                    if(matches.length > 0) {
                        const candidates = Array.from(document.querySelectorAll('button, div[role="button"], .flex.justify-between, .cursor-pointer'));
                        const specificButtons = candidates.filter(e => (e.textContent || "").replace(/\\s+/g, " ").includes("Compare the best offers"));
                        
                        const visibleButtons = specificButtons.filter(b => b.offsetWidth > 0 && b.offsetHeight > 0);
                        const btnToClick = visibleButtons.length > 0 ? visibleButtons[0] : specificButtons[0];
                        
                        if (btnToClick) {
                            btnToClick.scrollIntoView();
                            
                            const eventOpts = { bubbles: true, cancelable: true, view: window };
                            btnToClick.dispatchEvent(new MouseEvent('click', eventOpts));
                            
                            try { btnToClick.click(); } catch(e) {}
                            
                            let fiberKey = Object.keys(btnToClick).find(k => k.startsWith('__reactFiber$'));
                            if (fiberKey) {
                                let fiber = btnToClick[fiberKey];
                                let found = false;
                                while (fiber && !found) {
                                    if (fiber.memoizedProps) {
                                        ['onClick', 'onPointerDown', 'onMouseDown'].forEach(h => {
                                            if (typeof fiber.memoizedProps[h] === 'function') {
                                                try {
                                                    fiber.memoizedProps[h]({ preventDefault: () => {}, stopPropagation: () => {}, target: btnToClick, currentTarget: btnToClick });
                                                    found = true;
                                                } catch(e) {}
                                            }
                                        });
                                    }
                                    fiber = fiber.return;
                                }
                            }
                        }
                    }
                }
                """
                try:
                    await page.evaluate(click_js)
                    # Wait for API response up to 5 seconds
                    try:
                        await asyncio.wait_for(api_caught.wait(), timeout=6.0)
                    except asyncio.TimeoutError:
                        await page.wait_for_timeout(4000) # Wait for DOM to render if API failed
                except Exception:
                    pass
                    
                js_extract = """
                (fields) => {
                    let result = {};
                    for (const field of fields) {
                        if (field.name === 'other_offers') continue;
                        
                        try {
                            const el = document.querySelector(field.selector);
                            if (el) {
                                result[field.name] = (el.innerText || el.textContent || "").trim();
                            } else {
                                result[field.name] = "";
                            }
                        } catch(e) {
                            result[field.name] = "";
                        }
                    }
                    
                    let uniqueOffers = [];
                    try {
                        const tempOffers = [];
                        const soldByPs = Array.from(document.querySelectorAll('p')).filter(p => (p.textContent || "").includes("Sold by"));
                        
                        soldByPs.forEach(soldByP => {
                            let sellerName = "";
                            let price = "";
                            let warranty = "";

                            const spans = soldByP.querySelectorAll('span');
                            if (spans.length >= 2) sellerName = spans[1].textContent.trim();
                            else sellerName = soldByP.textContent.replace('Sold by', '').trim();

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

                        const seen = new Set();
                        tempOffers.forEach(o => {
                            const key = o.seller_name + o.price;
                            if (!seen.has(key)) {
                                seen.add(key);
                                uniqueOffers.push(o);
                            }
                        });
                    } catch(e) {}
                    
                    result["dom_offers"] = uniqueOffers;
                    return result;
                }
                """
                extracted_data = await page.evaluate(js_extract, schema_fields)
                
                seen = set()
                unique_offers = []
                # First append API offers if any
                for o in offers_data:
                    key = f"{o['seller_name']}_{o['price']}"
                    if key not in seen:
                        seen.add(key)
                        unique_offers.append(o)
                # Then append DOM offers if any
                for o in extracted_data.pop("dom_offers", []):
                    key = f"{o['seller_name']}_{o['price']}"
                    if key not in seen:
                        seen.add(key)
                        unique_offers.append(o)
                        
                extracted_data["other_offers"] = unique_offers
                
            except Exception as e:
                error_msg = str(e)
                status_code = 500
                
            finally:
                await browser.close()
                
            return {
                "url": url,
                "status": status_code,
                "error": error_msg,
                "data": [extracted_data] if not error_msg else []
            }


@app.route('/scrape_btech9', methods=['POST'])
def scrape():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON payload received"}), 400
         
    urls = data.get("urls")
    schema = data.get("schema")

    if not isinstance(urls, list) or not isinstance(schema, dict):
        return jsonify({"error": "Invalid input"}), 400

    fields = schema.get("fields", [])

    async def run_all():
        tasks = [process_url_with_playwright(url_info.get("url"), fields) for url_info in urls]
        return await asyncio.gather(*tasks)

    results = asyncio.run(run_all())
    return jsonify(results)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=False)
