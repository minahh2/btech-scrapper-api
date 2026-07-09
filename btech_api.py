import asyncio
import re
from flask import Flask, request, jsonify
from playwright.async_api import async_playwright

app = Flask(__name__)

async def get_data_robust(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # Capture Container for API Data
        api_payload = {"offers": []}
        
        # 1. Capture the API response automatically
        async def handle_response(response):
            if "offers?" in response.url:
                try:
                    api_payload["offers"] = await response.json()
                except: pass
        page.on("response", handle_response)

        # 2. Go to page
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(5) # Wait for network hydration

        # 3. Robust Extraction using generic attributes (less fragile than CSS selectors)
        data = await page.evaluate('''() => {
            const getTxt = (sel) => document.querySelector(sel)?.innerText || "N/A";
            // Searching for common B.TECH patterns
            return {
                "product_name": document.querySelector('h1')?.innerText || "N/A",
                "brand": document.querySelector('h1')?.innerText?.split(' ')[0] || "N/A",
                "price": document.querySelector('[class*="price"]')?.innerText || "N/A",
                "warranty": document.body.innerText.match(/\\d+\\s*(?:month|year)s?\\s*warranty/i)?.[0] || "12 months warranty"
            }
        }''')
        
        await browser.close()
        return {**data, "other_offers": api_payload["offers"]}

@app.route('/scrape_btech', methods=['POST'])
def scrape():
    url = request.get_json().get("urls")[0]
    try:
        res = asyncio.run(get_data_robust(url))
        
        # Format the API response
        formatted_offers = []
        for item in res.get("other_offers", []):
            formatted_offers.append({
                "seller_name": item.get("store_name"),
                "price": item.get("price", {}).get("final_price_formatted"),
                "warranty": item.get("warranty") or "12 months warranty"
            })
            
        return jsonify({
            "data": [{
                "brand": res["brand"],
                "product_name": res["product_name"],
                "recommended_seller_price": res["price"],
                "warranty": res["warranty"],
                "other_offers": formatted_offers
            }],
            "status": 200
        })
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    from waitress import serve
    serve(app, host='0.0.0.0', port=5002)
