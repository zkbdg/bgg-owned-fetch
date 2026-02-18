import os
import time
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

USERNAME = os.environ["BGG_USERNAME"]
BGG_API_TOKEN = os.environ["BGG_API_TOKEN"]
BGG_COOKIE = os.environ.get("BGG_COOKIE")

COLLECTION_URL = "https://boardgamegeek.com/xmlapi2/collection"
THING_URL = "https://boardgamegeek.com/xmlapi2/thing"
PLAYS_URL = "https://boardgamegeek.com/xmlapi2/plays"

JSON_FILE = "bgg_collection.json"


# =========================
# 共通リクエスト処理
# =========================
def bgg_get(url, params):
    headers = {
        "Authorization": f"Bearer {BGG_API_TOKEN}",
        "User-Agent": "ZAKIbg-sync/3.0"
    }

    cookies = {}
    if BGG_COOKIE:
        cookies["bggsession"] = BGG_COOKIE

    while True:
        resp = requests.get(url, params=params, headers=headers, cookies=cookies)

        if resp.status_code == 202:
            time.sleep(5)
            continue

        if resp.status_code == 429:
            time.sleep(60)
            continue

        resp.raise_for_status()
        return resp.text


# =========================
# collection取得
# =========================
def fetch_collection():
    xml_text = bgg_get(
        COLLECTION_URL,
        {"username": USERNAME, "own": 1, "stats": 1}
    )

    root = ET.fromstring(xml_text)
    items = []

    for item in root.findall("item"):
        items.append({
            "objectid": item.attrib["objectid"],
            "name": item.find("name").text
        })

    return items


# =========================
# thing取得（新規のみ）
# =========================
def fetch_thing(game_id):
    xml_text = bgg_get(
        THING_URL,
        {"id": game_id, "stats": 1}
    )

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


# =========================
# plays全取得＆集計
# =========================
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

            game_id = item.attrib["objectid"]

            if game_id not in plays_dict:
                plays_dict[game_id] = {
                    "last_date": None,
                    "last_quantity": 0,
                    "total_plays": 0
                }

            # 通算加算
            plays_dict[game_id]["total_plays"] += quantity

            # 最新日判定
            if date_str:
                current_date = datetime.strptime(date_str, "%Y-%m-%d")
                last_date = plays_dict[game_id]["last_date"]

                if last_date is None or current_date > last_date:
                    plays_dict[game_id]["last_date"] = current_date
                    plays_dict[game_id]["last_quantity"] = quantity

        # ページ終了判定
        if page * 100 >= total:
            break

        page += 1

    # datetime → 文字列変換
    for gid in plays_dict:
        if plays_dict[gid]["last_date"]:
            plays_dict[gid]["last_date"] = plays_dict[gid]["last_date"].strftime("%Y-%m-%d")

    return plays_dict


# =========================
# メイン同期処理
# =========================
def main():

    # JSON読込
    if os.path.exists(JSON_FILE):
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            local_data = json.load(f)
    else:
        local_data = []

    local_dict = {g["objectid"]: g for g in local_data}
    local_ids = set(local_dict.keys())

    # collection取得
    remote_items = fetch_collection()
    remote_ids = {g["objectid"] for g in remote_items}

    new_ids = remote_ids - local_ids
    removed_ids = local_ids - remote_ids

    # 削除反映
    for rid in removed_ids:
        del local_dict[rid]

    # 追加分thing取得
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

    # plays集計
    plays_dict = fetch_and_aggregate_plays()

    # lastplays付与
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

    # 保存
    final_list = sorted(local_dict.values(), key=lambda x: x["name"].lower())

    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)

    print("✅ Full sync complete")


if __name__ == "__main__":
    main()
