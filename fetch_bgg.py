import requests
import xml.etree.ElementTree as ET
import json
import time

USERNAME = "zakibg"

URL = f"https://boardgamegeek.com/xmlapi2/collection?username={USERNAME}&own=1&stats=1&excludesubtype=boardgameexpansion"

MAX_RETRIES = 30

for attempt in range(MAX_RETRIES):
    print(f"[{attempt+1}/{MAX_RETRIES}] Fetching...")

    resp = requests.get(URL, timeout=60)

    # 202 = まだ生成中
    if resp.status_code == 202:
        print("BGG preparing data... waiting 5 seconds")
        time.sleep(5)
        continue

    resp.raise_for_status()

    if not resp.content.strip():
        print("Empty response, waiting 5 seconds")
        time.sleep(5)
        continue

    break
else:
    raise Exception("BGG API did not respond after retries.")

root = ET.fromstring(resp.content)

games = []

for item in root.findall("item"):
    games.append({
        "id": item.attrib.get("objectid"),
        "name": item.find("name").attrib.get("value") if item.find("name") is not None else None,
        "year": item.find("yearpublished").attrib.get("value") if item.find("yearpublished") is not None else None,
        "numplays": item.find("numplays").attrib.get("value") if item.find("numplays") is not None else "0",
    })

with open("owned_list.json", "w", encoding="utf-8") as f:
    json.dump(games, f, ensure_ascii=False, indent=2)

print(f"{len(games)} games fetched successfully.")
