import requests
import xml.etree.ElementTree as ET
import time
import json
import os

USERNAME = "zakibg"

headers = {
    "User-Agent": "Mozilla/5.0"
}

latest_by_game = {}
page = 1

while True:
    url = f"https://boardgamegeek.com/xmlapi2/plays?username={USERNAME}&subtype=boardgame&page={page}"
    r = requests.get(url, headers=headers)

    if r.status_code == 202:
        time.sleep(5)
        continue

    r.raise_for_status()

    root = ET.fromstring(r.content)
    plays = root.findall("play")

    if not plays:
        break

    for play in plays:
        date = play.get("date")
        item = play.find("item")
        game_id = item.get("objectid")
        name = item.get("name")

        if game_id not in latest_by_game or date > latest_by_game[game_id]["last_play"]:
            latest_by_game[game_id] = {
                "name": name,
                "last_play": date
            }

    page += 1
    time.sleep(1)

os.makedirs("output", exist_ok=True)

with open("output/plays_latest.json", "w", encoding="utf-8") as f:
    json.dump(latest_by_game, f, ensure_ascii=False, indent=2)

print(f"{len(latest_by_game)} games written to output/plays_latest.json")
