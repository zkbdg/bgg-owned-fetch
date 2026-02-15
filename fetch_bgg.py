import requests
import xml.etree.ElementTree as ET
import json
import time

USERNAME = "ZAKIbg"  # ここを自分のユーザー名に変更
OUTPUT_FILE = "bgg_collection.json"

MAX_RETRIES = 20
WAIT_TIME = 5  # 秒

def fetch_collection(owned=True, wishlist=False):
    """
    BGG XML APIからコレクションを取得（拡張も含む）
    """
    params = []
    if owned:
        params.append("own=1")
    if wishlist:
        params.append("wishlist=1")

    url = f"https://boardgamegeek.com/xmlapi2/collection?username={USERNAME}&stats=1"
    if params:
        url += "&" + "&".join(params)

    for i in range(MAX_RETRIES):
        print(f"[{i+1}/{MAX_RETRIES}] Fetching...")
        resp = requests.get(url)
        if resp.status_code == 200 and resp.content.strip():
            return resp.content
        time.sleep(WAIT_TIME)

    raise Exception("BGG API が応答しませんでした。")

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

def main():
    print("Fetching owned games...")
    owned_xml = fetch_collection(owned=True)
    owned_list = parse_collection(owned_xml)

    print("Fetching wishlist games...")
    wishlist_xml = fetch_collection(wishlist=True)
    wishlist_list = parse_collection(wishlist_xml)

    # 名前順でソート（None は空文字として扱う）
    collection = {
        "owned": sorted(owned_list, key=lambda x: x["name"] or ""),
        "wishlist": sorted(wishlist_list, key=lambda x: x["name"] or "")
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(collection, f, indent=2, ensure_ascii=False)

    print(f"Saved collection to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
