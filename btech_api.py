from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
import re
import json
import logging
import urllib.parse
import requests
import time

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

def fetch_btech_data(url: str):
    debug_info = {
        "jwt_found": False,
        "api_offers_count": 0,
        "html_fetch_time": 0,
        "api_fetch_time": 0,
        "total_time": 0
    }
    
    start_total = time.time()
    
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }

    # 1. Fetch HTML to get the JWT Cookie and product info
    start_html = time.time()
    try:
        response = session.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except Exception as e:
        logging.error(f"Error fetching HTML: {e}")
        raise Exception(f"Failed to fetch B.TECH HTML: {str(e)}")
        
    debug_info["html_fetch_time"] = round(time.time() - start_html, 2)

    # 2. Extract JWT
    jwt_token = None
    for c in session.cookies:
        if c.name == 'btech-auth-session':
            try:
                decoded_val = urllib.parse.unquote(c.value)
                auth_data = json.loads(decoded_val)
                jwt_token = auth_data.get("JWT")
                break
            except Exception as e:
                logging.error(f"Error parsing cookie: {e}")

    # 3. Extract Product ID from URL
    match = re.search(r'/p/([^/?]+)', url)
    product_id = match.group(1) if match else None

    # 4. Fetch API data if JWT is found
    api_offers_data = []
    if jwt_token and product_id:
        debug_info["jwt_found"] = True
        api_url = f"https://retail-online-prod.btech.com/api/v1/green/discovery/api/v1/products/{product_id}/offers?city_id=31&area_id=88"
        api_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://btech.com",
            "Referer": "https://btech.com/",
            "Authorization": f"Bearer {jwt_token}",
        }
        
        start_api = time.time()
        try:
            api_response = session.get(api_url, headers=api_headers, timeout=10)
            if api_response.status_code == 200:
                api_offers_data = api_response.json()
                debug_info["api_offers_count"] = len(api_offers_data)
        except Exception as e:
            logging.error(f"Error fetching API directly: {e}")
            
        debug_info["api_fetch_time"] = round(time.time() - start_api, 2)

    # 5. Parse HTML with BeautifulSoup
    soup = BeautifulSoup(response.text, 'html.parser')
    
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

    # 6. Parse API Offers
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

    debug_info["total_time"] = round(time.time() - start_total, 2)

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


@app.route('/scrape', methods=['POST'])
def scrape_btech():
    try:
        data = request.json
        # Handle both 'url' and 'urls', and handle if 'urls' is a list
        url_input = data.get('urls') or data.get('url')
        
        if isinstance(url_input, list):
            url = url_input[0] if url_input else ""
        else:
            url = url_input
            
        if not url:
            return jsonify([{"status": 400, "url": "", "data": [], "error": "URL is required"}]), 400
            
        result = fetch_btech_data(url)

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
            "url": request.json.get('url', '') if request.json else '',
            "data": [],
            "error": str(e)
        }]), 500

if __name__ == "__main__":
    # Completely thread-safe since we are using requests!
    app.run(host="0.0.0.0", port=5002, debug=False, threaded=True)
