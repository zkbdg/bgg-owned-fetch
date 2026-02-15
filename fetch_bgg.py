import os
import requests
import time
import xml.etree.ElementTree as ET
import json

USERNAME = "zakibg"
BGG_COOKIE = os.environ["BGG_COOKIE"]

# ====================================
# 取得用関数
# ====================================
def fetch_collection(owned=False, wishlist=False):
    if owned:
        url = f"https://boardgamegeek.com/xmlapi2/collection?username={USERNAME}&own=1&stats=1"
        status_label = "owned"
    elif wishlist:
        url = f"https://boardgamegeek.com/xmlapi2/collection?username={USERNAME}&wishlist=1&stats=1"
        status_label = "wishlist"
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

    # XML → dict 再帰変換
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

    games = [xml_to_dict(item) for item in root.findall("item")]

    # status キー追加
    for game in games:
        game["status"] = status_label

    return games

# ====================================
# Owned と Wishlist 両方取得
# ====================================
owned_games = fetch_collection(owned=True)
wishlist_games = fetch_collection(wishlist=True)

all_games = owned_games + wishlist_games

# 保存
with open("bgg_collection.json", "w", encoding="utf-8") as f:
    json.dump(all_games, f, ensure_ascii=False, indent=2)

print(f"{len(all_games)} games saved to bgg_collection.json")
