import os
import json
import time
import requests
import xml.etree.ElementTree as ET

BGG_API_TOKEN = os.environ["BGG_API_TOKEN"]
BGG_COOKIE = os.environ["BGG_COOKIE"]
API_URL_THING = "https://boardgamegeek.com/xmlapi2/thing"
API_URL_PLAYS = "https://boardgamegeek.com/xmlapi2/plays"
API_URL_COLLECTION = "https://boardgamegeek.com/xmlapi2/collection"

BATCH_SIZE = 18
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
# BGG plays 取得
# ====================================
def fetch_latest_plays():
    print("Fetching plays...")
    headers = {"User-Agent": "Mozilla/5.0", "Cookie": BGG_COOKIE}
    latest = {}
    page = 1
    while True:
        url = f"{API_URL_PLAYS}?username=ZAKIbg&subtype=boardgame&page={page}"
        resp = requests.get(url, headers=headers, timeout=60)
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
# BGG collection 取得
# ====================================
def fetch_collection(latest_plays, status_filter):
    url = f"{API_URL_COLLECTION}?username=ZAKIbg&{status_filter}=1&stats=1"
    headers = {"User-Agent": "Mozilla/5.0", "Cookie": BGG_COOKIE}
    print(f"Fetching collection ({status_filter}) ...")
    for i in range(15):
        resp = requests.get(url, headers=headers, timeout=60)
        if resp.status_code == 202 or not resp.text.strip():
            print(f"[{i+1}/15] Waiting...")
            time.sleep(5)
            continue
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        break
    else:
        raise Exception(f"BGG timeout fetching {status_filter}")

    games = []
    for item in root.findall("item"):
        game = xml_to_dict(item)
        game["status"] = status_filter
        game_id = game.get("objectid")
        game["lastplay"] = latest_plays.get(game_id)
        # 不要フィールド削除
        for key in ["image", "thumbnail", "objecttype", "subtype", "collid"]:
            game.pop(key, None)
        if "name" in game and isinstance(game["name"], dict):
            game["name"].pop("sortindex", None)
        games.append(game)
    return games

# ====================================
# Thing API 取得（差分）
# ====================================
def fetch_thing_info(game_id):
    headers = {"Authorization": f"Bearer {BGG_API_TOKEN}"}
    cookies = {"bggsession": BGG_COOKIE}
    params = {"id": game_id, "stats": 1}

    while True:
        resp = requests.get(API_URL_THING, params=params, headers=headers, cookies=cookies)
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
    # Designers
    designers = [l.attrib["value"] for l in item.findall("link") if l.attrib.get("type") == "boardgamedesigner"]
    # Mechanics
    mechanics = [l.attrib["value"] for l in item.findall("link") if l.attrib.get("type") == "boardgamemechanic"]
    # Categories
    categories = [l.attrib["value"] for l in item.findall("link") if l.attrib.get("type") == "boardgamecategory"]
    # Weight
    weight_elem = item.find("statistics/ratings/averageweight")
    weight = weight_elem.attrib["value"] if weight_elem is not None else None
    return designers, weight, mechanics, categories

# ====================================
# メイン
# ====================================
def main():
    latest_plays = fetch_latest_plays()

    # collection 全件取得
    owned_games = fetch_collection(latest_plays, "own")
    wishlist_games = fetch_collection(latest_plays, "wishlist")
    preordered_games = fetch_collection(latest_plays, "preordered")
    prevowned_games = fetch_collection(latest_plays, "prevowned")

    all_games = owned_games + wishlist_games + preordered_games + prevowned_games

    # local_dict にして objectid で管理（差分更新用）
    local_dict = {g["objectid"]: g for g in all_games}

    # Thing API 差分更新対象
    pending = [
        g for g in all_games
        if "designers" not in g
        or "mechanics" not in g
        or "categories" not in g
        or "weight" not in g
    ]
    print(f"Pending games to update via Thing: {len(pending)}")

    for game in pending[:BATCH_SIZE]:
        try:
            designers, weight, mechanics, categories = fetch_thing_info(game["objectid"])
            game["designers"] = designers
            game["weight"] = weight
            game["mechanics"] = mechanics
            game["categories"] = categories
            print(f"Updated {game['name']} → designers:{len(designers)}, mechanics:{len(mechanics)}, categories:{len(categories)}, weight:{weight}")
            time.sleep(SLEEP_BETWEEN_CALLS)
        except Exception as e:
            print(f"Error fetching {game.get('name')} ({game['objectid']}): {e}")

    # ====================================
    # 名前が dict の場合に安全化
    # ====================================
    corrected = 0
    for game_id, game in local_dict.items():
        name_field = game.get("name")
        if isinstance(name_field, dict):
            value = name_field.get("value")
            game["name"] = value if value else f"unknown_{game_id}"
            corrected += 1
        elif name_field is None:
            game["name"] = f"unknown_{game_id}"
            corrected += 1
    print(f"[DEBUG] Total corrected names: {corrected}")

    # sort 安全化
    final_list = sorted(local_dict.values(), key=lambda x: str(x["name"]).lower())

    # 保存
    with open("bgg_collection.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)

    print(f"{len(final_list)} games saved to bgg_collection.json")

if __name__ == "__main__":
    main()
