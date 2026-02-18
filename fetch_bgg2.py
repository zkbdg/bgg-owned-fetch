import json
import time
import requests
import os
import xml.etree.ElementTree as ET

BGG_API_TOKEN = os.environ.get("BGG_API_TOKEN")
BGG_COOKIE = os.environ.get("BGG_COOKIE")
API_URL = "https://boardgamegeek.com/xmlapi2/thing"

BATCH_SIZE = 10          # 1回で更新するゲーム数（テスト用）
SLEEP_BETWEEN_CALLS = 1  # API呼び出し間隔（秒）
SLEEP_ON_429 = 60        # 429が返った場合の待機時間（秒）


def fetch_thing_info(game_id):
    headers = {}
    cookies = {}

    # トークンがある場合のみ付与
    if BGG_API_TOKEN:
        headers["Authorization"] = f"Bearer {BGG_API_TOKEN}"

    if BGG_COOKIE:
        cookies["bggsession"] = BGG_COOKIE

    params = {
        "id": game_id,
        "stats": 1
    }

    while True:
        resp = requests.get(
            API_URL,
            params=params,
            headers=headers,
            cookies=cookies
        )

        if resp.status_code == 429:
            print(f"[{game_id}] Rate limited → wait {SLEEP_ON_429}s")
            time.sleep(SLEEP_ON_429)
            continue

        if resp.status_code == 202:
            print(f"[{game_id}] Data not ready → wait 5s")
            time.sleep(5)
            continue

        resp.raise_for_status()
        break

    root = ET.fromstring(resp.text)
    item = root.find("item")

    # ✅ 正しい type
    designers = [
        link.attrib["value"]
        for link in item.findall("link")
        if link.attrib.get("type") == "boardgamedesigner"
    ]

    weight_elem = item.find("statistics/ratings/averageweight")
    weight = weight_elem.attrib["value"] if weight_elem is not None else None

    return designers, weight


def main():
    with open("bgg_collection.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    # designers または weight が未取得のものだけ更新
    pending = [
        g for g in data
        if "designers" not in g or not g.get("designers")
        or "weight" not in g or not g.get("weight")
    ]

    print(f"Pending games to update: {len(pending)}")

    batch = pending[:BATCH_SIZE]
    updated = 0

    for game in batch:
        try:
            designers, weight = fetch_thing_info(game["objectid"])

            game["designers"] = designers
            game["weight"] = weight

            updated += 1

            print(
                f"Updated {game['name']['value']} "
                f"→ designers: {designers}, weight: {weight}"
            )

            time.sleep(SLEEP_BETWEEN_CALLS)

        except Exception as e:
            print(
                f"Error fetching {game['name']['value']} "
                f"({game['objectid']}): {e}"
            )

    if updated > 0:
        with open("bgg_collection.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Total updated in this batch: {updated}")


if __name__ == "__main__":
    main()
