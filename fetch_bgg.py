import os
import requests
import time
import xml.etree.ElementTree as ET
import json

USERNAME = "zakibg"

URL = (
    f"https://boardgamegeek.com/xmlapi2/collection"
    f"?username={USERNAME}"
    f"&own=1"
    f"&stats=1"
    f"&excludesubtype=boardgameexpansion"
)

headers = {
    "User-Agent": "Mozilla/5.0",
    "Cookie": os.environ.get("BGG_COOKIE", "")
}

print("Fetching BGG collection...")

# --- 202 Accepted 対応ポーリング ---
for i in range(20):
    resp = requests.get(URL, headers=headers, timeout=60)

    if resp.status_code == 202 or not resp.text.strip():
        print(f"[{i+1}/20] Waiting for BGG to prepare data...")
        time.sleep(5)
        continue

    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    break
else:
    raise Exception("BGG timeout: data not ready.")

print("Parsing XML...")

games = []

for item in root.findall("item"):

    name_tag = item.find("name")
    year_tag = item.find("yearpublished")
    plays_tag = item.find("numplays")
    stats_tag = item.find("stats")

    rating_value = None
    if stats_tag is not None:
        rating_tag = stats_tag.find("rating")
        if rating_tag is not None:
            rating_value = rating_tag.attrib.get("value")

    game = {
        "id": item.attrib.get("objectid"),
        "name": name_tag.text if name_tag is not None else None,
        "year": year_tag.text if year_tag is not None else None,
        "numplays": int(plays_tag.text) if plays_tag is not None and plays_tag.text.isdigit() else 0,
        "minplayers": stats_tag.attrib.get("minplayers") if stats_tag is not None else None,
        "maxplayers": stats_tag.attrib.get("maxplayers") if stats_tag is not None else None,
        "playingtime": stats_tag.attrib.get("playingtime") if stats_tag is not None else None,
        "rating": rating_value,
    }

    games.append(game)

# --- ソート（プレイ回数降順） ---
games.sort(key=lambda x: x["numplays"], reverse=True)

with open("owned.json", "w", encoding="utf-8") as f:
    json.dump(games, f, ensure_ascii=False, indent=2)

print(f"{len(games)} games saved to owned.json")
