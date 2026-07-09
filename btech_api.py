import json
import asyncio
from flask import Flask, request, jsonify
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

app = Flask(__name__)

# Realistic browser profile to avoid detection
browser_config = BrowserConfig(
    viewport_width=1920,
    viewport_height=1080,
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    headless=True 
)

@app.route('/scrape_btech', methods=['POST'])
def scrape():
    data = request.get_json()
    url = data.get("urls")[0]
    
    async def run_interceptor():
        async with AsyncWebCrawler(config=browser_config) as crawler:
            # We will use this list to catch the API JSON
            captured_json = []

            async def handle_response(response):
                # Look for the internal B.TECH API that lists offers
                if "offering-count" in response.url or "product" in response.url and response.status == 200:
                    try:
                        content = await response.json()
                        captured_json.append(content)
                    except:
                        pass

            # Setup the crawler
            browser = await crawler.browser_context.new_page()
            browser.on("response", handle_response)
            
            await browser.goto(url)
            
            # Find and click the button
            btn = browser.locator('div[data-slot="card-header"]')
            if await btn.count() > 0:
                await btn.click(force=True)
                await asyncio.sleep(5) # Wait for the network call
            
            return captured_json

    try:
        data = asyncio.run(run_interceptor())
        return jsonify({"intercepted_data": data})
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    from waitress import serve
    serve(app, host='0.0.0.0', port=5002)
