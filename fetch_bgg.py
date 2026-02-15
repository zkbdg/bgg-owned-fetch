import requests
import json

USERNAME = "zakibg"

URL = f"https://bgg-proxy.chemzigzagcashmere.workers.dev/"

headers = {
    "User-Agent": "Mozilla/5.0"
}

resp = requests.get(URL, headers=headers, timeout=60)
resp.raise_for_status()

data = resp.json()

games = []

for item in data["items"]:
    games.append({
        "id": item.get("objectid"),
        "name": item.get("name"),
        "year": item.get("yearpublished"),
        "numplays": item.get("numplays"),
    })

with open("owned_list.json", "w", encoding="utf-8") as f:
    json.dump(games, f, ensure_ascii=False, indent=2)

print(f"{len(games)} games fetched.")
