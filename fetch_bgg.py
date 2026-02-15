import os
import requests
import time
import xml.etree.ElementTree as ET
import json

USERNAME = "zakibg"

URL = f"https://boardgamegeek.com/xmlapi2/collection?username={USERNAME}&own=1&stats=1&excludesubtype=boardgameexpansion"

headers = {
    "User-Agent": "Mozilla/5.0",
    "Cookie": os.environ["BGG_COOKIE"]
}

print("Fetching BGG collection...")

for i in range(15):
    resp = requests.get(URL, headers=headers, timeout=60)

    if resp.status_code == 202 or not resp.text.strip():
        print(f"[{i+1}/15] Waiting...")
        time.sleep(5)
        continue

    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    break
else:
    raise Exception("BGG timeout")

games = []

for item in root.findall("item"):
    games.append({
        "id": item.attrib.get("objectid"),
        "name": item.find("name").attrib.get("value") if item.find("name") is not None else None,
        "year": item.find("yearpublished").attrib.get("value") if item.find("yearpublished") is not None else None,
        "numplays": item.find("numplays").attrib.get("value") if item.find("numplays") is not None else "0",
    })

with open("owned.json", "w", encoding="utf-8") as f:
    json.dump(games, f, ensure_ascii=False, indent=2)

print(f"{len(games)} games saved.")
