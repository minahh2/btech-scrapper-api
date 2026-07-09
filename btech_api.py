import asyncio
import re
import requests
from flask import Flask, request, jsonify
from playwright.async_api import async_playwright

app = Flask(__name__)

async def get_btech_data_robust(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # Variable to store intercepted data
        captured_data = {"token": None, "api_response": None}

        # Intercept the API call to get the token AND the response
        async def handle_request(request):
            if "offers?" in request.url:
                auth = request.headers.get("authorization")
                if auth: captured_data["token"] = auth
        
        async def handle_response(response):
            if "offers?" in response.url and response.status == 200:
                captured_data["api_response"] = await response.json()

        page.on("request", handle_request)
        page.on("response", handle_response)

        # Navigate
        await page.goto(url, wait_until="networkidle")
        await asyncio.sleep(3) # Ensure network calls finish
        
        # Extract main page data (Robust fallback)
        product_info = await page.evaluate('''() => {
            return {
                "product_name": document.querySelector('h1')?.innerText || "N/A",
                "brand": document.querySelector('[data-slot="brand-name"]')?.innerText || "N/A",
                "price": document.querySelector('span[class*="price"]')?.innerText || "N/A",
                "warranty": "12 months warranty"
            }
        }''')
        
        await browser.close()
        return {**product_info, "offers": captured_data["api_response"]}

@app.route('/scrape_btech', methods=['POST'])
def scrape():
    data = request.get_json()
    url = data.get("urls")[0]
    
    try:
        result = asyncio.run(get_btech_data_robust(url))
        
        # Map to your required output format
        formatted = {
            "brand": result.get("brand"),
            "product_name": result.get("product_name"),
            "recommended_seller_price": result.get("price"),
            "warranty": result.get("warranty"),
            "other_offers": [
                {
                    "seller_name": off.get("store_name"),
                    "price": off.get("price", {}).get("final_price_formatted"),
                    "warranty": off.get("warranty") or "12 months warranty"
                } for off in (result.get("offers") or [])
            ]
        }
        return jsonify({"data": [formatted], "status": 200, "url": url})
    except Exception as e:
        return jsonify({"error": str(e), "status": 500})

if __name__ == '__main__':
    from waitress import serve
    serve(app, host='0.0.0.0', port=5002)
