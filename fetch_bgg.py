import os
import requests
import time
import xml.etree.ElementTree as ET
import json

USERNAME = "zakibg"
BGG_COOKIE = os.environ["BGG_COOKIE"]

# ====================================
# BGG コレクション取得（必要フィールドのみ）
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
        # stats フィールドをそのまま dict に抽出
        stats_elem = item.find("stats")
        stats = {}
        if stats_elem is not None:
            for stat_child in stats_elem:
                stats[stat_child.tag] = stat_child.attrib

        game = {
            "name": item.find("name").attrib.get("value") if item.find("name") is not None else None,
            "yearpublished": item.find("yearpublished").attrib.get("value") if item.find("yearpublished") is not None else None,
            "stats": stats,
            "status": status_label
        }
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
