import os
import requests
import time
import xml.etree.ElementTree as ET
import json
import smtplib
import datetime
from email.mime.text import MIMEText

# ====================================
# 必須
# ====================================
BGG_API_TOKEN = os.environ["BGG_API_TOKEN"]
BGG_COOKIE = os.environ["BGG_COOKIE"]
API_THING = "https://boardgamegeek.com/xmlapi2/thing"
USERNAME = "zakibg"

# ====================================
# 設定
# ====================================
ROTATION_DAYS = 100
SLEEP_BETWEEN_CALLS = 1
SLEEP_ON_429 = 60

# ====================================
# XML → dict
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
# plays 全取得
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
            if game_id not in lastplays or date > lastplays[game_id]:
                lastplays[game_id] = date

        page += 1
        time.sleep(1)

    print(f"Collected last plays for {len(lastplays)} games")
    return lastplays

# ====================================
# collection（stats含む）
# ====================================
def fetch_collection(username, status_flag):
    url = f"https://boardgamegeek.com/xmlapi2/collection?username={username}&{status_flag}=1&stats=1"
    headers = {"User-Agent": "Mozilla/5.0", "Cookie": BGG_COOKIE}

    for _ in range(15):
        resp = requests.get(url, headers=headers, timeout=60)
        if resp.status_code == 202:
            time.sleep(5)
            continue
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        break
    else:
        raise Exception("Collection timeout")

    games = []
    for item in root.findall("item"):
        g = xml_to_dict(item)

        # 明示的に日次更新対象を上書き
        g["status"] = status_flag
        g["numplays"] = item.findtext("numplays")
        games.append(g)

    return games

# ====================================
# Thing API
# ====================================
def fetch_thing_info(game_id):
    headers = {"Authorization": f"Bearer {BGG_API_TOKEN}"}
    cookies = {"bggsession": BGG_COOKIE}
    params = {"id": game_id, "stats": 1}

    while True:
        resp = requests.get(API_THING, params=params, headers=headers, cookies=cookies)
        if resp.status_code == 429:
            time.sleep(SLEEP_ON_429)
            continue
        if resp.status_code == 202:
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

    game_type = item.attrib.get("type", "boardgame")

    return designers, weight, mechanics, categories, game_type

# ====================================
# 実行
# ====================================
def main():

    today_mod = datetime.date.today().toordinal() % ROTATION_DAYS

    try:
        with open("bgg_collection.json", "r", encoding="utf-8") as f:
            old_data = json.load(f)
    except FileNotFoundError:
        old_data = []

    old_dict = {g["objectid"]: g for g in old_data}

    # --- plays ---
    lastplays = fetch_latest_plays(USERNAME)

    # --- collection 日次全更新 ---
    owned = fetch_collection(USERNAME, "own")
    wishlist = fetch_collection(USERNAME, "wishlist")
    preordered = fetch_collection(USERNAME, "preordered")
    prevowned = fetch_collection(USERNAME, "prevowned")

    all_games = owned + wishlist + preordered + prevowned
    local_dict = {g["objectid"]: g for g in all_games}

    # 削除反映
    removed = set(old_dict) - set(local_dict)
    for rid in removed:
        del old_dict[rid]

    # マージ（stats含め毎回上書き）
    for oid, game in local_dict.items():
        old_dict[oid] = game

    # ====================================
    # Thing ローテ更新
    # ====================================
    to_update = []

    for g in old_dict.values():
        oid = int(g["objectid"])

        if (
            "designers" not in g or
            "mechanics" not in g or
            "categories" not in g or
            "weight" not in g or
            "type" not in g or
            oid % ROTATION_DAYS == today_mod
        ):
            to_update.append(g)

    print(f"Thing targets: {len(to_update)}")

    for game in to_update:
        try:
            designers, weight, mechanics, categories, game_type = fetch_thing_info(game["objectid"])
            game["designers"] = designers
            game["weight"] = weight
            game["mechanics"] = mechanics
            game["categories"] = categories
            game["type"] = game_type
            time.sleep(SLEEP_BETWEEN_CALLS)
        except Exception as e:
            print(f"Thing error {game['objectid']} {e}")

    # --- lastplay 反映 ---
    for oid, date in lastplays.items():
        if oid in old_dict:
            old_dict[oid]["lastplay"] = date

    # --- 保存 ---
    final_list = sorted(old_dict.values(), key=lambda x: x["name"]["value"].lower())

    with open("bgg_collection.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)

    print(f"{len(final_list)} games saved")


if __name__ == "__main__":
    main()
