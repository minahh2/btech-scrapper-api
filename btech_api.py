import json
import asyncio
from flask import Flask, request, jsonify
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

app = Flask(__name__)

# Ultra-stealth config
browser_config = BrowserConfig(
    viewport_width=1920,
    viewport_height=1080,
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    headless=True
)

@app.route('/scrape_btech', methods=['POST'])
def scrape():
    data = request.get_json()
    if not data or "urls" not in data:
        return jsonify({"error": "No URL provided"})
    
    url = data.get("urls")[0]
    
    config = CrawlerRunConfig(
        scan_full_page=True,
        page_timeout=30000
    )

    async def run_diagnostic():
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(url=url, config=config)
            
            # SAFE ATTRIBUTE ACCESS
            # We check metadata first, then the object directly
            page_title = "Unknown"
            if hasattr(result, 'metadata') and result.metadata and 'title' in result.metadata:
                page_title = result.metadata['title']
            elif hasattr(result, 'title'):
                page_title = result.title

            return {
                "url": url,
                "status_code": result.status_code,
                "page_title": page_title,
                "content_length": len(result.markdown) if result.markdown else 0,
                # This gives us a safe preview of the HTML to debug why "Sold by" was missing
                "html_preview": result.html[:1500] if result.html else "NO_HTML"
            }

    try:
        data = asyncio.run(run_diagnostic())
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e), "trace": "Make sure you check your result object structure"})

if __name__ == '__main__':
    from waitress import serve
    serve(app, host='0.0.0.0', port=5002)
