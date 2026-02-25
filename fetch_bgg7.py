import os
import requests
import time
import xml.etree.ElementTree as ET
import json
import smtplib
import datetime
from email.mime.text import MIMEText

BGG_API_TOKEN = os.environ["BGG_API_TOKEN"]

API_COLLECTION = "https://boardgamegeek.com/xmlapi2/collection"
API_THING = "https://boardgamegeek.com/xmlapi2/thing"
API_PLAYS = "https://boardgamegeek.com/xmlapi2/plays"

USERNAME = "ZAKIbg"

THING_KEYS = [
    "yearpublished",
    "minplayers",
    "maxplayers",
    "playingtime",
    "minplaytime",
    "maxplaytime",
]

COLLECTION_CALLS = 0
THING_CALLS = 0
PLAY_CALLS = 0


def fetch_collection():
    global COLLECTION_CALLS

    url = f"{API_COLLECTION}?username={USERNAME}&own=1&wishlist=1&preordered=1&prevowned=1&stats=1"

    for _ in range(15):
        resp = requests.get(url, timeout=60)
        COLLECTION_CALLS += 1

        if resp.status_code == 202 or not resp.text.strip():
            time.sleep(5)
            continue

        root = ET.fromstring(resp.content)
        items = []

        for item in root.findall("item"):
            game = {
                "objectid": item.attrib["objectid"],
                "name": item.find("name").text if item.find("name") is not None else "",
            }

            status = item.find("status")
            if status is not None:
                if status.attrib.get("own") == "1":
                    game["status"] = "owned"
                elif status.attrib.get("wishlist") == "1":
                    game["status"] = "wishlist"
                elif status.attrib.get("preordered") == "1":
                    game["status"] = "preordered"
                elif status.attrib.get("prevowned") == "1":
                    game["status"] = "previouslyowned"

            items.append(game)

        return items

    raise Exception("Collection fetch failed")


def fetch_thing(objectid):
    global THING_CALLS

    url = f"{API_THING}?id={objectid}&stats=1"
    resp = requests.get(url, timeout=60)
    THING_CALLS += 1

    if resp.status_code != 200:
        return {}

    root = ET.fromstring(resp.content)
    item = root.find("item")
    if item is None:
        return {}

    data = {}
    for key in THING_KEYS:
        elem = item.find(key)
        if elem is not None and "value" in elem.attrib:
            data[key] = elem.attrib["value"]

    return data


def fetch_lastplays():
    global PLAY_CALLS

    url = f"{API_PLAYS}?username={USERNAME}&page=1"
    resp = requests.get(url, timeout=60)
    PLAY_CALLS += 1

    if resp.status_code != 200:
        return {}

    root = ET.fromstring(resp.content)
    plays = {}

    for play in root.findall("play"):
        date = play.attrib.get("date")
        item = play.find("item")
        if item is None:
            continue

        oid = item.attrib.get("objectid")
        if oid and oid not in plays:
            plays[oid] = date

    return plays


def send_mail(body):
    msg = MIMEText(body)
    msg["Subject"] = f"[{THING_CALLS} THING / {COLLECTION_CALLS} COLLECTION / {PLAY_CALLS} PLAY API calls]"
    msg["From"] = os.environ["MAIL_FROM"]
    msg["To"] = os.environ["MAIL_TO"]

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(os.environ["MAIL_FROM"], os.environ["MAIL_PASSWORD"])
        server.send_message(msg)


def main():
    today = datetime.datetime.utcnow()
    is_monthly_refresh = today.day == 1

    try:
        with open("bgg_collection.json", "r") as f:
            old_data = json.load(f)
    except:
        old_data = []

    old_dict = {g["objectid"]: g for g in old_data}

    collection = fetch_collection()
    new_dict = {g["objectid"]: g for g in collection}

    # ===== thing引き継ぎ＋lastplay保護 =====
    for oid, g in new_dict.items():
        if oid in old_dict:
            # thing情報引き継ぎ
            for key in THING_KEYS:
                if key in old_dict[oid]:
                    g[key] = old_dict[oid][key]

            # lastplay引き継ぎ（安全化）
            if "lastplay" in old_dict[oid]:
                g["lastplay"] = old_dict[oid]["lastplay"]

    # ===== ローテーション対象のみthing更新 =====
    rotation_targets = list(new_dict.keys())[:10]

    for oid in rotation_targets:
        thing_data = fetch_thing(oid)
        new_dict[oid].update(thing_data)

    # ===== plays更新 =====
    plays = fetch_lastplays()
    for oid, date in plays.items():
        if oid in new_dict:
            new_dict[oid]["lastplay"] = date

    # ===== 月初はlastplay再構築 =====
    if is_monthly_refresh:
        for g in new_dict.values():
            g.pop("lastplay", None)

        plays = fetch_lastplays()
        for oid, date in plays.items():
            if oid in new_dict:
                new_dict[oid]["lastplay"] = date

    final_data = list(new_dict.values())

    with open("bgg_collection.json", "w") as f:
        json.dump(final_data, f, indent=2, ensure_ascii=False)

    body = (
        f"Collection size: {len(final_data)}\n"
        f"THING calls: {THING_CALLS}\n"
        f"COLLECTION calls: {COLLECTION_CALLS}\n"
        f"PLAY calls: {PLAY_CALLS}"
    )

    print(body)
    send_mail(body)


if __name__ == "__main__":
    main()
