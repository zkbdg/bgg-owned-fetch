import os
import requests
import time
import xml.etree.ElementTree as ET
import json
import smtplib
import datetime
from email.mime.text import MIMEText

BGG_API_TOKEN = os.environ["BGG_API_TOKEN"]
BGG_COOKIE = os.environ["BGG_COOKIE"]
API_THING = "https://boardgamegeek.com/xmlapi2/thing"

USERNAME = "zakibg"

ROTATION_DAYS = 100
SLEEP_BETWEEN_CALLS = 1
SLEEP_ON_429 = 60

THING_KEYS = ["designers", "mechanics", "categories", "weight", "type"]

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
# plays
# ====================================
def fetch_latest_plays(username):
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
            if game_id and date:
                if game_id not in lastplays or date > lastplays[game_id]:
                    lastplays[game_id] = date

        page += 1
        time.sleep(1)

    return lastplays

# ====================================
# collection
# ====================================
def fetch_collection(username, param, status_label):
    url = f"https://boardgamegeek.com/xmlapi2/collection?username={username}&{param}=1&stats=1"
    headers = {"User-Agent": "Mozilla/5.0", "Cookie": BGG_COOKIE}

    for _ in range(15):
        resp = requests.get(url, headers=headers, timeout=60)
        if resp.status_code == 202 or not resp.text.strip():
            time.sleep(5)
            continue
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        break
    else:
        raise Exception("Collection fetch timeout")

    games = []
    for item in root.findall("item"):
        g = xml_to_dict(item)

        # 👇 statusを単純化
        g["status"] = status_label

        games.append(g)

    return games

# ====================================
# thing
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

    return designers, mechanics, categories, weight, game_type

# ====================================
# メール
# ====================================
def send_email(updated_count, total_count, target_info):
    EMAIL_FROM = os.environ.get("EMAIL_FROM")
    EMAIL_TO = os.environ.get("EMAIL_TO")
    EMAIL_USER = os.environ.get("EMAIL_USER")
    EMAIL_PASS = os.environ.get("EMAIL_PASS")

    if not all([EMAIL_FROM, EMAIL_TO, EMAIL_USER, EMAIL_PASS]):
        return

    subject = f"BGG Updated: {updated_count} Thing calls"

    body = (
        f"Total games: {total_count}\n"
        f"Thing updated today: {updated_count}\n\n"
        f"Targets ({len(target_info)}):\n"
        + "\n".join(target_info)
    )

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(EMAIL_USER, EMAIL_PASS)
        smtp.send_message(msg)

# ====================================
# main
# ====================================
def main():

    today_mod = datetime.date.today().toordinal() % ROTATION_DAYS

    try:
        with open("bgg_collection.json", "r", encoding="utf-8") as f:
            old_data = json.load(f)
    except FileNotFoundError:
        old_data = []

    old_dict = {g["objectid"]: g for g in old_data}

    # collection完全同期
    owned = fetch_collection(USERNAME, "own", "owned")
    wishlist = fetch_collection(USERNAME, "wishlist", "wishlist")
    preordered = fetch_collection(USERNAME, "preordered", "preordered")
    prevowned = fetch_collection(USERNAME, "prevowned", "previouslyowned")

    all_games = owned + wishlist + preordered + prevowned
    new_dict = {g["objectid"]: g for g in all_games}

    # thing情報移植
    for oid, g in new_dict.items():
        if oid in old_dict:
            for key in THING_KEYS:
                if key in old_dict[oid]:
                    g[key] = old_dict[oid][key]

    # thing差分判定（理由付き）
    to_update = []
    target_info = []

    for g in new_dict.values():
        oid = int(g["objectid"])
        name = g["name"]["value"]

        if any(k not in g for k in THING_KEYS):
            to_update.append(g)
            target_info.append(f"{name} (missing thing data)")
            continue

        if oid % ROTATION_DAYS == today_mod:
            to_update.append(g)
            target_info.append(f"{name} (rotation bucket)")

    print(f"Thing targets: {len(to_update)}")
    for t in target_info:
        print(f"  - {t}")

    updated = 0

    for game in to_update:
        try:
            designers, mechanics, categories, weight, game_type = fetch_thing_info(game["objectid"])
            game["designers"] = designers
            game["mechanics"] = mechanics
            game["categories"] = categories
            game["weight"] = weight
            game["type"] = game_type
            updated += 1
            time.sleep(SLEEP_BETWEEN_CALLS)
        except Exception as e:
            print(f"Thing error {game['objectid']} {e}")

    # plays
    lastplays = fetch_latest_plays(USERNAME)
    for oid, date in lastplays.items():
        if oid in new_dict:
            new_dict[oid]["lastplay"] = date

    final_list = sorted(new_dict.values(), key=lambda x: x["name"]["value"].lower())

    with open("bgg_collection.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)

    print(f"{len(final_list)} games saved")
    print(f"Thing updated: {updated}")

    send_email(updated, len(final_list), target_info)


if __name__ == "__main__":
    main()
