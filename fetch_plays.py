import os
import requests

USERNAME = "zakibg"
BGG_COOKIE = os.environ.get("BGG_COOKIE")

headers = {
    "User-Agent": "Mozilla/5.0",
    "Cookie": BGG_COOKIE
}

url = f"https://boardgamegeek.com/xmlapi2/collection?username={USERNAME}&own=1&stats=1"

resp = requests.get(url, headers=headers, timeout=60)
resp.raise_for_status()

print(resp.status_code)
