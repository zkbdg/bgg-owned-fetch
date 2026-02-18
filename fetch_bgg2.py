import os
import requests
import time
import xml.etree.ElementTree as ET
import json

# ====================================
# 必須: トークンと Cookie
# ====================================
BGG_API_TOKEN = os.environ["BGG_API_TOKEN"]
BGG_COOKIE = os.environ["BGG_COOKIE"]
API_THING = "https://boardgamegeek.com/xmlapi2/thing"

# ====================================
# 固定ユーザー名
# ====================================
USERNAME = "zakibg"

# ====================================
# 設定
# ====================================
BATCH_SIZE = 2       # Thing 差分取得の件数
SLEEP_BETWEEN_CALLS = 1
SLEEP_ON_429 = 60

# ====================================
# XML → dict 再帰
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
# plays 全件取得
# ====================================
def fetch_latest_plays(username):
    print("Fetching plays...")
    headers = {"User-Agent": "Mozilla/5.0", "Cookie": BGG_COOKIE}
    lastplays = {}
    page = 1

    while True:
        url = f"https://boardgamegeek.com/xmlapi2/plays?username={username}&subtype=boardgame&page={page}"
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
            if game_id not in lastplays or date > lastplays[game_id]:
                lastplays[game_id] = date

        page += 1
        time.sleep(1)

    print(f"Collected last plays for {len(lastplays)} games")
    return lastplays

# ====================================
# collection 取得
# ====================================
def fetch_collection(username, owned=False, wishlist=False, preordered=False, prevowned=False):
    status = None
    if owned:
        url = f"https://boardgamegeek.com/xmlapi2/collection?username={username}&own=1&stats=1"
        status = "owned"
    elif wishlist:
        url = f"https://boardgamegeek.com/xmlapi2/collection?username={username}&wishlist=1&stats=1"
        status = "wishlist"
    elif preordered:
        url = f"https://boardgamegeek.com/xmlapi2/collection?username={username}&preordered=1&stats=1"
        status = "preordered"
    elif prevowned:
        url = f"https://boardgamegeek.com/xmlapi2/collection?username={username}&prevowned=1&stats=1"
        status = "previouslyowned"
    else:
        return []

    headers = {"User-Agent": "Mozilla/5.0", "Cookie": BGG_COOKIE}
    print(f"Fetching {status} collection...")
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
        raise Exception(f"Timeout fetching {status}")

    games = []
    for item in root.findall("item"):
        game = xml_to_dict(item)
        game["status"] = status
        games.append(game)
    return games

# ====================================
# Thing API 差分取得
# ====================================
def fetch_thing_info(game_id):
    headers = {"Authorization": f"Bearer {BGG_API_TOKEN}"}
    cookies = {"bggsession": BGG_COOKIE}
    params = {"id": game_id, "stats": 1}

    while True:
        resp = requests.get(API_THING, params=params, headers=headers, cookies=cookies)
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

    designers = [link.attrib["value"] for link in item.findall("link") if link.attrib.get("type") == "boardgamedesigner"]
    mechanics = [link.attrib["value"] for link in item.findall("link") if link.attrib.get("type") == "boardgamemechanic"]
    categories = [link.attrib["value"] for link in item.findall("link") if link.attrib.get("type") == "boardgamecategory"]
    weight_elem = item.find("statistics/ratings/averageweight")
    weight = weight_elem.attrib["value"] if weight_elem is not None else None
    type_ = item.attrib.get("type")  # boardgame or boardgameexpansion

    return designers, weight, mechanics, categories, type_

# ====================================
# 実行
# ====================================
def main():
    # 1. plays
    lastplays = fetch_latest_plays(USERNAME)

    # 2. collection
    owned = fetch_collection(USERNAME, owned=True)
    wishlist = fetch_collection(USERNAME, wishlist=True)
    preordered = fetch_collection(USERNAME, preordered=True)
    prevowned = fetch_collection(USERNAME, prevowned=True)

    all_games = owned + wishlist + preordered + prevowned
    local_dict = {g["objectid"]: g for g in all_games}

    # 3. Thing API 差分
    pending = [
        g for g in all_games
        if "designers" not in g or "mechanics" not in g or "categories" not in g or "weight" not in g or "type" not in g
    ]
    print(f"Pending games to update via Thing API: {len(pending)}")

    for game in pending:
        try:
            designers, weight, mechanics, categories, type_ = fetch_thing_info(game["objectid"])
            game["designers"] = designers
            game["weight"] = weight
            game["mechanics"] = mechanics
            game["categories"] = categories
            game["type"] = type_
            print(f"Updated {game['name']['value']}")
            time.sleep(SLEEP_BETWEEN_CALLS)
        except Exception as e:
            print(f"Error fetching {game['name']['value']} ({game['objectid']}): {e}")

    # 4. lastplay 追加
    for game_id, date in lastplays.items():
        if game_id in local_dict:
            local_dict[game_id]["lastplay"] = date

    # 5. XMLから消えたゲームは削除
    xml_ids = set(g["objectid"] for g in all_games)
    json_ids = set(local_dict.keys())
    removed_ids = json_ids - xml_ids
    for rid in removed_ids:
        print(f"Removed {local_dict[rid]['name']['value']} (no longer in collection)")
        del local_dict[rid]

    # 6. 保存
    final_list = sorted(local_dict.values(), key=lambda x: x["name"]["value"].lower())
    with open("bgg_collection.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)

    print(f"{len(final_list)} games saved to bgg_collection.json")

if __name__ == "__main__":
    main()
