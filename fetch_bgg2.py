import json
import time
import requests
import os
import xml.etree.ElementTree as ET

API_URL = "https://boardgamegeek.com/xmlapi2/thing"

BGG_API_TOKEN = os.environ.get("BGG_API_TOKEN")

BATCH_SIZE = 10
SLEEP_BETWEEN_CALLS = 1
SLEEP_ON_429 = 60


def fetch_thing_info(game_id):
    params = {
        "id": game_id,
        "stats": 1,
    }

    # ✅ トークンはクエリパラメータ
    if BGG_API_TOKEN:
        params["api_key"] = BGG_API_TOKEN

    headers = {
        "User-Agent": "bgg-owned-fetch-script/1.0"
    }

    while True:
        resp = requests.get(API_URL, params=params, headers=headers)

        if resp.status_code == 429:
            print(f"[{game_id}] 429 Rate limited → wait {SLEEP_ON_429}s")
            time.sleep(SLEEP_ON_429)
            continue

        if resp.status_code == 202:
            print(f"[{game_id}] 202 Preparing data → wait 5s")
            time.sleep(5)
            continue

        resp.raise_for_status()
        break

    root = ET.fromstring(resp.text)
    item = root.find("item")

    designers = []
    for link in item.findall("link"):
        if link.attrib.get("type") == "boardgamedesigner":
            designers.append(link.attrib.get("value"))

    weight_elem = item.find("statistics/ratings/averageweight")
    weight = weight_elem.attrib.get("value") if weight_elem is not None else None

    return designers, weight


def main():
    with open("bgg_collection.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    pending = [
        g for g in data
        if not g.get("designers")
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
