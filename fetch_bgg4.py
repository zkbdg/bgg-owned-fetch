import os
import requests
import time
import xml.etree.ElementTree as ET
import json
import smtplib
import datetime
from email.mime.text import MIMEText

# ====================================
# 必須: Cookie（ThingもこれでOK）
# ====================================
BGG_COOKIE = os.environ["BGG_COOKIE"]
API_THING = "https://boardgamegeek.com/xmlapi2/thing"

# ====================================
# 固定ユーザー名
# ====================================
USERNAME = "zakibg"

# ====================================
# 設定
# ====================================
ROTATION_DAYS = 100
SLEEP_BETWEEN_CALLS = 1
SLEEP_ON_429 = 60
THING_KEYS = ["designers", "weight", "mechanics", "categories", "type"]

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
# collection 取得
# ====================================
def fetch_collection(username, owned=False, wishlist=False, preordered=False, prevowned=False):

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

    for _ in range(15):
        resp = requests.get(url, headers=headers, timeout=60)

        if resp.status_code == 202:
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
# Thing API
# ====================================
def fetch_thing_info(game_id):

    headers = {"User-Agent": "Mozilla/5.0", "Cookie": BGG_COOKIE}
    params = {"id": game_id, "stats": 1}

    while True:
        resp = requests.get(API_THING, params=params, headers=headers)

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
    weight = float(weight_elem.attrib["value"]) if weight_elem is not None else None

    game_type = item.attrib.get("type", "boardgame")

    return designers, weight, mechanics, categories, game_type

# ====================================
# メール送信
# ====================================
def send_email(updated_count, total_count, diff_logs):

    EMAIL_FROM = os.environ.get("EMAIL_FROM")
    EMAIL_TO = os.environ.get("EMAIL_TO")
    EMAIL_USER = os.environ.get("EMAIL_USER")
    EMAIL_PASS = os.environ.get("EMAIL_PASS")

    if not all([EMAIL_FROM, EMAIL_TO, EMAIL_USER, EMAIL_PASS]):
        return

    subject = f"BGG Sync Report"

    body = f"""Total games: {total_count}
Thing updated today: {updated_count}
Diff count: {len(diff_logs)}

Changes:
""" + "\n".join(diff_logs[:50])

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(EMAIL_USER, EMAIL_PASS)
        smtp.send_message(msg)

# ====================================
# 実行
# ====================================
def main():

    today_mod = datetime.date.today().toordinal() % ROTATION_DAYS
    print(f"Rotation bucket today: {today_mod}")

    try:
        with open("bgg_collection.json", "r", encoding="utf-8") as f:
            old_data = json.load(f)
    except FileNotFoundError:
        old_data = []

    old_dict = {g["objectid"]: g for g in old_data}

    # --- plays ---
    lastplays = fetch_latest_plays(USERNAME)

    # --- collection ---
    owned = fetch_collection(USERNAME, owned=True)
    wishlist = fetch_collection(USERNAME, wishlist=True)
    preordered = fetch_collection(USERNAME, preordered=True)
    prevowned = fetch_collection(USERNAME, prevowned=True)

    all_games = owned + wishlist + preordered + prevowned
    local_dict = {g["objectid"]: g for g in all_games}

    diff_logs = []

    # --- 削除 ---
    removed = set(old_dict) - set(local_dict)
    for rid in removed:
        name = old_dict[rid]["name"]["value"]
        msg = f"Removed: {name}"
        print(msg)
        diff_logs.append(msg)
        del old_dict[rid]

    # --- 完全同期 + 差分チェック ---
    for oid, game in local_dict.items():

        if oid in old_dict:
            old = old_dict[oid]
            name = game["name"]["value"]

            # rating
            old_rating = old.get("stats", {}).get("rating", {}).get("value")
            new_rating = game.get("stats", {}).get("rating", {}).get("value")
            if old_rating != new_rating:
                msg = f"Rating changed: {name} {old_rating} → {new_rating}"
                print(msg)
                diff_logs.append(msg)

            # numplays
            old_plays = old.get("numplays")
            new_plays = game.get("numplays")
            if old_plays != new_plays:
                msg = f"Numplays changed: {name} {old_plays} → {new_plays}"
                print(msg)
                diff_logs.append(msg)

            # status
            if old.get("status") != game.get("status"):
                msg = f"Status changed: {name} {old.get('status')} → {game.get('status')}"
                print(msg)
                diff_logs.append(msg)

            # Thing情報は引き継ぐ
            for key in THING_KEYS:
                if key in old:
                    game[key] = old[key]

        old_dict[oid] = game

    # --- Thing更新判定 ---
    to_update = []

    for g in old_dict.values():
        oid = int(g["objectid"])

        if not all(k in g for k in THING_KEYS):
            to_update.append(g)
            continue

        if oid % ROTATION_DAYS == today_mod:
            to_update.append(g)

    print(f"Thing API targets today: {len(to_update)}")

    updated = 0

    for game in to_update:
        try:
            designers, weight, mechanics, categories, game_type = fetch_thing_info(game["objectid"])
            game["designers"] = designers
            game["weight"] = weight
            game["mechanics"] = mechanics
            game["categories"] = categories
            game["type"] = game_type
            updated += 1
            print(f"Thing refreshed: {game['name']['value']}")
            time.sleep(SLEEP_BETWEEN_CALLS)
        except Exception as e:
            print(f"Thing error: {game['objectid']} {e}")

    # --- lastplay反映 ---
    for oid, date in lastplays.items():
        if oid in old_dict:
            old_dict[oid]["lastplay"] = date

    # --- 保存 ---
    final_list = sorted(old_dict.values(), key=lambda x: x["name"]["value"].lower())

    with open("bgg_collection.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)

    print(f"{len(final_list)} games saved")
    print(f"Thing updated: {updated}")
    print(f"Diff count: {len(diff_logs)}")

    send_email(updated, len(final_list), diff_logs)


if __name__ == "__main__":
    main()
