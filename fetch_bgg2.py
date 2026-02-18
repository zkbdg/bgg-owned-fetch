import json
import time
import requests
import os
import xml.etree.ElementTree as ET

BGG_API_TOKEN = os.environ.get("BGG_API_TOKEN")
BGG_COOKIE = os.environ.get("BGG_COOKIE")
API_URL = "https://boardgamegeek.com/xmlapi2/thing"

BATCH_SIZE = 10        # 1回で更新するゲーム数
SLEEP_BETWEEN_CALLS = 1  # API呼び出し間隔（秒）
SLEEP_ON_429 = 60       # 429が返った場合の待機時間（秒）

def fetch_thing_info(game_id):
    headers = {"Authorization": f"Bearer {BGG_API_TOKEN}"} if BGG_API_TOKEN else {}
    cookies = {"bggsession": BGG_COOKIE} if BGG_COOKIE else {}
    params = {"id": game_id, "stats": 1}

    while True:
        resp = requests.get(API_URL, params=params, headers=headers, cookies=cookies)
        if resp.status_code == 429:  # Too Many Requests
            print(f"[{game_id}] Rate limited → wait {SLEEP_ON_429}s")
            time.sleep(SLEEP_ON_429)
            continue
        if resp.status_code == 202:  # Preparing data
            print(f"[{game_id}] Data not ready → wait 5s")
            time.sleep(5)
            continue
        resp.raise_for_status()
        break

    root = ET.fromstring(resp.text)
    item = root.find("item")
    designers = [link.attrib["value"] for link in item.findall("link[@type='designer']")]
    weight_elem = item.find("statistics/ratings/averageweight")
    weight = weight_elem.attrib["value"] if weight_elem is not None else None
    return designers, weight

def main():
    with open("bgg_collection.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    # 未取得ゲームだけ抽出
    pending = [g for g in data if "designers" not in g or "weight" not in g]
    print(f"Pending games to update: {len(pending)}")

    batch = pending[:BATCH_SIZE]
    updated = 0

    for game in batch:
        try:
            designers, weight = fetch_thing_info(game["objectid"])
            game["designers"] = designers
            game["weight"] = weight
            updated += 1
            print(f"Updated {game['name']['value']} → designers: {designers}, weight: {weight}")
            time.sleep(SLEEP_BETWEEN_CALLS)
        except Exception as e:
            print(f"Error fetching {game['name']['value']} ({game['objectid']}): {e}")

    if updated > 0:
        with open("bgg_collection.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Total updated in this batch: {updated}")

if __name__ == "__main__":
    main()
