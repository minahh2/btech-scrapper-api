import asyncio
import re
from flask import Flask, request, jsonify
from playwright.async_api import async_playwright

app = Flask(__name__)

async def get_btech_data_forensic(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # Variable to store results
        forensic_data = {"status": "No API data captured", "raw_response": ""}

        # FORENSIC INTERCEPTOR: Catch the API call and look at everything
        async def handle_api_route(route):
            response = await route.fetch()
            body = await response.text()
            forensic_data["status"] = f"Code {response.status}"
            forensic_data["raw_response"] = body
            await route.continue_()

        # Intercept the specific offers endpoint
        await page.route("**/offers?*", handle_api_route)

        # Navigate
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(5) 
        
        await browser.close()
        return forensic_data

@app.route('/scrape_btech', methods=['POST'])
def scrape():
    data = request.get_json()
    url = data.get("urls")[0]
    try:
        res = asyncio.run(get_btech_data_forensic(url))
        return jsonify(res)
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    from waitress import serve
    serve(app, host='0.0.0.0', port=5002)
