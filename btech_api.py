import asyncio
import re
from flask import Flask, request, jsonify
from playwright.async_api import async_playwright

app = Flask(__name__)

async def fetch_btech_data(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # 1. Faster Navigation
        await page.goto(url, wait_until="domcontentloaded")
        
        # 2. Extract Product ID
        product_id = re.search(r'/p/([a-zA-Z0-9-]+)', url).group(1)
        
        # 3. Direct API call from within the Browser Session
        # This inherits all cookies/tokens automatically!
        api_url = f"https://retail-online-prod.btech.com/api/v1/green/discovery/api/v1/products/{product_id}/offers?city_id=31&area_id=88"
        
        # This performs the request *as the browser*
        response = await page.request.get(api_url)
        
        offers = []
        if response.status == 200:
            offers = await response.json()
            
        # 4. Fallback DOM extraction for main product info
        product_info = await page.evaluate('''() => {
            return {
                "product_name": document.querySelector('h1')?.innerText || "N/A",
                "brand": document.querySelector('[data-slot="brand-name"]')?.innerText || "N/A",
                "price": document.querySelector('.price-main')?.innerText || "N/A",
                "warranty": "12 months warranty"
            }
        }''')
        
        await browser.close()
        return {**product_info, "other_offers": offers}

@app.route('/scrape_btech', methods=['POST'])
def scrape():
    data = request.get_json()
    url = data.get("urls")[0]
    try:
        res = asyncio.run(fetch_btech_data(url))
        
        formatted_offers = [
            {
                "seller_name": off.get("store_name"),
                "price": off.get("price", {}).get("final_price_formatted"),
                "warranty": off.get("warranty") or "12 months warranty"
            } for off in (res.get("other_offers") or [])
        ]
        
        return jsonify({
            "data": [{
                "brand": res.get("brand"),
                "product_name": res.get("product_name"),
                "recommended_seller_price": res.get("price"),
                "warranty": res.get("warranty"),
                "other_offers": formatted_offers
            }],
            "status": 200
        })
    except Exception as e:
        return jsonify({"error": str(e), "status": 500})

if __name__ == '__main__':
    from waitress import serve
    serve(app, host='0.0.0.0', port=5002)
