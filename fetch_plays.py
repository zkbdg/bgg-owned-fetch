import requests
import xml.etree.ElementTree as ET
import time

username = "ZAKIbg"
url = f"https://boardgamegeek.com/xmlapi2/plays?username={username}&subtype=boardgame&page=1"

while True:
    r = requests.get(url)

    if r.status_code == 202:
        print("BGG processing... waiting")
        time.sleep(5)
        continue

    if r.status_code != 200:
        print("Error:", r.status_code)
        exit(1)

    if not r.content.strip():
        print("Empty response")
        time.sleep(5)
        continue

    break

root = ET.fromstring(r.content)
