import asyncio
import re
import json
from flask import Flask, request, jsonify
from playwright.async_api import async_playwright

app = Flask(__name__)

async def get_btech_data(url):
    async with async_playwright() as p:
        # 1. Stealth Browser Config
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()

        # 2. Extract Product ID Dynamically
        product_id = re.search(r'/p/([a-zA-Z0-9-]+)', url)
        if not product_id: return {"error": "Invalid URL"}
        pid = product_id.group(1)

        # 3. Intercept API Response
        api_data = []
        async def handle_response(response):
            if "offers?" in response.url and pid in response.url:
                try:
                    nonlocal api_data
                    api_data = await response.json()
                except: pass
        
        page.on("response", handle_response)

        # 4. Navigate and Extract
        await page.goto(url, wait_until="networkidle")
        
        # Extract main info from the DOM
        product_info = await page.evaluate('''() => {
            return {
                "product_name": document.querySelector('h1')?.innerText || "N/A",
                "brand": document.querySelector('[data-slot="brand-name"]')?.innerText || "N/A",
                "recommended_seller_name": document.querySelector('.seller-info')?.innerText || "Sold by B.TECH",
                "recommended_seller_price": document.querySelector('.price-main')?.innerText || "N/A",
                "warranty": document.querySelector('.warranty-info')?.innerText || "12 months warranty"
            }
        }''')

        # Give it a moment to catch the network response
        await asyncio.sleep(2)
        await browser.close()

        # 5. Merge Data
        product_info["other_offers"] = api_data
        return product_info

@app.route('/scrape_btech', methods=['POST'])
def scrape():
    data = request.get_json()
    url = data.get("urls")[0]
    
    try:
        result = asyncio.run(get_btech_data(url))
        return jsonify({"data": [result], "status": 200, "url": url})
    except Exception as e:
        return jsonify({"error": str(e), "status": 500})

if __name__ == '__main__':
    from waitress import serve
    serve(app, host='0.0.0.0', port=5002)
