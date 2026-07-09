import asyncio
from flask import Flask, request, jsonify
from playwright.async_api import async_playwright

app = Flask(__name__)

async def get_btech_data_sync(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        await page.goto(url, wait_until="domcontentloaded")
        
        # Define the API pattern we want to catch
        api_pattern = "**/offers?*"
        
        # Start the "Spy" - wait_for_response returns a promise/coroutine
        # We start this BEFORE the click
        response_future = page.wait_for_response(api_pattern, timeout=15000)
        
        # Perform the Click
        btn = page.locator('div[data-slot="card-header"]').first
        if await btn.count() > 0:
            await btn.click(force=True)
            
            # Wait for the API response to arrive
            response = await response_future
            api_data = await response.json()
        else:
            api_data = []

        await browser.close()
        return api_data

@app.route('/scrape_btech', methods=['POST'])
def scrape():
    data = request.get_json()
    url = data.get("urls")[0]
    
    try:
        offers = asyncio.run(get_btech_data_sync(url))
        
        formatted_offers = [
            {
                "seller_name": off.get("store_name"),
                "price": off.get("price", {}).get("final_price_formatted"),
                "warranty": off.get("warranty") or "12 months warranty"
            } for off in (offers if isinstance(offers, list) else [])
        ]
        
        return jsonify({
            "status": 200,
            "url": url,
            "other_offers": formatted_offers
        })
    except Exception as e:
        return jsonify({"error": str(e), "status": 500})

if __name__ == '__main__':
    from waitress import serve
    serve(app, host='0.0.0.0', port=5002)
