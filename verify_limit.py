import requests
import time

URL = "http://localhost:8000/api/search"

def test_rate_limit():
    print("Testing Rate Limit (10/day)...")
    
    # Hit endpoint 12 times (should fail at 11)
    for i in range(1, 13):
        try:
            resp = requests.post(URL, json={"query": f"test {i}"})
            print(f"Request {i}: {resp.status_code}")
            
            if resp.status_code == 429:
                print("✅ 429 Too Many Requests received! Rate limiting is working.")
                return
            elif resp.status_code != 200:
                print(f"❌ Unexpected status: {resp.status_code}")
        except Exception as e:
            print(f"❌ Request failed: {e}")
            
    print("❌ Failed to trigger rate limit after 24 requests.")

if __name__ == "__main__":
    test_rate_limit()
