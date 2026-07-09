import requests
import re
from flask import Flask, request, jsonify

app = Flask(__name__)

# You only need the token. Headers are standard.
# If this fails with 401/403, just refresh the token in your cURL once more.
BEARER_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI2MjE2NmI5Zi03Y2FmLTQ2MGEtODYwOS1jYzUwMmJlOTU1OTQiLCJzZXNzaW9uX2lkIjoiOTQ5YjBkZWYtOTQxMS00NjQ2LTk2YjUtODFhM2FiYTQxMjQxIiwiaWF0IjoxNzgzNTkxNTYxLCJleHAiOjE4MTUxMjc1NjEsImlzcyI6ImN5cGhlci1pZGVudGl0eS1zZXJ2aWNlIiwiYXVkIjoiZ3Vlc3QiLCJ0eXBlIjoiZ3Vlc3RfYWNjZXNzX3Rva2VuIiwiaXNfZ3Vlc3QiOnRydWUsInNlc3Npb25fdG9rZW4iOiJvcnlfc3RfQ3pGWVNiQ3FqdXZGWTVicW9NeXlNblhmNzJwNzBOY0kifQ.gyzBz4-M4UvFn915q4BMIJaaSOBP9vO1FIg1en-X0JQ"

@app.route('/scrape_btech', methods=['POST'])
def scrape():
    data = request.get_json()
    url = data.get("urls")[0]
    
    # Extract PID
    pid_match = re.search(r'/p/([a-zA-Z0-9-]+)', url)
    if not pid_match:
        return jsonify({"error": "Invalid URL format"})
    pid = pid_match.group(1)

    # API Endpoint (The same one from your working cURL)
    api_url = f"https://retail-online-prod.btech.com/api/v1/green/discovery/api/v1/products/{pid}/offers?city_id=31&area_id=88"
    
    headers = {
        'Authorization': f'Bearer {BEARER_TOKEN}',
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36'
    }

    try:
        # Simple, fast, non-browser request
        response = requests.get(api_url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            offers_data = response.json()
            formatted_offers = [
                {
                    "seller_name": off.get("store_name"),
                    "price": off.get("price", {}).get("final_price_formatted"),
                    "warranty": off.get("warranty") or "12 months warranty"
                } for off in offers_data
            ]
            
            return jsonify({
                "data": [{
                    "product_name": "Product Details", # We can add a simple scraper for this if needed
                    "other_offers": formatted_offers
                }],
                "status": 200
            })
        else:
            return jsonify({"error": f"API Blocked with status {response.status_code}", "raw": response.text})
            
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    from waitress import serve
    serve(app, host='0.0.0.0', port=5002)
