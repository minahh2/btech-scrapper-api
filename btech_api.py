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
    url = request.get_json().get("urls")[0]
    
    config = CrawlerRunConfig(
        scan_full_page=True,
        page_timeout=30000
    )

    async def run_diagnostic():
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(url=url, config=config)
            
            # Extract basic diagnostic info
            return {
                "url": url,
                "status_code": result.status_code,
                "page_title": result.title if result.title else "NO_TITLE_FOUND",
                "content_length": len(result.markdown) if result.markdown else 0,
                "html_preview": result.html[:2000] if result.html else "NO_HTML_RETURNED"
            }

    try:
        data = asyncio.run(run_diagnostic())
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    from waitress import serve
    serve(app, host='0.0.0.0', port=5002)
