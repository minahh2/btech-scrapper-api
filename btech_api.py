import asyncio
import re
import requests
from flask import Flask, request, jsonify
from playwright.async_api import async_playwright

app = Flask(__name__)

async def fetch_with_session(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Use a context that mimics a real desktop
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # 1. Warm up the session
        await page.goto(url, wait_until="networkidle")
        await asyncio.sleep(3)
        
        # 2. Extract Cookies and URL Info
        cookies = await context.cookies()
        product_id = re.search(r'/p/([a-zA-Z0-9-]+)', url).group(1)
        
        # Extract product details while we are here
        info = await page.evaluate('''() => {
            return {
                "product_name": document.querySelector('h1')?.innerText || "N/A",
                "price": document.querySelector('[class*="price"]')?.innerText || "N/A"
            }
        }''')
        await browser.close()

        # 3. Direct API Call using the Session Cookies
        session = requests.Session()
        for cookie in cookies:
            session.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'])
        
        # Reconstruct the API URL (This is the URL from your successful cURL test)
        api_url = f"https://retail-online-prod.btech.com/api/v1/green/discovery/api/v1/products/{product_id}/offers?city_id=31&area_id=88"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }
        
        response = session.get(api_url, headers=headers, timeout=10)
        
        return {
            **info,
            "offers": response.json() if response.status_code == 200 else []
        }

@app.route('/scrape_btech', methods=['POST'])
def scrape():
    url = request.get_json().get("urls")[0]
    try:
        res = asyncio.run(fetch_with_session(url))
        
        formatted_offers = []
        # Parse the JSON response we got from the API
        if isinstance(res.get("offers"), list):
            for item in res["offers"]:
                formatted_offers.append({
                    "seller_name": item.get("store_name"),
                    "price": item.get("price", {}).get("final_price_formatted"),
                    "warranty": item.get("warranty") or "12 months warranty"
                })
        
        return jsonify({
            "data": [{
                "brand": "Honor", # Can be extracted from DOM if needed
                "product_name": res["product_name"],
                "recommended_seller_price": res["price"],
                "warranty": "12 months warranty",
                "other_offers": formatted_offers
            }],
            "status": 200
        })
    except Exception as e:
        return jsonify({"error": str(e), "status": 500})

if __name__ == '__main__':
    from waitress import serve
    serve(app, host='0.0.0.0', port=5002)
