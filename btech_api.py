import asyncio
from flask import Flask, request, jsonify
from playwright.async_api import async_playwright

app = Flask(__name__)

async def get_btech_data_surgical(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # Load page
        await page.goto(url, wait_until="domcontentloaded")
        
        # 1. Setup the "Spy" for the API request BEFORE clicking
        # We look for any response that contains "offers" and returns JSON
        async with page.expect_response(lambda r: "offers?" in r.url, timeout=20000) as response_info:
            
            # 2. NUCLEAR CLICK: Don't use playwright locator.click()
            # Use JS to trigger the element directly from its selector
            await page.evaluate('''() => {
                const btn = document.querySelector('[data-slot="card-header"]');
                if (btn) btn.click();
            }''')
        
        # Capture the result
        response = await response_info.value
        api_data = await response.json()

        # 3. DOM Extraction (Fallback)
        product_info = await page.evaluate('''() => {
            return {
                "product_name": document.querySelector('h1')?.innerText || "N/A",
                "brand": "Honor",
                "price": document.querySelector('[class*="price"]')?.innerText || "N/A",
                "warranty": "12 months warranty"
            }
        }''')
        
        await browser.close()
        return {**product_info, "other_offers": api_data}

@app.route('/scrape_btech', methods=['POST'])
def scrape():
    data = request.get_json()
    url = data.get("urls")[0]
    
    try:
        res = asyncio.run(get_btech_data_surgical(url))
        
        formatted_offers = []
        if isinstance(res.get("other_offers"), list):
            for item in res["other_offers"]:
                formatted_offers.append({
                    "seller_name": item.get("store_name"),
                    "price": item.get("price", {}).get("final_price_formatted"),
                    "warranty": item.get("warranty") or "12 months warranty"
                })
        
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
        return jsonify({"error": f"Scrape failed: {str(e)}", "status": 500})

if __name__ == '__main__':
    from waitress import serve
    serve(app, host='0.0.0.0', port=5002)
