import os
import requests
import time
import json
import xml.etree.ElementTree as ET

USERNAME = os.environ["BGG_USERNAME"]

COLLECTION_URL = f"https://boardgamegeek.com/xmlapi2/collection?username={USERNAME}&own=1&wishlist=1&preordered=1&stats=1"
PLAYS_URL = f"https://boardgamegeek.com/xmlapi2/plays?username={USERNAME}"
THING_URL = "https://boardgamegeek.com/xmlapi2/thing?id={ids}&stats=1"

COLLECTION_FILE = "bgg_collection.json"
PLAYS_FILE = "bgg_plays.json"
THING_FILE = "bgg_thing.json"

# ------------------------
# Utility
# ------------------------

def fetch_xml(url):
    while True:
        r = requests.get(url)
        if r.status_code == 202:
            time.sleep(2)
            continue
        r.raise_for_status()
        return ET.fromstring(r.content)

# ------------------------
# 1️⃣ COLLECTION (フル同期)
# ------------------------

def fetch_collection():
    root = fetch_xml(COLLECTION_URL)
    collection = []

    for item in root.findall("item"):
        game = {
            "id": item.get("objectid"),
            "name": item.find("name").text,
            "yearpublished": item.findtext("yearpublished"),
            "numplays": item.findtext("numplays"),
            "status": item.find("status").attrib,
            "stats": {
                "rating": {
                    "value": item.find("stats/rating").attrib.get("value")
                }
            }
        }

        # rank
        rank = item.find("stats/rating/ranks/rank")
        if rank is not None:
            game["stats"]["rank"] = rank.attrib.get("value")

        collection.append(game)

    return collection

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ------------------------
# 2️⃣ PLAYS (全件取得)
# ------------------------

def fetch_all_plays():
    all_plays = []
    page = 1

    while True:
        url = f"{PLAYS_URL}&page={page}"
        root = fetch_xml(url)

        plays = root.findall("play")
        if not plays:
            break

        for play in plays:
            entry = {
                "id": play.get("id"),
                "date": play.get("date"),
                "quantity": play.get("quantity"),
                "game_id": play.find("item").get("objectid"),
                "game_name": play.find("item").get("name"),
            }
            all_plays.append(entry)

        page += 1
        time.sleep(1)

    return all_plays

# ------------------------
# 3️⃣ THING (差分取得)
# ------------------------

def load_existing_thing():
    if not os.path.exists(THING_FILE):
        return {}
    with open(THING_FILE, "r", encoding="utf-8") as f:
        return {g["id"]: g for g in json.load(f)}

def fetch_thing_batch(ids):
    url = THING_URL.format(ids=",".join(ids))
    root = fetch_xml(url)

    results = {}
    for item in root.findall("item"):
        results[item.get("id")] = {
            "id": item.get("id"),
            "minplayers": item.findtext("minplayers"),
            "maxplayers": item.findtext("maxplayers"),
            "playingtime": item.findtext("playingtime"),
        }

    return results

def update_thing(collection):
    existing = load_existing_thing()
    collection_ids = [g["id"] for g in collection]

    # 差分対象：
    # ① 未取得ID
    # ② 2024年以降発売
    ids_to_fetch = []

    for g in collection:
        if g["id"] not in existing:
            ids_to_fetch.append(g["id"])
        elif g.get("yearpublished") and int(g["yearpublished"]) >= 2024:
            ids_to_fetch.append(g["id"])

    # 50件ずつ
    for i in range(0, len(ids_to_fetch), 50):
        batch = ids_to_fetch[i:i+50]
        print("Fetching thing:", batch)
        data = fetch_thing_batch(batch)
        existing.update(data)
        time.sleep(2)

    # 所持から外れたもの削除
    existing = {k: v for k, v in existing.items() if k in collection_ids}

    save_json(THING_FILE, list(existing.values()))

# ------------------------
# MAIN
# ------------------------

def main():
    print("Fetching collection...")
    collection = fetch_collection()
    save_json(COLLECTION_FILE, collection)

    print("Fetching plays...")
    plays = fetch_all_plays()
    save_json(PLAYS_FILE, plays)

    print("Updating thing (diff)...")
    update_thing(collection)

    print("Done.")

if __name__ == "__main__":
    main()
