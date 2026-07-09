import requests
import re
from flask import Flask, request, jsonify

app = Flask(__name__)

# REPLACE THIS WITH YOUR CURRENT TOKEN IF IT EXPIRES
# To refresh: Copy the "Bearer" token from your browser Network tab (Copy as cURL)
BEARER_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI2MjE2NmI5Zi03Y2FmLTQ2MGEtODYwOS1jYzUwMmJlOTU1OTQiLCJzZXNzaW9uX2lkIjoiOTQ5YjBkZWYtOTQxMS00NjQ2LTk2YjUtODFhM2FiYTQxMjQxIiwiaWF0IjoxNzgzNTkxNTYxLCJleHAiOjE4MTUxMjc1NjEsImlzcyI6ImN5cGhlci1pZGVudGl0eS1zZXJ2aWNlIiwiYXVkIjoiZ3Vlc3QiLCJ0eXBlIjoiZ3Vlc3RfYWNjZXNzX3Rva2VuIiwiaXNfZ3Vlc3QiOnRydWUsInNlc3Npb25fdG9rZW4iOiJvcnlfc3RfQ3pGWVNiQ3FqdXZGWTVicW9NeXlNblhmNzJwNzBOY0kifQ.gyzBz4-M4UvFn915q4BMIJaaSOBP9vO1FIg1en-X0JQ"

@app.route('/scrape_btech', methods=['POST'])
def scrape():
    data = request.get_json()
    url = data.get("urls")[0]
    
    # Extract product ID from URL using Regex
    product_id_match = re.search(r'/p/([a-zA-Z0-9-]+)', url)
    if not product_id_match:
        return jsonify({"error": "Could not extract product ID from URL"})
    
    product_id = product_id_match.group(1)
    
    # Direct API request
    api_url = f"https://retail-online-prod.btech.com/api/v1/green/discovery/api/v1/products/{product_id}/offers?city_id=31&area_id=88"
    
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {BEARER_TOKEN}',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36',
        'X-Platform': 'web'
    }

    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            offers_data = response.json()
            
            # Format to match your required structure
            formatted_offers = []
            for item in offers_data:
                formatted_offers.append({
                    "seller_name": item.get("store_name"),
                    "price": item.get("price", {}).get("final_price_formatted"),
                    "warranty": item.get("warranty") or "No warranty"
                })
            
            return jsonify({
                "url": url,
                "status": 200,
                "other_offers": formatted_offers
            })
        else:
            return jsonify({"error": f"API returned status {response.status_code}", "raw": response.text})
            
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    from waitress import serve
    print("🚀 API-Native B.TECH scraper running...")
    serve(app, host='0.0.0.0', port=5002)
