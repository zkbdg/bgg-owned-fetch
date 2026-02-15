import requests
import time
import xml.etree.ElementTree as ET
import json

USERNAME = "zakibg"
URL = f"https://boardgamegeek.com/xmlapi2/collection?username={USERNAME}&own=1&stats=1"

headers = {
    "User-Agent": "Mozilla/5.0"
}

print("Fetching BGG collection...")

for i in range(15):
    resp = requests.get(URL, headers=headers, timeout=60)

    if resp.status_code == 202 or not resp.text.strip():
        print(f"[{i+1}/15] Waiting for BGG to prepare data...")
        time.sleep(5)
        continue

    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    break
else:
    raise Exception("BGG did not return data in time.")

games = []

for item in root.findall("item"):
    name_tag = item.find("name")
    year_tag = item.find("yearpublished")
    plays_tag = item.find("numplays")

    games.append({
        "id": item.attrib.get("objectid"),
        "name": name_tag.attrib.get("value") if name_tag is not None else None,
        "year": year_tag.attrib.get("value") if year_tag is not None else None,
        "numplays": plays_tag.attrib.get("value") if plays_tag is not None else "0",
    })

with open("owned.json", "w", encoding="utf-8") as f:
    json.dump(games, f, ensure_ascii=False, indent=2)

print(f"{len(games)} games saved.")
