import os
import time
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

USERNAME = "ZAKIbg"
BGG_API_TOKEN = os.environ["BGG_API_TOKEN"]

COLLECTION_URL = "https://boardgamegeek.com/xmlapi2/collection"
THING_URL = "https://boardgamegeek.com/xmlapi2/thing"
PLAYS_URL = "https://boardgamegeek.com/xmlapi2/plays"

JSON_FILE = "bgg_collection.json"


def bgg_get(url, params):
    headers = {
        "Authorization": f"Bearer {BGG_API_TOKEN}",
        "User-Agent": "ZAKIbg-sync/5.0"
    }

    while True:
        r = requests.get(url, params=params, headers=headers)

        if r.status_code == 202:
            time.sleep(5)
            continue

        if r.status_code == 429:
            time.sleep(60)
            continue

        r.raise_for_status()
        return r.text


# ========================
# collection（stats付き）
# ========================
def fetch_collection():
    xml_text = bgg_get(
        COLLECTION_URL,
        {
            "username": USERNAME,
            "own": 1,
            "stats": 1
        }
    )

    root = ET.fromstring(xml_text)
    items = []

    for item in root.findall("item"):
        stats_node = item.find("stats")
        rating = None
        numplays = 0

        if stats_node is not None:
            rating_node = stats_node.find("rating")
            numplays_node = stats_node.find("numplays")

            if rating_node is not None:
                val = rating_node.attrib.get("value")
                if val and val != "N/A":
                    rating = float(val)

            if numplays_node is not None:
                numplays = int(numplays_node.attrib.get("value", 0))

        items.append({
            "objectid": item.attrib["objectid"],
            "name": item.find("name").text,
            "collection_stats": {
                "rating": rating,
                "numplays": numplays
            }
        })

    return items


def fetch_thing(game_id):
    xml_text = bgg_get(THING_URL, {"id": game_id, "stats": 1})
    root = ET.fromstring(xml_text)
    item = root.find("item")

    designers = [
        l.attrib["value"]
        for l in item.findall("link")
        if l.attrib.get("type") == "boardgamedesigner"
    ]

    mechanics = [
        l.attrib["value"]
        for l in item.findall("link")
        if l.attrib.get("type") == "boardgamemechanic"
    ]

    categories = [
        l.attrib["value"]
        for l in item.findall("link")
        if l.attrib.get("type") == "boardgamecategory"
    ]

    weight_node = item.find("statistics/ratings/averageweight")
    weight = float(weight_node.attrib["value"]) if weight_node is not None else None

    return designers, mechanics, categories, weight


def fetch_and_aggregate_plays():
    page = 1
    plays_dict = {}

    while True:
        xml_text = bgg_get(
            PLAYS_URL,
            {"username": USERNAME, "page": page}
        )

        root = ET.fromstring(xml_text)
        total = int(root.attrib.get("total", 0))
        plays = root.findall("play")

        if not plays:
            break

        for play in plays:
            date_str = play.attrib.get("date")
            quantity = int(play.attrib.get("quantity", 1))
            item = play.find("item")
            if item is None:
                continue

            gid = item.attrib["objectid"]

            if gid not in plays_dict:
                plays_dict[gid] = {
                    "last_date": None,
                    "last_quantity": 0,
                    "total_plays": 0
                }

            plays_dict[gid]["total_plays"] += quantity

            if date_str:
                d = datetime.strptime(date_str, "%Y-%m-%d")
                last = plays_dict[gid]["last_date"]

                if last is None or d > last:
                    plays_dict[gid]["last_date"] = d
                    plays_dict[gid]["last_quantity"] = quantity

        if page * 100 >= total:
            break

        page += 1

    for gid in plays_dict:
        if plays_dict[gid]["last_date"]:
            plays_dict[gid]["last_date"] = plays_dict[gid]["last_date"].strftime("%Y-%m-%d")

    return plays_dict


def main():

    if os.path.exists(JSON_FILE):
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            local_data = json.load(f)
    else:
        local_data = []

    local_dict = {g["objectid"]: g for g in local_data}
    local_ids = set(local_dict.keys())

    remote_items = fetch_collection()
    remote_ids = {g["objectid"] for g in remote_items}

    new_ids = remote_ids - local_ids
    removed_ids = local_ids - remote_ids

    for rid in removed_ids:
        del local_dict[rid]

    for item in remote_items:
        gid = item["objectid"]

        if gid in new_ids:
            designers, mechanics, categories, weight = fetch_thing(gid)
            local_dict[gid] = {
                "objectid": gid,
                "name": item["name"],
                "designers": designers,
                "mechanics": mechanics,
                "categories": categories,
                "weight": weight
            }

        # collection_statsは毎回更新
        local_dict[gid]["collection_stats"] = item["collection_stats"]

    plays_dict = fetch_and_aggregate_plays()

    for gid, game in local_dict.items():
        if gid in plays_dict:
            p = plays_dict[gid]
            game["lastplays"] = {
                "date": p["last_date"],
                "quantity": p["last_quantity"],
                "total_plays": p["total_plays"]
            }
        else:
            game["lastplays"] = None

    final_list = sorted(local_dict.values(), key=lambda x: x["name"].lower())

    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)

    print("✅ Sync complete with stats")


if __name__ == "__main__":
    main()
