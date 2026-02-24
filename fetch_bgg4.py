import os
import requests
import time
import xml.etree.ElementTree as ET
import json
import smtplib
import datetime
from email.mime.text import MIMEText

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
            gid = item.get("objectid")
            if gid and date:
                if gid not in lastplays or date > lastplays[gid]:
                    lastplays[gid] = date

        page += 1
        time.sleep(1)

    print(f"Collected last plays for {len(lastplays)} games")
    return lastplays

# ====================================
# collection 完全取得
# ====================================
def fetch_collection(username, flag):
    url = f"https://boardgamegeek.com/xmlapi2/collection?username={username}&{flag}=1&stats=1"
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
        g["status"] = flag
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
# メール
# ====================================
def send_email(updated, total, diff_log):
    EMAIL_FROM = os.environ.get("EMAIL_FROM")
    EMAIL_TO = os.environ.get("EMAIL_TO")
    EMAIL_USER = os.environ.get("EMAIL_USER")
    EMAIL_PASS = os.environ.get("EMAIL_PASS")

    if not all([EMAIL_FROM, EMAIL_TO, EMAIL_USER, EMAIL_PASS]):
        return

    subject = f"BGG Sync: {updated} thing updates"

    body = f"""Total games: {total}
Thing updated: {updated}

Collection changes:
{diff_log if diff_log else "None"}
"""

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
    print(f"Rotation bucket: {today_mod}")

    try:
        with open("bgg_collection.json", "r", encoding="utf-8") as f:
            old_data = json.load(f)
    except FileNotFoundError:
        old_data = []

    old_dict = {g["objectid"]: g for g in old_data}

    # --- plays ---
    lastplays = fetch_latest_plays(USERNAME)

    # --- collection完全同期 ---
    owned = fetch_collection(USERNAME, "own")
    wishlist = fetch_collection(USERNAME, "wishlist")
    preordered = fetch_collection(USERNAME, "preordered")
    prevowned = fetch_collection(USERNAME, "prevowned")

    all_games = owned + wishlist + preordered + prevowned
    new_dict = {g["objectid"]: g for g in all_games}

    # --- 差分ログ ---
    diff_lines = []

    for oid, new_game in new_dict.items():
        if oid in old_dict:
            old_game = old_dict[oid]
            if old_game.get("stats") != new_game.get("stats"):
                diff_lines.append(f"Stats changed: {new_game['name']['value']}")
        else:
            diff_lines.append(f"Added: {new_game['name']['value']}")

    removed = set(old_dict) - set(new_dict)
    for r in removed:
        diff_lines.append(f"Removed: {old_dict[r]['name']['value']}")

    # --- thing更新対象 ---
    to_update = []

    for g in new_dict.values():
        oid = int(g["objectid"])

        if any(k not in g for k in ["designers","mechanics","categories","weight","type"]):
            to_update.append(g)
            continue

        if oid % ROTATION_DAYS == today_mod:
            to_update.append(g)

    print(f"Thing targets: {len(to_update)}")

    updated = 0

    for g in to_update:
        try:
            designers, weight, mechanics, categories, game_type = fetch_thing_info(g["objectid"])
            g["designers"] = designers
            g["mechanics"] = mechanics
            g["categories"] = categories
            g["weight"] = weight
            g["type"] = game_type
            updated += 1
            print(f"Updated {g['name']['value']}")
            time.sleep(SLEEP_BETWEEN_CALLS)
        except Exception as e:
            print("Thing error:", e)

    # --- lastplay統合 ---
    for oid, date in lastplays.items():
        if oid in new_dict:
            new_dict[oid]["lastplay"] = date

    final_list = sorted(new_dict.values(), key=lambda x: x["name"]["value"].lower())

    with open("bgg_collection.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)

    print(f"{len(final_list)} games saved")
    print(f"Thing updated: {updated}")

    send_email(updated, len(final_list), "\n".join(diff_lines))


if __name__ == "__main__":
    main()
