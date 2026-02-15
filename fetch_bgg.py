import os
import requests
import xml.etree.ElementTree as ET
import json
import time

# ====================================
# 設定
# ====================================
USERNAME = "ZAKIbg"             # BGGユーザー名
OUTPUT_FILE = "bgg_collection.json"

MAX_RETRIES = 30
WAIT_TIME = 5  # 秒

# ====================================
# コレクション取得
# ====================================
def fetch_collection(owned=True, wishlist=False):
    """
    BGG XML APIからコレクションを取得
    Cookie認証対応、Accepted (202) 待機ロジックあり
    """
    params = []
    if owned:
        params.append("own=1")
    if wishlist:
        params.append("wishlist=1")

    url = f"https://boardgamegeek.com/xmlapi2/collection?username={USERNAME}&stats=1"
    if params:
        url += "&" + "&".join(params)

    # GitHub Secrets から Cookie を取得
    headers = {}
    bgg_cookie = os.environ.get("BGG_COOKIE")
    if bgg_cookie:
        headers["Cookie"] = f"bggsessionid={bgg_cookie}"

    for i in range(MAX_RETRIES):
        print(f"[{i+1}/{MAX_RETRIES}] Fetching...")
        resp = requests.get(url, headers=headers)

        if resp.status_code == 200 and resp.content.strip():
            return resp.content
        elif resp.status_code == 202:
            print("Request accepted, waiting before retry...")
        else:
            print(f"Status {resp.status_code}, retrying...")

        time.sleep(WAIT_TIME)

    raise Exception("BGG API が応答しませんでした。")

# ====================================
# XML パース
# ====================================
def parse_collection(xml_bytes):
    """
    XML をパースして JSON 用リストに変換
    """
    root = ET.fromstring(xml_bytes)
    games = []
    for item in root.findall("item"):
        game = {
            "id": item.get("objectid"),
            "name": item.findtext("name"),
            "year": item.findtext("yearpublished"),
            "numplays": item.findtext("numplays")
        }
        games.append(game)
    return games

# ====================================
# メイン
# ====================================
def main():
    print("Fetching owned games...")
    owned_xml = fetch_collection(owned=True)
    owned_list = parse_collection(owned_xml)

    print("Fetching wishlist games...")
    wishlist_xml = fetch_collection(wishlist=True)
    wishlist_list = parse_collection(wishlist_xml)

    # 名前順でソート（None は空文字扱い）
    collection = {
        "owned": sorted(owned_list, key=lambda x: x["name"] or ""),
        "wishlist": sorted(wishlist_list, key=lambda x: x["name"] or "")
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(collection, f, indent=2, ensure_ascii=False)

    print(f"Saved collection to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
