from flask import Flask, request, jsonify
from curl_cffi import requests
from bs4 import BeautifulSoup
import time
import random
import logging
import re

# Setup minimal logging
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# Hardcoded schema for B.TECH to avoid file read errors in Docker
BTECH_SCHEMA = {
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
        {"name": "number_of_other_offers", "selector": "div.px-small.pt-small.flex.justify-between.items-center span.text-xsmall.font-medium.text-secondarySupportiveD3", "type": "text"}
    ]
}

def fetch_btech_simple(url):
    debug_info = {}
    start_total = time.time()

    # Small random jitter to prevent basic rate limits
    time.sleep(random.uniform(0.5, 1.5))
    
    session = requests.Session(impersonate="chrome120")

    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }

    start_html = time.time()
    response = session.get(url, headers=headers, timeout=15)
    debug_info["html_fetch_time"] = round(time.time() - start_html, 2)
    response.raise_for_status()

    # Parse HTML
    soup = BeautifulSoup(response.text, 'html.parser')
    extracted_data = {}
    
    # Dynamically extract every field exactly matching the schema
    for field in BTECH_SCHEMA['fields']:
        field_name = field['name']
        selector = field['selector']
        element = soup.select_one(selector)
        extracted_data[field_name] = element.text.strip() if element else ""
        
    # Basic fallbacks for critical fields just in case the CSS selectors miss
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

    debug_info["total_time"] = round(time.time() - start_total, 2)

    # Combine everything perfectly matching the schema (excluding other_offers)
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
        "number_of_other_offers": extracted_data.get("number_of_other_offers", ""),
        "other_offers": [],  # INTENTIONALLY BLANK to maximize performance and avoid AWS bans
        "DEBUG_INFO": debug_info
    }

    return data


@app.route('/scrape', methods=['POST'])
def scrape_btech():
    try:
        data = request.json
        url_input = data.get('urls') or data.get('url')
        
        if isinstance(url_input, list):
            url = url_input[0] if url_input else ""
        else:
            url = url_input
            
        if not url:
            return jsonify([{"status": 400, "url": "", "data": [], "error": "URL is required"}]), 400
            
        result = fetch_btech_simple(url)

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
    app.run(host="0.0.0.0", port=5002, debug=False, threaded=True)
