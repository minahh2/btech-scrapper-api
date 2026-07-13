from flask import Flask, request, jsonify
from playwright.async_api import async_playwright
import asyncio
from bs4 import BeautifulSoup
import re
import json
import logging
import urllib.parse
import requests
import time

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

def extract_offers_via_api(url, jwt_token):
    match = re.search(r'/p/([^/?]+)', url)
    if not match:
        return []
    product_id = match.group(1)
    
    api_url = f"https://retail-online-prod.btech.com/api/v1/green/discovery/api/v1/products/{product_id}/offers?city_id=31&area_id=88"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://btech.com",
        "Referer": "https://btech.com/",
        "Authorization": f"Bearer {jwt_token}",
    }
    
    try:
        response = requests.get(api_url, headers=headers, timeout=15)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        logging.error(f"Error fetching API directly: {e}")
        
    return []

async def fetch_btech_data(url: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-gpu',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled'
            ]
        )
        context = await browser.new_context(
            viewport={'width': 800, 'height': 600},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        await page.route("**/*.{png,jpg,jpeg,webp,gif,svg,woff2,woff,ttf,css,mp4,webm}", lambda route: route.abort())

        debug_info = {
            "jwt_found": False,
            "api_offers_count": 0,
            "goto_time": 0
        }

        try:
            start_time = time.time()
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            debug_info["goto_time"] = round(time.time() - start_time, 2)
            
            cookies = await context.cookies()
            jwt_token = None
            for c in cookies:
                if c['name'] == 'btech-auth-session':
                    try:
                        decoded_val = urllib.parse.unquote(c['value'])
                        auth_data = json.loads(decoded_val)
                        jwt_token = auth_data.get("JWT")
                        break
                    except Exception as e:
                        logging.error(f"Error parsing cookie: {e}")

            api_offers_data = []
            if jwt_token:
                debug_info["jwt_found"] = True
                api_offers_data = extract_offers_via_api(url, jwt_token)
                if api_offers_data:
                    debug_info["api_offers_count"] = len(api_offers_data)

            html = await page.content()
            soup = BeautifulSoup(html, 'html.parser')
            
            product_name = ""
            brand = ""
            recommended_seller_name = ""
            recommended_seller_price = ""

            h1 = soup.find('h1')
            if h1:
                product_name = h1.text.strip()
                try:
                    brand = product_name.split()[0]
                except:
                    pass

            seller_divs = soup.find_all('div', class_='flex flex-row items-center gap-2')
            for div in seller_divs:
                if "Sold by" in div.text:
                    recommended_seller_name = div.text.strip()
                    break

            price_spans = soup.find_all('span', class_='text-bukra-price')
            for span in price_spans:
                if "EGP" in span.text:
                    recommended_seller_price = span.text.replace("EGP", "").strip()
                    break
                    
            if not recommended_seller_price:
                 price_wrapper = soup.find('div', class_=lambda c: c and 'price' in c.lower())
                 if price_wrapper:
                     match = re.search(r'([\d,]+)\s*EGP', price_wrapper.text)
                     if match:
                         recommended_seller_price = match.group(1).strip()

            other_offers = []
            for item in api_offers_data:
                try:
                    price_val = item.get("price", {}).get("final_price_formatted", "")
                    if not price_val:
                        price_val = str(item.get("price", {}).get("final_price", ""))
                    
                    offer = {
                        "seller_name": "Sold by " + item.get("seller_name", ""),
                        "price": price_val,
                        "positive_reviews": "",
                        "rating": "",
                        "delivery_time": item.get("delivery_date", ""),
                        "is_fulfilled_by_btech": item.get("is_fulfilled_by_btech", False),
                        "warranty": item.get("warranty", "")
                    }
                    other_offers.append(offer)
                except Exception as e:
                    logging.error(f"Error parsing offer item: {e}")

            data = {
                "product_name": product_name,
                "brand": brand,
                "recommended_seller_price": recommended_seller_price,
                "recommended_seller_name": recommended_seller_name,
                "recommended_seller_rating": "",
                "recommended_seller_positive_reviews": "",
                "extra_disc": "",
                "warranty": "12 months warranty",
                "is_seller_amazon": "",
                "ratings_count": "",
                "rating": "",
                "number_of_other_offers": str(len(other_offers)) if other_offers else "",
                "other_offers": other_offers,
                "DEBUG_INFO": debug_info
            }

            return data

        finally:
            await browser.close()


@app.route('/scrape', methods=['POST'])
def scrape_btech():
    try:
        data = request.json
        url = data.get('url')
        
        if not url:
            return jsonify([{"status": 400, "url": "", "data": [], "error": "URL is required"}]), 400
            
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(fetch_btech_data(url))
        loop.close()

        return jsonify([{
            "status": 200,
            "url": url,
            "data": [result],
            "error": ""
        }])
    except Exception as e:
        logging.error(f"Error during scrape: {e}")
        return jsonify([{
            "status": 500,
            "url": request.json.get('url', ''),
            "data": [],
            "error": str(e)
        }]), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001, debug=True)
