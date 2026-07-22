from flask import Flask, request, jsonify
from curl_cffi import requests
from bs4 import BeautifulSoup
import time
import logging
import json
import urllib.parse
import re

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

def extract_data(soup, schema):
    result = {}
    for field in schema.get('fields', []):
        if field.get('type') == 'text':
            elements = soup.select(field.get('selector', ''))
            if elements:
                result[field['name']] = elements[0].get_text(strip=True)
            else:
                result[field['name']] = None
        elif field.get('type') == 'list':
            list_results = []
            elements = soup.select(field.get('selector', ''))
            for element in elements:
                item_data = {}
                for subfield in field.get('fields', []):
                    sub_elements = element.select(subfield.get('selector', ''))
                    if sub_elements:
                        item_data[subfield['name']] = sub_elements[0].get_text(strip=True)
                    else:
                        item_data[subfield['name']] = None
                list_results.append(item_data)
            result[field['name']] = list_results
    return result

def extract_product_id(url):
    try:
        # e.g., https://btech.com/en/p/5cdab7d8-9613-4ac8-b869-451d8960521b/something
        return url.split('/p/')[1].split('/')[0].split('?')[0]
    except Exception:
        return None

@app.route('/scrape', methods=['POST'])
def scrape():
    data = request.get_json()
    if not data:
         return jsonify({"error": "No JSON payload received"}), 400
         
    urls = data.get("urls")
    schema = data.get("schema")

    if not isinstance(urls, list) or not isinstance(schema, dict):
        return jsonify({"error": "Invalid input. 'urls' must be a list, 'schema' must be a dict."}), 400

    results = []
    
    # We create a single persistent session which is amazing for anti-bot
    session = requests.Session(impersonate="chrome120")
    
    for url in urls:
        try:
            logging.info(f"Fetching {url}")
            
            # 1. Fetch main HTML page to get the schema fields and the Auth Cookie
            res = session.get(url, timeout=15)
            
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                extracted_data = extract_data(soup, schema)
                
                # 2. Extract JWT token from the newly assigned cookie
                jwt_token = None
                auth_cookie = session.cookies.get('btech-auth-session')
                if auth_cookie:
                    try:
                        decoded_cookie = urllib.parse.unquote(auth_cookie)
                        jwt_token = json.loads(decoded_cookie).get('JWT')
                    except Exception as e:
                        logging.warning(f"Could not parse auth cookie: {e}")
                
                # 3. If we have the token, hit the internal API!
                sellers_found = []
                product_id = extract_product_id(url)
                
                if jwt_token and product_id:
                    logging.info("JWT Token found, hitting internal offers API...")
                    api_url = f"https://retail-online-prod.btech.com/api/v1/green/discovery/api/v1/products/{product_id}/offers?city_id=31&area_id=88"
                    
                    headers = {
                        'Accept': 'application/json',
                        'Accept-Language': 'en',
                        'Authorization': f'Bearer {jwt_token}',
                        'Origin': 'https://btech.com',
                        'Referer': url,
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    }
                    
                    api_res = session.get(api_url, headers=headers, timeout=10)
                    if api_res.status_code == 200:
                        try:
                            offers_data = api_res.json()
                            for offer in offers_data:
                                seller = offer.get('seller_name', 'Unknown')
                                price_val = offer.get('price', {}).get('final_price_formatted', 'Unknown')
                                price = f"EGP {price_val}" if price_val != 'Unknown' else "Unknown"
                                
                                # B.TECH doesn't provide seller ratings in this JSON, so we default to N/A
                                sellers_found.append({
                                    "seller_name": seller,
                                    "price": price,
                                    "rating": "N/A"
                                })
                            logging.info(f"Successfully extracted {len(sellers_found)} offers from API!")
                        except Exception as e:
                            logging.error(f"Error parsing API JSON: {e}")
                    else:
                        logging.warning(f"Offers API returned status {api_res.status_code}")
                
                # 4. Integrate offers into extracted_data
                if sellers_found:
                    main_seller = extracted_data.get('recommended_seller_name', '')
                    # Optional: filter out the main seller
                    if main_seller:
                        sellers_found = [s for s in sellers_found if s['seller_name'] != main_seller]
                        
                    extracted_data['other_offers'] = sellers_found
                else:
                    extracted_data['other_offers'] = []
                
                # Number of other offers fix
                if extracted_data['other_offers']:
                    extracted_data['number_of_other_offers'] = str(len(extracted_data['other_offers']))
                    
                results.append({
                    "url": url, 
                    "status": res.status_code, 
                    "data": extracted_data
                })
            else:
                results.append({
                    "url": url, 
                    "status": res.status_code, 
                    "error": f"HTTP Error {res.status_code}"
                })
                
        except Exception as e:
            results.append({
                "url": url, 
                "status": 500, 
                "error": str(e)
            })

    return jsonify(results)

if __name__ == '__main__':
    from waitress import serve
    print("Starting B.TECH CFFI production server with Waitress on port 5002 (Max 8 threads)...")
    serve(app, host='0.0.0.0', port=5002, threads=3)
