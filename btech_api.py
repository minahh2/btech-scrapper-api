import json
import asyncio
import re
from flask import Flask, request, jsonify
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from bs4 import BeautifulSoup

app = Flask(__name__)
browser_config = BrowserConfig(headless=True)

async def btech_native_click(page, *args, **kwargs):
    await page.wait_for_timeout(3000) 
    btn = page.locator('div[data-slot="card-header"]').first
    if await btn.count() > 0:
        await btn.click(force=True)
        await page.wait_for_timeout(4000) # Ensure full hydration

@app.route('/scrape_btech', methods=['POST'])
def scrape():
    data = request.get_json()
    url = data.get("urls")[0]
    
    async def run_scraper():
        async with AsyncWebCrawler(config=browser_config) as crawler:
            crawler.crawler_strategy.set_hook("after_goto", btech_native_click)
            result = await crawler.arun(url=url)
            
            # THE "TRUTH SERUM" PARSER
            soup = BeautifulSoup(result.html, 'html.parser')
            
            # Get everything in the body
            body_text = soup.body.get_text(" ", strip=True)
            
            # Find all prices (simple regex for EGP/LE)
            prices = re.findall(r'[\d,]+\s*(?:LE|EGP)', body_text)
            
            # Find everything that looks like "Sold by ..."
            # We look for "Sold by" and take the next 3 words
            all_matches = re.findall(r'Sold\s*by\s*[\w\s]{1,20}', body_text, re.IGNORECASE)
            
            return {
                "status": "Success",
                "total_text_length": len(body_text),
                "sold_by_found": all_matches,
                "prices_found": prices,
                "raw_body_preview": body_text[:1000] # See exactly what we are reading
            }

    try:
        return jsonify(asyncio.run(run_scraper()))
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    from waitress import serve
    serve(app, host='0.0.0.0', port=5002)
