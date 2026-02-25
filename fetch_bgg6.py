import os
import requests
import time
import xml.etree.ElementTree as ET
import json
import smtplib
import datetime
from email.mime.text import MIMEText

BGG_API_TOKEN = os.environ["BGG_API_TOKEN"]
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
# plays（月1フル + 差分取得）
# ====================================
def fetch_latest_plays(username, old_lastplays, force_full=False):
    headers = {"Authorization": f"Bearer {BGG_API_TOKEN}"}
    lastplays = {}
    page = 1

    print("Plays mode:", "FULL REFRESH" if force_full else "INCREMENTAL")

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

        stop = False

        for play in plays:
            date = play.get("date")
            item = play.find("item")
            if item is None:
                continue

            game_id = item.get("objectid")
            if not game_id or not date:
                continue

            if not force_full:
                old_date = old_lastplays.get(game_id)
                if old_date and date <= old_date:
                    stop = True
                    break

            if game_id not in lastplays or date > lastplays.get(game_id, ""):
                lastplays[game_id] = date

        if stop:
            break

        page += 1
        time.sleep(1)

    return lastplays

# ====================================
# collection
# ====================================
def fetch_collection(username, param, status_label):
    url = f"https://boardgamegeek.com/xmlapi2/collection?username={username}&{param}=1&stats=1"
    headers = {"Authorization": f"Bearer {BGG_API_TOKEN}"}

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
        g["status"] = status_label
        games.append(g)

    return games

# ====================================
# thing
# ====================================
def fetch_thing_info(game_id):
    headers = {"Authorization": f"Bearer {BGG_API_TOKEN}"}
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
    weight = weight_elem.attrib["value"] if weight_elem is not None else None

    game_type = item.attrib.get("type", "boardgame")

    return designers, mechanics, categories, weight, game_type

# ====================================
# main
# ====================================
def main():

    today = datetime.date.today()
    today_mod = today.toordinal() % ROTATION_DAYS

    force_full_refresh = (today.day == 1)

    try:
        with open("bgg_collection.json", "r", encoding="utf-8") as f:
            old_data = json.load(f)
    except FileNotFoundError:
        old_data = []

    old_dict = {g["objectid"]: g for g in old_data}
    old_lastplays = {
        g["objectid"]: g.get("lastplay")
        for g in old_data
        if g.get("lastplay")
    }

    owned = fetch_collection(USERNAME, "own", "owned")
    wishlist = fetch_collection(USERNAME, "wishlist", "wishlist")
    preordered = fetch_collection(USERNAME, "preordered", "preordered")
    prevowned = fetch_collection(USERNAME, "prevowned", "previouslyowned")

    all_games = owned + wishlist + preordered + prevowned
    new_dict = {g["objectid"]: g for g in all_games}

    for oid, g in new_dict.items():
        if oid in old_dict:
            for key in THING_KEYS:
                if key in old_dict[oid]:
                    g[key] = old_dict[oid][key]

    # ===== thing rotation =====
    to_update = []
    for g in new_dict.values():
        oid = int(g["objectid"])

        if any(k not in g for k in THING_KEYS):
            to_update.append(g)
            continue

        if oid % ROTATION_DAYS == today_mod:
            to_update.append(g)

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

    # ===== plays =====
    lastplays = fetch_latest_plays(
        USERNAME,
        old_lastplays,
        force_full=force_full_refresh
    )

    # 差分マージ
    for oid, date in lastplays.items():
        if oid in new_dict:
            new_dict[oid]["lastplay"] = date

    final_list = sorted(new_dict.values(), key=lambda x: x["name"]["value"].lower())

    with open("bgg_collection.json", "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)

    print(f"{len(final_list)} games saved")
    print(f"Thing updated: {updated}")

if __name__ == "__main__":
    main()
