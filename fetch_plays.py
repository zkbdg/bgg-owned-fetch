import os
import requests
import xml.etree.ElementTree as ET
import time
import json

USERNAME = "zakibg"
BGG_COOKIE = os.environ["BGG_COOKIE"]

headers = {
    "User-Agent": "Mozilla/5.0",
    "Cookie": BGG_COOKIE
}

latest_by_game = {}
page = 1

while True:
    url = f"https://boardgamegeek.com/xmlapi2/plays?username={USERNAME}&subtype=boardgame&page={page}"
    print(f"Fetching page {page}...")

    r = requests.get(url, headers=headers, timeout=60)

    if r.status_code == 202:
        print("BGG processing, waiting...")
        time.sleep(5)
        continue

    r.raise_for_status()

    if not r.content.strip():
        print("Empty response, stopping.")
        break

    root = ET.fromstring(r.content)
    plays = root.findall("play")

    if not plays:
        print("No more plays found.")
        break

    for play in plays:
        date = play.get("date")
        item = play.find("item")

        if item is None:
            continue

        game_id = item.get("objectid")
        name = item.get("name")

        if not game_id or not date:
            continue

        if game_id not in latest_by_game:
            latest_by_game[game_id] = {
                "name": name,
                "last_play": date
            }
        else:
            if date > latest_by_game[game_id]["last_play"]:
                latest_by_game[game_id]["last_play"] = date

    page += 1
    time.sleep(1)

# リポジトリ直下に保存
with open("plays_latest.json", "w", encoding="utf-8") as f:
    json.dump(latest_by_game, f, ensure_ascii=False, indent=2)

print(f"{len(latest_by_game)} games saved to plays_latest.json")
