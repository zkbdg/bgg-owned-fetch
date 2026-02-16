import os
import requests
import time
import xml.etree.ElementTree as ET
import json

USERNAME = "zakibg"
BGG_COOKIE = os.environ["BGG_COOKIE"]

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
# BGG コレクション取得
# ====================================
def fetch_collection(owned=False, wishlist=False, preordered=False, prevowned=False):
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

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Cookie": BGG_COOKIE
    }

    print(f"Fetching {status_label} collection...")
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
        raise Exception(f"BGG timeout fetching {status_label}")

    games = []
    for item in root.findall("item"):
        game = xml_to_dict(item)
        game["status"] = status_label

        # 不要フィールド削除
        for key in ["image", "thumbnail", "objecttype", "subtype", "collid"]:
            game.pop(key, None)
        if "name" in game and isinstance(game["name"], dict):
            game["name"].pop("sortindex", None)

        # stats 内の不要フィールド削除
        stats = game.get("stats", {})
        for key in ["minplaytime", "maxplaytime", "numowned"]:
            stats.pop(key, None)

        # rating 内の不要フィールド削除 & value → myrating
        rating = stats.get("rating", {})
        rating.pop("stddev", None)
        rating.pop("median", None)
        rating.pop("usersrated", None)  # ← 追加
        if "value" in rating:
            rating["myrating"] = rating.pop("value")
        stats["rating"] = rating
        game["stats"] = stats

        # numplays 削除
        # game.pop("numplays", None)

        games.append(game)

    return games

# ====================================
# 全コレクション取得
# ====================================
owned_games = fetch_collection(owned=True)
wishlist_games = fetch_collection(wishlist=True)
preordered_games = fetch_collection(preordered=True)
prevowned_games = fetch_collection(prevowned=True)

all_games = owned_games + wishlist_games + preordered_games + prevowned_games

# ====================================
# 保存
# ====================================
with open("bgg_collection.json", "w", encoding="utf-8") as f:
    json.dump(all_games, f, ensure_ascii=False, indent=2)

print(f"{len(all_games)} games saved to bgg_collection.json")
