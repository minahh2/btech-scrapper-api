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
    
    # 0. Protective Jitter: Wait 2-4 seconds before fetching anything
    # This guarantees that even if n8n sends requests back-to-back quickly,
    # we enforce a safe rate-limit so the new IP never gets banned by AWS!
    import random
    time.sleep(random.uniform(2.0, 4.0))
    
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

    # 5. Load Schema and Parse HTML with BeautifulSoup
    schema = {
        "schema": {
            "name": "BtechProductSchema",
            "baseSelector": "body",
            "fields": [
                {"name": "product_name", "selector": "h1.font-regular.text-small.text-absolute-dark", "type": "text"},
                {"name": "brand", "selector": "p.font-medium.text-secondary-supportive-d2.text-xsmall", "type": "text"},
                {"name": "rating", "selector": "[id='acrPopover'] span span a [class='a-size-small a-color-base']", "type": "text"},
                {"name": "ratings_count", "selector": "[id='acrCustomerReviewText']", "type": "text"},
                {"name": "recommended_seller_price", "selector": "span.font-semibold.text-medium", "type": "text"},
                {"name": "recommended_seller_name", "selector": "div.flex.flex-col.divide-y > div.py-large:last-of-type p", "type": "text"},
                {"name": "recommended_seller_rating", "selector": "#aod-pinned-offer .a-icon-alt", "type": "text"},
                {"name": "is_seller_amazon", "selector": "div.w-fit.flex.gap-small.items-center font-medium.rounded-full.bg-neutral-l4.text-absolute-dark.px-xsmall.py-3xsmall.text-xsmall", "type": "text"},
                {"name": "extra_disc", "selector": "[class='flex items-center w-full gap-3xsmall'] [class='font-medium text-xxsmall text-successD1 line-clamp-1 text-start']", "type": "text"},
                {"name": "recommended_seller_positive_reviews", "selector": "#aod-pinned-offer [id^='seller-rating-count-'] span", "type": "text"},
                {"name": "warranty", "selector": "div.flex.items-center.justify-between.py-large.gap-small p.flex.gap-2xsmall", "type": "text"},
                {"name": "number_of_other_offers", "selector": "div.px-small.pt-small.flex.justify-between.items-center span.text-xsmall.font-medium.text-secondarySupportiveD3", "type": "text"},
                {"name": "other_offers", "selector": "#extracted_offers_json", "type": "text"}
            ]
        }
    }
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    extracted_data = {}
    
    # Dynamically extract every field based on the user's schema selectors
    for field in schema.get('schema', {}).get('fields', []):
        field_name = field['name']
        selector = field['selector']
        
        # We handle other_offers separately since it comes from the API
        if field_name in ["other_offers", "number_of_other_offers"]:
            continue
            
        element = soup.select_one(selector)
        extracted_data[field_name] = element.text.strip() if element else ""
        
    # Fallback to basic HTML extraction if schema selectors fail (e.g. they are Amazon selectors)
    if not extracted_data.get('product_name'):
        h1 = soup.find('h1')
        extracted_data['product_name'] = h1.text.strip() if h1 else ""
        
    if not extracted_data.get('brand') and extracted_data.get('product_name'):
        extracted_data['brand'] = extracted_data['product_name'].split()[0]
        
    if not extracted_data.get('recommended_seller_price'):
        price_spans = soup.find_all('span', class_='text-bukra-price')
        for span in price_spans:
            if "EGP" in span.text:
                extracted_data['recommended_seller_price'] = span.text.replace("EGP", "").strip()
                break
        if not extracted_data.get('recommended_seller_price'):
            price_wrapper = soup.find('div', class_=lambda c: c and 'price' in c.lower())
            if price_wrapper:
                 match = re.search(r'([\d,]+)\s*EGP', price_wrapper.text)
                 if match:
                     extracted_data['recommended_seller_price'] = match.group(1).strip()
                     
    if not extracted_data.get('recommended_seller_name'):
        seller_divs = soup.find_all('div', class_='flex flex-row items-center gap-2')
        for div in seller_divs:
            if "Sold by" in div.text:
                extracted_data['recommended_seller_name'] = div.text.strip()
                break

    # 6. Parse API Offers and extract dynamic warranty
    other_offers = []
    api_warranty = ""
    for item in api_offers_data:
        try:
            price_val = item.get("price", {}).get("final_price_formatted", "")
            if not price_val:
                price_val = str(item.get("price", {}).get("final_price", ""))
            
            offer_warranty = item.get("warranty") or ""
            if offer_warranty and not api_warranty:
                api_warranty = offer_warranty  # Grab the first available warranty from API
                
            offer = {
                "seller_name": "Sold by " + item.get("seller_name", ""),
                "price": price_val,
                "positive_reviews": "",
                "rating": "",
                "delivery_time": item.get("delivery_date", ""),
                "is_fulfilled_by_btech": item.get("is_fulfilled_by_btech", False),
                "warranty": offer_warranty
            }
            other_offers.append(offer)
        except Exception as e:
            logging.error(f"Error parsing offer item: {e}")
            
    # If the schema selector didn't find a warranty in HTML, use the one from the API!
    if not extracted_data.get("warranty") and api_warranty:
        extracted_data["warranty"] = api_warranty

    debug_info["total_time"] = round(time.time() - start_total, 2)

    # Combine everything perfectly matching the schema
    data = {
        "product_name": extracted_data.get("product_name", ""),
        "brand": extracted_data.get("brand", ""),
        "rating": extracted_data.get("rating", ""),
        "ratings_count": extracted_data.get("ratings_count", ""),
        "recommended_seller_price": extracted_data.get("recommended_seller_price", ""),
        "recommended_seller_name": extracted_data.get("recommended_seller_name", ""),
        "recommended_seller_rating": extracted_data.get("recommended_seller_rating", ""),
        "is_seller_amazon": extracted_data.get("is_seller_amazon", ""),
        "extra_disc": extracted_data.get("extra_disc", ""),
        "recommended_seller_positive_reviews": extracted_data.get("recommended_seller_positive_reviews", ""),
        "warranty": extracted_data.get("warranty", ""),
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
