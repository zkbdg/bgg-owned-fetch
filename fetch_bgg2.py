import os
import requests
import time
import xml.etree.ElementTree as ET
import json

USERNAME = "zakibg"
BGG_COOKIE = os.environ["BGG_COOKIE"]

API_THING = "https://boardgamegeek.com/xmlapi2/thing"

SLEEP_BETWEEN_CALLS = 1
SLEEP_ON_429 = 60


# ====================================
# XML → dict（再帰）
# ====================================
def xml_to_dict(element):
    d = {}
    if element.attrib:
        d.update(element.attrib)

    children = list(element)
    if children:
        for child in children:
            child_dict = xml_to_dict(child)
            if child.tag in d:
                if not isinstance(d[child.tag], list):
                    d[child.tag] = [d[child.tag]]
                d[child.tag].append(child_dict)
            else:
                d[child.tag] = child_dict
    else:
        text = element.text.strip() if element.text else None
        if text:
            d["value"] = text

    return d


# ====================================
# thing 詳細取得
# ====================================
def fetch_thing_info(game_id):
    params = {"id": game_id, "stats": 1}

    while True:
        resp = requests.get(API_THING, params=params)

        if resp.status_code == 429:
            print(f"[{game_id}] Rate limited → wait {SLEEP_ON_429}s")
            time.sleep(SLEEP_ON_429)
            continue

        if resp.status_code == 202:
            print(f"[{game_id}] Waiting for thing data...")
            time.sleep(5)
            continue

        resp.raise_for_status()
        break

    root = ET.fromstring(resp.content)
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

    weight_elem = item.find("statistics/ratings/averageweight")
    weight = weight_elem.attrib["value"] if weight_elem is not None else None

    return designers, mechanics, categories, weight


# ====================================
# plays取得
# ====================================
def fetch_latest_plays():
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Cookie": BGG_COOKIE
    }

    latest = {}
    page = 1

    while True:
        url = f"https://boardgamegeek.com/xmlapi2/plays?username={USERNAME}&subtype=boardgame&page={page}"
        resp = requests.get(url, headers=headers)

        if resp.status_code == 202:
            time.sleep(5)
            continue

        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        plays = root.findall("play")
        if not plays:
            break

        for play in plays:
            date = play.get("date")
            item = play.find("item")
            if item is None:
                continue

            game_id = item.get("objectid")
            if not game_id or not date:
                continue

            if game_id not in latest or date > latest[game_id]:
                latest[game_id] = date

        page += 1
        time.sleep(1)

    return latest


# ====================================
# collection取得
# ====================================
def fetch_collection(latest_plays):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Cookie": BGG_COOKIE
    }

    url = f"https://boardgamegeek.com/xmlapi2/collection?username={USERNAME}&own=1&stats=1"

    for _ in range(15):
        resp = requests.get(url, headers=headers)

        if resp.status_code == 202:
            time.sleep(5)
            continue

        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        break
    else:
        raise Exception("BGG collection timeout")

    games = []

    for item in root.findall("item"):
        game = xml_to_dict(item)
        game["status"] = "owned"

        game_id = game.get("objectid")
        game["lastplay"] = latest_plays.get(game_id)

        games.append(game)

    return games


# ====================================
# 実行
# ====================================

# 旧JSON読み込み
try:
    with open("bgg_collection.json", "r", encoding="utf-8") as f:
        old_data = json.load(f)
except FileNotFoundError:
    old_data = []

old_map = {g["objectid"]: g for g in old_data}

latest_plays = fetch_latest_plays()
collection = fetch_collection(latest_plays)

updated_count = 0

for game in collection:
    old = old_map.get(game["objectid"])

    # 旧データから詳細を引き継ぐ
    if old:
        for key in ["designers", "mechanics", "categories", "weight"]:
            if key in old:
                game[key] = old[key]

    # 差分判定
    if not all(k in game for k in ["designers", "mechanics", "categories", "weight"]):
        designers, mechanics, categories, weight = fetch_thing_info(game["objectid"])
        game["designers"] = designers
        game["mechanics"] = mechanics
        game["categories"] = categories
        game["weight"] = weight
        updated_count += 1
        print(f"Thing fetched → {game['name']['value']}")
        time.sleep(SLEEP_BETWEEN_CALLS)

# 保存
with open("bgg_collection.json", "w", encoding="utf-8") as f:
    json.dump(collection, f, ensure_ascii=False, indent=2)

print(f"Finished. Thing updates this run: {updated_count}")
