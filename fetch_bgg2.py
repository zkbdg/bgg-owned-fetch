import json
import time
import requests
import os
import xml.etree.ElementTree as ET

BGG_API_TOKEN = os.environ["BGG_API_TOKEN"]  # ← 必須にする（無いと即エラー）
BGG_COOKIE = os.environ.get("BGG_COOKIE")

API_URL = "https://boardgamegeek.com/xmlapi2/thing"

BATCH_SIZE = 18
SLEEP_BETWEEN_CALLS = 1
SLEEP_ON_429 = 60


def fetch_thing_info(game_id):
    headers = {
        "Authorization": f"Bearer {BGG_API_TOKEN}",
        "User-Agent": "ZAKIbg-fetch/1.0"
    }

    cookies = {}
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
            cookies=cookies,
            timeout=30
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

    if item is None:
        raise Exception("No <item> found in response")

    designers = [
        link.attrib["value"]
        for link in item.findall("link")
        if link.attrib.get("type") == "boardgamedesigner"
    ]

    mechanics = [
        link.attrib["value"]
        for link in item.findall("link")
        if link.attrib.get("type") == "boardgamemechanic"
    ]

    categories = [
        link.attrib["value"]
        for link in item.findall("link")
        if link.attrib.get("type") == "boardgamecategory"
    ]

    weight_elem = item.find("statistics/ratings/averageweight")
    weight = weight_elem.attrib["value"] if weight_elem is not None else None

    return designers, weight, mechanics, categories


def main():
    with open("bgg_collection.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    pending = [
        g for g in data
        if "designers" not in g
        or "mechanics" not in g
        or "categories" not in g
        or "weight" not in g
    ]

    print(f"Pending games to update: {len(pending)}")

    batch = pending[:BATCH_SIZE]
    updated = 0

    for game in batch:
        try:
            designers, weight, mechanics, categories = fetch_thing_info(
                game["objectid"]
            )

            game["designers"] = designers
            game["weight"] = weight
            game["mechanics"] = mechanics
            game["categories"] = categories

            updated += 1

            print(
                f"Updated {game['name']['value']} "
                f"→ designers: {len(designers)}, "
                f"mechanics: {len(mechanics)}, "
                f"categories: {len(categories)}, "
                f"weight: {weight}"
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
