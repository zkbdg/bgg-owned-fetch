import os
import requests
import time
import xml.etree.ElementTree as ET
import json

USERNAME = "zakibg"
BGG_API_TOKEN = os.environ["BGG_API_TOKEN"]  # 環境変数にトークンをセット

HEADERS = {
    "User-Agent": "BGGFetcher/1.0",
    "Authorization": f"Bearer {BGG_API_TOKEN}"
}

# ====================================
# XML → dict（再帰的に stats を丸ごと残す）
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
# plays取得（objectid → lastplay）
# ====================================
def fetch_latest_plays():
    print("Fetching plays...")
    latest = {}
    page = 1

    while True:
        url = f"https://boardgamegeek.com/xmlapi2/plays?username={USERNAME}&subtype=boardgame&page={page}"
        resp = requests.get(url, headers=HEADERS, timeout=60)

        if resp.status_code == 202:
            print("Waiting for plays...")
            time.sleep(5)
            continue

        resp.raise_for_status()

        if not resp.text.strip():
            break

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

    print(f"Latest play dates collected: {len(latest)} games")
    return latest

# ====================================
# thing APIで weight / designers 取得
# ====================================
def fetch_thing_info(game_id):
    url = f"https://boardgamegeek.com/xmlapi2/thing?id={game_id}&stats=1"
    resp = requests.get(url, headers=HEADERS, timeout=60)

    if resp.status_code == 202:
        # XML生成に時間がかかる場合は少し待つ
        time.sleep(5)
        resp = requests.get(url, headers=HEADERS, timeout=60)

    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    item = root.find("item")
    if item is None:
        return {}

    info = {}
    # weight
    statistics = item.find("statistics")
    if statistics is not None:
        ratings = statistics.find("ratings")
        if ratings is not None:
            averageweight = ratings.find("averageweight")
            if averageweight is not None and "value" in averageweight.attrib:
                info["weight"] = averageweight.attrib["value"]

    # designers
    designers = [link.attrib["value"] for link in item.findall("link[@type='boardgamedesigner']")]
    info["designers"] = designers

    return info

# ====================================
# BGG コレクション取得
# ====================================
def fetch_collection(latest_plays, owned=False, wishlist=False, preordered=False, prevowned=False):
    if owned:
        url = f"https://boardgamegeek.com/xmlapi2/collection?username={USERNAME}&own=1&stats=1"
        status_label = "owned"
    elif wishlist:
        url = f"https://boardgamegeek.com/xmlapi2/collection?username={USERNAME}&wishlist=1&stats=1"
        status_label = "wishlist"
    elif preordered:
        url = f"https://boardgamegeek.com/xmlapi2/collection?username={USERNAME}&preordered=1&stats=1"
        status_label = "preordered"
    elif prevowned:
        url = f"https://boardgamegeek.com/xmlapi2/collection?username={USERNAME}&prevowned=1&stats=1"
        status_label = "previouslyowned"
    else:
        return []

    print(f"Fetching {status_label} collection...")
    for i in range(15):
        resp = requests.get(url, headers=HEADERS, timeout=60)
        if resp.status_code == 202 or not resp.text.strip():
            print(f"[{i+1}/15] Waiting...")
            time.sleep(5)
            continue
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        break
    else:
        raise Exception(f"BGG timeout fetching {status_label}")

    games = []
    for item in root.findall("item"):
        game = xml_to_dict(item)
        game["status"] = status_label

        # 最終プレイ日
        game_id = game.get("objectid")
        game["lastplay"] = latest_plays.get(game_id)

        # thing APIで weight / designers を追加
        thing_info = fetch_thing_info(game_id)
        game.update(thing_info)

        # 不要フィールド削除
        for key in ["image", "thumbnail", "objecttype", "subtype", "collid"]:
            game.pop(key, None)
        if "name" in game and isinstance(game["name"], dict):
            game["name"].pop("sortindex", None)

        # stats整理
        stats = game.get("stats", {})
        for key in ["minplaytime", "maxplaytime", "numowned"]:
            stats.pop(key, None)

        rating = stats.get("rating", {})
        rating.pop("stddev", None)
        rating.pop("median", None)
        rating.pop("usersrated", None)
        if "value" in rating:
            rating["myrating"] = rating.pop("value")
        stats["rating"] = rating
        game["stats"] = stats

        games.append(game)

    return games

# ====================================
# 実行
# ====================================
latest_plays = fetch_latest_plays()

owned_games = fetch_collection(latest_plays, owned=True)
wishlist_games = fetch_collection(latest_plays, wishlist=True)
preordered_games = fetch_collection(latest_plays, preordered=True)
prevowned_games = fetch_collection(latest_plays, prevowned=True)

all_games = owned_games + wishlist_games + preordered_games + prevowned_games

# ====================================
# 保存
# ====================================
with open("bgg_collection.json", "w", encoding="utf-8") as f:
    json.dump(all_games, f, ensure_ascii=False, indent=2)

print(f"{len(all_games)} games saved to bgg_collection.json")
