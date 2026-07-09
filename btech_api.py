import asyncio
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
        api_data = None

        # 1. Start listening for the specific API response
        async def handle_response(response):
            if "offers?" in response.url:
                try:
                    nonlocal api_data
                    api_data = await response.json()
                except: pass

        page.on("response", handle_response)

        # 2. Load the page
        await page.goto(url, wait_until="domcontentloaded")
        
        # 3. Target the button and click
        try:
            btn = page.locator('div[data-slot="card-header"]')
            if await btn.count() > 0:
                await btn.click(force=True)
                # CRITICAL: Wait specifically for the API response
                await page.wait_for_response(lambda r: "offers?" in r.url, timeout=15000)
                await asyncio.sleep(1) # Extra buffer
        except Exception as e:
            print(f"Click/Network error: {e}")

        # Extract DOM data as fallback
        product_info = await page.evaluate('''() => {
            return {
                "product_name": document.querySelector('h1')?.innerText || "N/A",
                "brand": document.querySelector('[data-slot="brand-name"]')?.innerText || "N/A",
                "recommended_seller_price": document.querySelector('.price-main')?.innerText || "N/A",
                "warranty": "12 months warranty"
            }
        }''')
        
        await browser.close()
        
        # Format the intercepted API data
        formatted_offers = []
        if api_data:
            for item in api_data:
                formatted_offers.append({
                    "seller_name": item.get("store_name"),
                    "price": item.get("price", {}).get("final_price_formatted"),
                    "warranty": item.get("warranty") or "12 months warranty"
                })

        return {**product_info, "other_offers": formatted_offers}

@app.route('/scrape_btech', methods=['POST'])
def scrape():
    data = request.get_json()
    url = data.get("urls")[0]
    try:
        result = asyncio.run(get_btech_data_robust(url))
        return jsonify({"data": [result], "status": 200, "url": url})
    except Exception as e:
        return jsonify({"error": str(e), "status": 500})

if __name__ == '__main__':
    from waitress import serve
    serve(app, host='0.0.0.0', port=5002)
