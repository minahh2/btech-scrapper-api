import os
import json
import asyncio
from flask import Flask, request, jsonify
from playwright.async_api import async_playwright

app = Flask(__name__)

_playwright_semaphore = asyncio.Semaphore(5)

async def process_url_with_playwright(url, schema_fields):
    async with _playwright_semaphore:
        try:
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
                            if isinstance(json_data, list):
                                for offer in json_data:
                                    seller_name = offer.get("store_name", "")
                                    price = str(offer.get("price", {}).get("final_price_formatted", ""))
                                    warranty = offer.get("warranty", "") or ""
                                    
                                    offers_data.append({
                                        "seller_name": f"Sold by {seller_name}" if seller_name else "",
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
                    response = await page.goto(url, wait_until="networkidle", timeout=30000)
                    status_code = response.status if response else 200
                    
                    try:
                        button = page.locator("text=Compare the best offers").first
                        try:
                            await button.wait_for(state="visible", timeout=5000)
                            await button.click(timeout=3000)
                            try:
                                await asyncio.wait_for(api_caught.wait(), timeout=6.0)
                            except asyncio.TimeoutError:
                                pass
                        except Exception as e:
                            pass
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
                    
                    if offers_data:
                        unique_offers = offers_data
                    else:
                        unique_offers = extracted_data.pop("dom_offers", [])
                        
                    # Deduplicate just in case
                    final_offers = []
                    seen = set()
                    for o in unique_offers:
                        # Normalize key
                        raw_seller = o['seller_name'].lower().replace("sold by", "").strip()
                        key = f"{raw_seller}_{o['price']}"
                        if key not in seen:
                            seen.add(key)
                            final_offers.append(o)
                            
                    extracted_data["other_offers"] = final_offers
                    
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
        except Exception as e:
            return {
                "url": url,
                "status": 500,
                "error": f"Playwright Init Error: {str(e)}",
                "data": []
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
        tasks = []
        for u in urls:
            url_str = u.get("url") if isinstance(u, dict) else u
            tasks.append(process_url_with_playwright(url_str, fields))
        return await asyncio.gather(*tasks)

    results = asyncio.run(run_all())
    return jsonify(results)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=False)
