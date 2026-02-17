import requests
import xml.etree.ElementTree as ET
import time
from collections import defaultdict

username = "ZAKIbg"

latest_by_game = {}

page = 1
while True:
    url = f"https://boardgamegeek.com/xmlapi2/plays?username={username}&subtype=boardgame&page={page}"
    r = requests.get(url)

    # 202対策
    if r.status_code == 202:
        time.sleep(5)
        continue

    root = ET.fromstring(r.content)
    plays = root.findall("play")

    if not plays:
        break

    for play in plays:
        date = play.get("date")
        item = play.find("item")
        game_id = item.get("objectid")
        name = item.get("name")

        if game_id not in latest_by_game:
            latest_by_game[game_id] = (name, date)
        else:
            # 日付比較
            if date > latest_by_game[game_id][1]:
                latest_by_game[game_id] = (name, date)

    page += 1

# 結果表示
for game_id, (name, date) in latest_by_game.items():
    print(f"{name}: {date}")
