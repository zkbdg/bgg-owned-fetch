import requests
import xml.etree.ElementTree as ET
import json

USERNAME = "zakibg"

URL = f"https://api.betterbggcollection.com/xmlapi2/collection?own=1&stats=1&excludesubtype=boardgameexpansion&username={USERNAME}"

headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/xml",
}

resp = requests.get(URL, headers=headers, timeout=60)
resp.raise_for_status()

root = ET.fromstring(resp.content)

games = []

for item in root.findall("item"):
    games.append({
        "id": item.attrib.get("objectid"),
        "name": item.find("name").attrib.get("value") if item.find("name") is not None else None,
        "year": item.find("yearpublished").attrib.get("value") if item.find("yearpublished") is not None else None,
        "numplays": item.find("numplays").attrib.get("value") if item.find("numplays") is not None else "0",
    })

with open("owned_list.json", "w", encoding="utf-8") as f:
    json.dump(games, f, ensure_ascii=False, indent=2)

print(f"{len(games)} games fetched.")
