import asyncio
import re
from flask import Flask, request, jsonify
from playwright.async_api import async_playwright

app = Flask(__name__)

async def get_data_stealth(url):
    async with async_playwright() as p:
        # Launch with stealth-like arguments
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # 1. Load the page (wait for critical elements only)
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(4) # Wait for page hydration
        
        # 2. Extract Product ID
        product_id = re.search(r'/p/([a-zA-Z0-9-]+)', url).group(1)
        api_url = f"https://retail-online-prod.btech.com/api/v1/green/discovery/api/v1/products/{product_id}/offers?city_id=31&area_id=88"

        # 3. RUN FETCH INSIDE BROWSER (This inherits all legitimate browser headers/cookies)
        api_payload = await page.evaluate(f'''async () => {{
            try {{
                const response = await fetch('{api_url}');
                return await response.json();
            }} catch (e) {{
                return [];
            }}
        }}''')

        # 4. Extract Main Info
        product_info = await page.evaluate('''() => {
            return {
                "product_name": document.querySelector('h1')?.innerText || "N/A",
                "brand": "Honor", 
                "price": document.querySelector('[class*="price"]')?.innerText || "N/A",
                "warranty": "12 months warranty"
            }
        }''')
        
        await browser.close()
        return {**product_info, "offers": api_payload}

@app.route('/scrape_btech', methods=['POST'])
def scrape():
    url = request.get_json().get("urls")[0]
    try:
        res = asyncio.run(get_data_stealth(url))
        
        # Handle cases where API returns error or no offers
        raw_offers = res.get("offers") if isinstance(res.get("offers"), list) else []
        
        formatted_offers = [
            {
                "seller_name": off.get("store_name"),
                "price": off.get("price", {}).get("final_price_formatted"),
                "warranty": off.get("warranty") or "12 months warranty"
            } for off in raw_offers
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
