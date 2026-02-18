import os
import time
import json
import requests
import xml.etree.ElementTree as ET

BGG_API_TOKEN = os.environ.get("BGG_API_TOKEN")
BGG_COOKIE = os.environ.get("BGG_COOKIE")
API_COLLECTION = "https://boardgamegeek.com/xmlapi2/collection"
API_PLAYS = "https://boardgamegeek.com/xmlapi2/plays"
API_THING = "https://boardgamegeek.com/xmlapi2/thing"

BATCH_SIZE = 50          # 1回で叩く件数
SLEEP_BETWEEN_CALLS = 1  # thing 間の間隔
SLEEP_ON_429 = 60        # 429のときの待機時間

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
# Plays 取得
# ====================================
def fetch_latest_plays(username):
    print("Fetching plays...")
    headers = {"User-Agent": "Mozilla/5.0", "Cookie": BGG_COOKIE}
    latest = {}
    page = 1
    while True:
        url = f"{API_PLAYS}?username={username}&subtype=boardgame&page={page}"
        resp = requests.get(url, headers=headers, timeout=60)
        if resp.status_code == 202:
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
    print(f"Collected lastplays for {len(latest)} games")
    return latest

# ====================================
# Collection 取得
# ====================================
def fetch_collection(username, owned=True):
    headers = {"User-Agent": "Mozilla/5.0", "Cookie": BGG_COOKIE}
    status = "owned" if owned else "other"
    url = f"{API_COLLECTION}?username={username}&own=1&stats=1" if owned else f"{API_COLLECTION}?username={username}&stats=1"
    for _ in range(15):
        resp = requests.get(url, headers=headers, timeout=60)
        if resp.status_code == 202 or not resp.text.strip():
            time.sleep(5)
            continue
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        break
    else:
        raise Exception("BGG timeout fetching collection")
    games = []
    for item in root.findall("item"):
        game = xml_to_dict(item)
        game["status"] = status
        games.append(game)
    return games

# ====================================
# Thing 取得
# ====================================
def fetch_thing_info(game_id):
    headers = {"Authorization": f"Bearer {BGG_API_TOKEN}"} if BGG_API_TOKEN else {}
    cookies = {"bggsession": BGG_COOKIE} if BGG_COOKIE else {}
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
    designers = [l.attrib["value"] for l in item.findall("link") if l.attrib.get("type") == "boardgamedesigner"]
    mechanics = [l.attrib["value"] for l in item.findall("link") if l.attrib.get("type") == "boardgamemechanic"]
    categories = [l.attrib["value"] for l in item.findall("link") if l.attrib.get("type") == "boardgamecategory"]
    weight_elem = item.find("statistics/ratings/averageweight")
    weight = weight_elem.attrib["value"] if weight_elem is not None else None
    return designers, mechanics, categories, weight

# ====================================
# メイン処理
# ====================================
def main():
    username = os.environ.get("BGG_USERNAME")
    # plays を先に取得
    lastplays = fetch_latest_plays(username)
    # collection
    collection = fetch_collection(username, owned=True)
    # ローカル JSON 読み込み
    try:
        with open("bgg_collection.json", "r", encoding="utf-8") as f:
            local_data = {g["objectid"]: g for g in json.load(f)}
    except FileNotFoundError:
        local_data = {}
    # collection を統合
    for g in collection:
        game_id = g["objectid"]
        g["lastplay"] = lastplays.get(game_id)
        if game_id in local_data:
            local_data[game_id].update(g)
        else:
            local_data[game_id] = g
    # Thing 差分更新
    pending = [g for g in local_data.values()
               if "designers" not in g or "mechanics" not in g or "categories" not in g or "weight" not in g]
    print(f"Pending thing updates: {len(pending)}")
    for i in range(0, len(pending), BATCH_SIZE):
        batch = pending[i:i+BATCH_SIZE]
        for game in batch:
            try:
                designers, mechanics, categories, weight = fetch_thing_info(game["objectid"])
                game["designers"] = designers
                game["mechanics"] = mechanics
                game["categories"] = categories
                game["weight"] = weight
                print(f"Updated {game['name']['value']} → weight:{weight}, designers:{len(designers)}")
                time.sleep(SLEEP_BETWEEN_CALLS)
            except Exception as e:
                print(f"Error fetching {game['name']['value']} ({game['objectid']}): {e}")
    # 保存
    final_list = sorted(local_data.values(), key=lambda x: x["name"]["value"].lower())
    with open("bgg_collection.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(final_list)} games")

if __name__ == "__main__":
    main()
